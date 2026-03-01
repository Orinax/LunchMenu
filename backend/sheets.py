"""
Google Sheets fetching logic.

Reads spreadsheet metadata and values, then calls the parser.
"""
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from parser import (
    classify_tab,
    extract_header_info,
    find_category_blocks,
    parse_sheet_values,
    parse_week_label,
)

logger = logging.getLogger(__name__)


def fetch_and_parse(spreadsheet_id: str) -> Dict[str, Any]:
    """
    Fetch the spreadsheet and return the normalised menu dict.
    """
    from auth import get_sheets_service

    service = get_sheets_service()
    sheets_api = service.spreadsheets()

    # ── 1. Get spreadsheet metadata ─────────────────────────────────────────
    meta = (
        sheets_api.get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties,merges)",
        )
        .execute()
    )

    raw_sheets = meta.get("sheets", [])
    logger.info("Spreadsheet has %d sheets", len(raw_sheets))

    # ── 2. Identify relevant tabs ────────────────────────────────────────────
    candidates: List[Dict] = []
    for sheet in raw_sheets:
        props = sheet.get("properties", {})
        if props.get("hidden"):
            continue
        tab_title: str = props.get("title", "")
        menu_type = classify_tab(tab_title)
        if menu_type is None:
            continue
        candidates.append(
            {
                "sheetId": props.get("sheetId"),
                "title": tab_title,
                "menu_type": menu_type,
                "merges": sheet.get("merges", []),
                "index": props.get("index", 999),
            }
        )
        logger.info("Candidate tab: %r → %s", tab_title, menu_type)

    if not candidates:
        raise ValueError(
            "No 'Lunch Ala Carte' or 'Lunch Program' tabs found in the spreadsheet."
        )

    # ── 3. Read header row for each candidate to get week info ───────────────
    ranges = [f"'{c['title']}'!A1:G2" for c in candidates]
    batch = (
        sheets_api.values()
        .batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            valueRenderOption="FORMATTED_VALUE",
        )
        .execute()
    )
    header_results = {
        vr["range"].split("!")[0].strip("'"): vr.get("values", [])
        for vr in batch.get("valueRanges", [])
    }

    # Augment candidates with parsed week info
    for c in candidates:
        hv = header_results.get(c["title"], [])
        _title, week_text, _, _ = extract_header_info(hv, c["merges"])
        start, end, label = parse_week_label(week_text)
        c["week_start"] = start
        c["week_end"] = end
        c["week_label"] = label
        c["week_text"] = week_text

    # ── 4. Select newest/current week for each menu type ────────────────────
    today = date.today()
    selected: Dict[str, Dict] = {}
    for menu_type in ("alacarte", "program"):
        type_candidates = [c for c in candidates if c["menu_type"] == menu_type]
        if not type_candidates:
            logger.warning("No tab found for menu type: %s", menu_type)
            continue
        selected[menu_type] = _pick_best_tab(type_candidates, today)
        logger.info(
            "Selected tab for %s: %r (week: %s)",
            menu_type,
            selected[menu_type]["title"],
            selected[menu_type].get("week_label"),
        )

    if not selected:
        raise ValueError("Could not select any tabs.")

    # ── 5. Fetch full sheet data for selected tabs ───────────────────────────
    full_ranges = [f"'{s['title']}'!A1:Z200" for s in selected.values()]
    full_batch = (
        sheets_api.values()
        .batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=full_ranges,
            valueRenderOption="FORMATTED_VALUE",
        )
        .execute()
    )
    full_data = {
        vr["range"].split("!")[0].strip("'"): vr.get("values", [])
        for vr in full_batch.get("valueRanges", [])
    }

    # ── 6. Parse each selected tab ──────────────────────────────────────────
    menus: Dict[str, Any] = {}
    week_info: Optional[Dict] = None

    for menu_type, tab in selected.items():
        values = full_data.get(tab["title"], [])
        merges = tab["merges"]
        days = parse_sheet_values(values, merges)
        menus[menu_type] = {"days": days}

        if week_info is None and tab.get("week_start"):
            week_info = {
                "start": tab["week_start"].isoformat(),
                "end": tab["week_end"].isoformat() if tab.get("week_end") else None,
                "label": tab.get("week_label", ""),
            }

    if week_info is None:
        week_info = {"start": None, "end": None, "label": ""}

    # ── 7. Build response ───────────────────────────────────────────────────
    selected_sheets_info = [
        {"title": s["title"], "sheetId": s["sheetId"]} for s in selected.values()
    ]

    return {
        "week": week_info,
        "lastFetched": datetime.now(timezone.utc).isoformat(),
        "menus": menus,
        "source": {
            "spreadsheetId": spreadsheet_id,
            "selectedSheets": selected_sheets_info,
        },
    }


def _pick_best_tab(tabs: List[Dict], today: date) -> Dict:
    """
    From a list of candidate tabs (same menu_type), prefer:
    1. The tab whose week range contains today.
    2. The tab with the most-recent start date.
    3. Fall back to the last sheet by index.
    """
    # Current week first
    for tab in tabs:
        ws, we = tab.get("week_start"), tab.get("week_end")
        if ws and we and ws <= today <= we:
            return tab
    # Most recent start date
    dated = [t for t in tabs if t.get("week_start")]
    if dated:
        return max(dated, key=lambda t: t["week_start"])
    # Fallback: highest sheet index (usually most recent)
    return max(tabs, key=lambda t: t.get("index", 0))
