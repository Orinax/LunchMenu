"""
Spreadsheet parsing logic.

Converts raw Google Sheets API responses (values + merges) into the
normalised menu JSON schema.
"""
import logging
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from dateutil import parser as dateutil_parser  # type: ignore

logger = logging.getLogger(__name__)

# ── Column helpers ───────────────────────────────────────────────────────────

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def col_index_to_letter(idx: int) -> str:
    """0-based column index to A1 letter (e.g. 0→'A', 25→'Z', 26→'AA')."""
    result = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def a1_col(letter: str) -> int:
    """A1 column letter(s) to 0-based index."""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


# ── Merge helpers ────────────────────────────────────────────────────────────


def merges_in_col(merges: List[Dict], col: int) -> List[Dict]:
    """Return merges whose startColumnIndex == col (0-based)."""
    return [
        m
        for m in merges
        if m.get("startColumnIndex") == col
        and m.get("endColumnIndex", col + 1) == col + 1
    ]


def find_header_merge(
    merges: List[Dict], row: int, start_col: int, end_col: int
) -> Optional[Dict]:
    """
    Return the first merge that starts in *row* (0-based) and whose column
    span overlaps [start_col, end_col).
    """
    for m in merges:
        rs, re_ = m.get("startRowIndex", -1), m.get("endRowIndex", -1)
        cs, ce = m.get("startColumnIndex", -1), m.get("endColumnIndex", -1)
        if rs == row and re_ > row and cs >= start_col and ce <= end_col + 1:
            return m
    return None


# ── Week date parsing ────────────────────────────────────────────────────────

_MONTH_NAMES = (
    "january|february|march|april|may|june|"
    "july|august|september|october|november|december"
)
_WEEK_RE = re.compile(
    rf"(\d{{1,2}})\s*[-–]\s*(\d{{1,2}})\s+({_MONTH_NAMES}),?\s+(\d{{4}})",
    re.IGNORECASE,
)
_WEEK_RANGE_RE = re.compile(
    rf"(\d{{1,2}})\s+({_MONTH_NAMES})\s*[-–]\s*(\d{{1,2}})\s+({_MONTH_NAMES}),?\s+(\d{{4}})",
    re.IGNORECASE,
)


def parse_week_label(text: str) -> Tuple[Optional[date], Optional[date], str]:
    """
    Parse a week label like '2-6 March, 2026' or '30 March – 3 April, 2026'.

    Returns (start_date, end_date, label_text).
    """
    text = text.strip()

    # Same-month range: "2-6 March, 2026"
    m = _WEEK_RE.search(text)
    if m:
        d1, d2, month, year = m.group(1), m.group(2), m.group(3), m.group(4)
        try:
            start = dateutil_parser.parse(f"{d1} {month} {year}").date()
            end = dateutil_parser.parse(f"{d2} {month} {year}").date()
            return start, end, text
        except Exception:
            pass

    # Cross-month range: "30 March – 3 April, 2026"
    m2 = _WEEK_RANGE_RE.search(text)
    if m2:
        d1, mon1, d2, mon2, year = (
            m2.group(1),
            m2.group(2),
            m2.group(3),
            m2.group(4),
            m2.group(5),
        )
        try:
            start = dateutil_parser.parse(f"{d1} {mon1} {year}").date()
            end = dateutil_parser.parse(f"{d2} {mon2} {year}").date()
            return start, end, text
        except Exception:
            pass

    logger.warning("Could not parse week label from: %r", text)
    return None, None, text


# ── Tab identification ───────────────────────────────────────────────────────

_ALA_CARTE_RE = re.compile(r"ala\s*carte", re.IGNORECASE)
_PROGRAM_RE = re.compile(r"program", re.IGNORECASE)


def classify_tab(title_text: str) -> Optional[str]:
    """Return 'alacarte', 'program', or None."""
    if _ALA_CARTE_RE.search(title_text):
        return "alacarte"
    if _PROGRAM_RE.search(title_text):
        return "program"
    return None


# ── Header extraction ────────────────────────────────────────────────────────


def extract_header_info(
    header_values: List[List[str]], merges: List[Dict]
) -> Tuple[str, str, str, str]:
    """
    Given the A1:G2 values and the sheet's merges, return
    (menu_type_text, week_label, raw_title_cell, raw_week_cell).

    Row 1 (index 0) contains merged cells for title and week range.
    """
    row0 = header_values[0] if header_values else []

    # Flatten the row; Google API only puts a value in the first cell of a merge.
    # We walk column merges in row 0 to find title cell and week-range cell.
    title_text = row0[0] if row0 else ""
    week_text = ""

    # Find any merge starting in row 0, col >= 2 → that's the week range merge
    for m in merges:
        if m.get("startRowIndex") == 0 and m.get("endRowIndex", 1) > 0:
            cs = m.get("startColumnIndex", 0)
            if cs >= 2 and cs < len(row0):
                candidate = row0[cs]
                if candidate:
                    week_text = candidate
                    break

    # If week_text not found via merge, scan remaining cells in row 0
    if not week_text:
        for cell in row0[1:]:
            if cell and re.search(r"\d", cell):
                week_text = cell
                break

    return title_text, week_text, title_text, week_text


# ── Category block parsing ────────────────────────────────────────────────────


def find_category_blocks(
    merges: List[Dict], total_rows: int
) -> List[Tuple[str, int, int]]:
    """
    Use merges in column A (col 0) to locate category blocks.

    Returns list of (category_cell_ref, start_row, end_row) where rows are
    0-based and end_row is exclusive.  Category blocks with only 1 row are
    ignored (they are likely sub-headers).
    """
    col_a_merges = merges_in_col(merges, 0)
    blocks = []
    for m in col_a_merges:
        rs = m.get("startRowIndex", 0)
        re_ = m.get("endRowIndex", rs + 1)
        if re_ - rs >= 2:  # at least 2 rows → real category block
            blocks.append((f"A{rs+1}:{rs+1}", rs, re_))
    # Sort by start row
    blocks.sort(key=lambda x: x[1])
    return blocks


def extract_cell_text(values: List[List[str]], row: int, col: int) -> str:
    """Safely retrieve a cell value."""
    try:
        return (values[row][col] or "").strip()
    except (IndexError, TypeError):
        return ""


def parse_day_items(
    values: List[List[str]],
    start_row: int,
    end_row: int,
    col: int,
) -> List[Dict[str, str]]:
    """
    For a single category block (rows start_row..end_row, exclusive) and a
    single day column, pair alternating EN/TH rows into items.
    Skips pairs where both EN and TH are blank.
    Tolerates odd row counts (last unpaired row → en only).
    """
    items: List[Dict[str, str]] = []
    row = start_row
    while row < end_row:
        en = extract_cell_text(values, row, col)
        th = extract_cell_text(values, row + 1, col) if row + 1 < end_row else ""
        if en or th:
            items.append({"en": en, "th": th})
        row += 2
    return items


def parse_sheet_values(
    values: List[List[str]],
    merges: List[Dict],
    day_cols: Optional[List[int]] = None,
) -> Dict[str, List[Dict]]:
    """
    Parse a sheet's values + merges into a days dict:
    {
      "monday": [ { "category": "...", "items": [ { "en": "...", "th": "..." } ] } ],
      ...
    }

    Parameters
    ----------
    values    : 2-D list from sheets API (rows × cols), 0-based.
    merges    : sheet merges from the Sheets API.
    day_cols  : 0-based column indices for Mon–Fri.  If None, auto-detected
                from row 1 (header row) or defaults to cols 1-5 (B-F).
    """
    total_rows = len(values)

    # Auto-detect or default day columns
    if day_cols is None:
        day_cols = _detect_day_columns(values, merges)

    category_blocks = find_category_blocks(merges, total_rows)
    if not category_blocks:
        logger.warning("No category blocks found (no column-A merges with ≥2 rows)")

    days: Dict[str, List[Dict]] = {day: [] for day in DAY_NAMES}

    for _ref, start_row, end_row in category_blocks:
        # Get category name from column A
        cat_en = extract_cell_text(values, start_row, 0)
        # Some cells have EN + TH on the same line separated by newline
        cat_lines = cat_en.split("\n")
        cat_label = cat_lines[0].strip() if cat_lines else cat_en

        for day_idx, col in enumerate(day_cols):
            if day_idx >= len(DAY_NAMES):
                break
            day_name = DAY_NAMES[day_idx]
            items = parse_day_items(values, start_row, end_row, col)
            if items:
                days[day_name].append({"category": cat_label, "items": items})

    return days


def _detect_day_columns(
    values: List[List[str]], merges: List[Dict]
) -> List[int]:
    """
    Try to find Mon–Fri columns from the header row (row index 1, i.e. row 2).
    Falls back to columns 1-5 (B-F).
    """
    day_keywords = ["mon", "tue", "wed", "thu", "fri"]
    header_row: List[str] = []
    for row_idx in range(min(3, len(values))):
        row = values[row_idx]
        matched = sum(
            1
            for cell in row
            if any(kw in (cell or "").lower() for kw in day_keywords)
        )
        if matched >= 3:
            header_row = row
            break

    if header_row:
        cols = []
        for i, cell in enumerate(header_row):
            cell_lower = (cell or "").lower()
            if any(kw in cell_lower for kw in day_keywords):
                cols.append(i)
        if len(cols) >= 5:
            return cols[:5]

    # Default: B=1, C=2, D=3, E=4, F=5
    return [1, 2, 3, 4, 5]
