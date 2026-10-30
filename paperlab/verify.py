"""Verification of expected results against the paper's PDF tables.

Two levels:
1. Presence — every extracted value appears on its cited page.
2. Pairing — each value sits at the table position its metric label claims,
   using a per-case table layout (the geometry of pdftotext cell order).

Verification is mechanical. It never produces a verdict.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

VALUE_RX = re.compile(r"\d+\.\d+\s*±\s*\d+\.\d+%|\d+\.\d+%")


def extract_page_values(text: str) -> list[str]:
    return VALUE_RX.findall(text)


def load_case(case_dir: str | Path) -> dict:
    case_dir = Path(case_dir)
    expected = json.loads((case_dir / "expected_results.json").read_text())
    layouts_path = case_dir / "table_layouts.json"
    layouts = json.loads(layouts_path.read_text()) if layouts_path.exists() else None
    return {"dir": case_dir, "expected": expected, "layouts": layouts}


def verify_presence(case: dict, pdf_path=None) -> dict:
    """Level 1: every result value appears on its cited page."""
    results = case["expected"]["results"]
    fails = []
    for i, r in enumerate(results):
        from .checks import load_page_text
        try:
            text = load_page_text(case["dir"], r["page"], pdf_path)
        except FileNotFoundError as e:
            fails.append({"index": i, "metric": r["metric"], "error": str(e)})
            continue
        values = extract_page_values(text)
        if r["value"] not in values:
            norm = re.sub(r"\s+", " ", text)
            if re.sub(r"\s+", " ", r["value"]) not in norm:
                fails.append({"index": i, "metric": r["metric"],
                              "value": r["value"], "page": r["page"]})
    return {"level": "presence", "total": len(results),
            "passed": len(results) - len(fails), "fails": fails}


def verify_pairing(case: dict, pdf_path=None) -> dict:
    """Level 2: metric-to-value pairing via per-case table layouts.

    A layout file maps each table to: page, offset (first index of that
    table's values within the page's flat value sequence), and 'map' —
    a list where map[k] is the flat PDF position for result k within
    the table (results ordered as in expected_results.json).
    """
    if case["layouts"] is None:
        return {"level": "pairing", "skipped": "no table_layouts.json for this case"}
    from .checks import load_page_text
    results = case["expected"]["results"]
    by_table: dict[str, list] = {}
    for i, r in enumerate(results):
        by_table.setdefault(r["table_or_figure"], []).append(i)
    fails = []
    checked = 0
    for table, layout in case["layouts"].items():
        idxs = by_table.get(table, [])
        if not idxs or "map" not in layout:
            continue
        try:
            text = load_page_text(case["dir"], layout["page"], pdf_path)
        except FileNotFoundError as e:
            fails.append({"table": table, "error": str(e)})
            continue
        page_vals = extract_page_values(text)
        offset = layout.get("offset", 0)
        for k, pdf_pos in enumerate(layout["map"]):
            if k >= len(idxs):
                break
            r = results[idxs[k]]
            pdf_val = page_vals[offset + pdf_pos] if offset + pdf_pos < len(page_vals) else None
            checked += 1
            if pdf_val != r["value"]:
                fails.append({"table": table, "metric": r["metric"],
                              "json": r["value"], "pdf": pdf_val})
    return {"level": "pairing", "total": checked,
            "passed": checked - len(fails), "fails": fails}


def verify_case(case_dir: str | Path, pdf_path=None) -> dict:
    case = load_case(case_dir)
    presence = verify_presence(case, pdf_path)
    pairing = verify_pairing(case, pdf_path)
    return {"presence": presence, "pairing": pairing}


def pairing_layout_from_expected(case_dir: str | Path, page: int,
                                 flat_pdf_values: list[str]) -> dict:
    """Helper to (re)derive a pairing layout from a fresh PDF extraction.

    Given the page's flat value sequence, record the position of each
    result value. Ambiguities (same value twice) must be resolved by a human.
    """
    case = load_case(case_dir)
    layout: dict[int, int] = {}
    ambiguous = []
    for i, r in enumerate(case["expected"]["results"]):
        if r["page"] != page:
            continue
        positions = [j for j, v in enumerate(flat_pdf_values) if v == r["value"]]
        if len(positions) == 1:
            layout[i] = positions[0]
        elif len(positions) == 0:
            ambiguous.append({"metric": r["metric"], "value": r["value"], "issue": "not found"})
        else:
            ambiguous.append({"metric": r["metric"], "value": r["value"],
                              "issue": f"multiple positions {positions}"})
    return {"layout": layout, "ambiguous": ambiguous}
