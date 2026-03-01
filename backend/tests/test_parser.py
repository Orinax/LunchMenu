"""
Unit tests for the parser module.

Uses mocked/static API responses – no real Google Sheets calls.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from parser import (
    classify_tab,
    col_index_to_letter,
    extract_cell_text,
    find_category_blocks,
    merges_in_col,
    parse_day_items,
    parse_sheet_values,
    parse_week_label,
)


# ── col_index_to_letter ──────────────────────────────────────────────────────

def test_col_index_to_letter():
    assert col_index_to_letter(0) == "A"
    assert col_index_to_letter(1) == "B"
    assert col_index_to_letter(25) == "Z"
    assert col_index_to_letter(26) == "AA"


# ── classify_tab ─────────────────────────────────────────────────────────────

def test_classify_tab_alacarte():
    assert classify_tab("Lunch Ala Carte (Mar 2-6)") == "alacarte"
    assert classify_tab("lunch ala carte") == "alacarte"


def test_classify_tab_program():
    assert classify_tab("Lunch Program (Mar 2-6)") == "program"
    assert classify_tab("LUNCH PROGRAM") == "program"


def test_classify_tab_unknown():
    assert classify_tab("Breakfast") is None


# ── parse_week_label ─────────────────────────────────────────────────────────

def test_parse_week_label_same_month():
    start, end, label = parse_week_label("2-6 March, 2026")
    assert start is not None
    assert start.day == 2
    assert start.month == 3
    assert start.year == 2026
    assert end.day == 6


def test_parse_week_label_cross_month():
    start, end, label = parse_week_label("30 March – 3 April, 2026")
    assert start is not None
    assert start.day == 30
    assert start.month == 3
    assert end.day == 3
    assert end.month == 4


def test_parse_week_label_invalid():
    start, end, label = parse_week_label("no date here")
    assert start is None
    assert end is None


# ── merges_in_col ─────────────────────────────────────────────────────────────

def test_merges_in_col():
    merges = [
        {"startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 5, "endRowIndex": 10},
        {"startColumnIndex": 1, "endColumnIndex": 3, "startRowIndex": 5, "endRowIndex": 10},
        {"startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 15, "endRowIndex": 20},
    ]
    result = merges_in_col(merges, 0)
    assert len(result) == 2


# ── find_category_blocks ──────────────────────────────────────────────────────

def test_find_category_blocks():
    merges = [
        # Category block: rows 5-14 (10 rows)
        {"startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 5, "endRowIndex": 15},
        # Another category block: rows 15-24
        {"startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 15, "endRowIndex": 25},
        # Single-row merge (header) – should be ignored
        {"startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 0, "endRowIndex": 1},
        # Multi-col merge – should be ignored
        {"startColumnIndex": 0, "endColumnIndex": 3, "startRowIndex": 0, "endRowIndex": 2},
    ]
    blocks = find_category_blocks(merges, 30)
    assert len(blocks) == 2
    assert blocks[0][1] == 5  # start_row
    assert blocks[0][2] == 15  # end_row
    assert blocks[1][1] == 15
    assert blocks[1][2] == 25


# ── extract_cell_text ─────────────────────────────────────────────────────────

def test_extract_cell_text():
    values = [["A", "B", "C"], ["D", "", "F"]]
    assert extract_cell_text(values, 0, 0) == "A"
    assert extract_cell_text(values, 1, 1) == ""
    assert extract_cell_text(values, 5, 0) == ""  # out of bounds


# ── parse_day_items ───────────────────────────────────────────────────────────

def test_parse_day_items_basic():
    values = [
        ["Cat A", "Grilled Chicken", "", "", "", ""],
        ["", "ไก่ย่าง", "", "", "", ""],
        ["", "Fried Rice", "", "", "", ""],
        ["", "ข้าวผัด", "", "", "", ""],
    ]
    items = parse_day_items(values, 0, 4, 1)
    assert len(items) == 2
    assert items[0]["en"] == "Grilled Chicken"
    assert items[0]["th"] == "ไก่ย่าง"
    assert items[1]["en"] == "Fried Rice"
    assert items[1]["th"] == "ข้าวผัด"


def test_parse_day_items_skip_blanks():
    values = [
        ["Cat", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "Soup", "", "", "", ""],
        ["", "ซุป", "", "", "", ""],
    ]
    items = parse_day_items(values, 0, 4, 1)
    # First pair is blank – should be skipped
    assert len(items) == 1
    assert items[0]["en"] == "Soup"


def test_parse_day_items_odd_rows():
    values = [
        ["Cat", "Item A", "", "", "", ""],
        ["", "ไอเท็ม เอ", "", "", "", ""],
        ["", "Item B", "", "", "", ""],  # unpaired – no TH row
    ]
    items = parse_day_items(values, 0, 3, 1)
    assert len(items) == 2
    assert items[1]["en"] == "Item B"
    assert items[1]["th"] == ""


# ── parse_sheet_values ────────────────────────────────────────────────────────

def _make_sample_sheet():
    """
    Build a minimal sample sheet similar to the real spreadsheet.

    Row 0 (1): header – "Lunch Ala Carte"  |  week label
    Row 1 (2): day headers – Mon Tue Wed Thu Fri
    Row 2-5 (3-6): Category "Thai food" block – 4 rows (2 EN+TH pairs)
    Row 6-9 (7-10): Category "Western" block – 4 rows
    """
    values = [
        ["Lunch Ala Carte", "", "2-6 March, 2026", "", "", "", ""],
        ["", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", ""],
        # Thai food block (rows 2-5)
        ["Thai food\nอาหารไทย", "Pad Thai", "Green Curry", "Tom Yum Soup", "Basil Chicken", "Mango Sticky Rice"],
        ["", "ผัดไทย", "แกงเขียวหวาน", "ต้มยำกุ้ง", "กระเพราไก่", "ข้าวเหนียวมะม่วง"],
        ["", "Pad See Ew", "Massaman Curry", "Som Tum", "Khao Man Gai", "Larb"],
        ["", "ผัดซีอิ๊ว", "แกงมัสมั่น", "ส้มตำ", "ข้าวมันไก่", "ลาบ"],
        # Western block (rows 6-9)
        ["Western\nอาหารตะวันตก", "Pasta", "Burger", "Pizza", "Steak", "Sandwich"],
        ["", "พาสต้า", "เบอร์เกอร์", "พิซซ่า", "สเต็ก", "แซนวิช"],
        ["", "Fish & Chips", "Caesar Salad", "Spaghetti", "Roast Chicken", "Quiche"],
        ["", "ฟิชแอนด์ชิพส์", "ซีซาร์สลัด", "สปาเก็ตตี้", "ไก่อบ", "ควิช"],
    ]
    merges = [
        # Title merge A1:B1 (col 0, row 0)
        {"startColumnIndex": 0, "endColumnIndex": 2, "startRowIndex": 0, "endRowIndex": 1},
        # Week range merge C1:F1 (col 2, row 0)
        {"startColumnIndex": 2, "endColumnIndex": 7, "startRowIndex": 0, "endRowIndex": 1},
        # Thai food category block: col A, rows 2-5
        {"startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 2, "endRowIndex": 6},
        # Western category block: col A, rows 6-9
        {"startColumnIndex": 0, "endColumnIndex": 1, "startRowIndex": 6, "endRowIndex": 10},
    ]
    return values, merges


def test_parse_sheet_values_categories():
    values, merges = _make_sample_sheet()
    days = parse_sheet_values(values, merges, day_cols=[1, 2, 3, 4, 5])
    assert "monday" in days
    assert len(days["monday"]) == 2  # 2 categories


def test_parse_sheet_values_items():
    values, merges = _make_sample_sheet()
    days = parse_sheet_values(values, merges, day_cols=[1, 2, 3, 4, 5])
    monday_thai = days["monday"][0]
    assert monday_thai["category"] == "Thai food"
    assert len(monday_thai["items"]) == 2
    assert monday_thai["items"][0]["en"] == "Pad Thai"
    assert monday_thai["items"][0]["th"] == "ผัดไทย"


def test_parse_sheet_values_friday():
    values, merges = _make_sample_sheet()
    days = parse_sheet_values(values, merges, day_cols=[1, 2, 3, 4, 5])
    friday_western = days["friday"][1]
    assert friday_western["items"][0]["en"] == "Sandwich"
    assert friday_western["items"][1]["en"] == "Quiche"
