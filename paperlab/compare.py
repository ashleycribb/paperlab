"""Comparison of a student's run against the paper's expected results.

Computes deltas and within-CI flags. It never states whether a run
supports the paper — that is the human verdict field.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

VALUE_RX = re.compile(
    r"(?P<point>\d+(?:\.\d+)?)\s*(?:±\s*(?P<ci>\d+(?:\.\d+)?)\s*)?%")


def parse_value(value: str) -> dict:
    m = VALUE_RX.search(value)
    if not m:
        return {"point": None, "ci": None, "raw": value}
    return {"point": float(m.group("point")),
            "ci": float(m.group("ci")) if m.group("ci") else None,
            "raw": value}


def compare_results(expected: list[dict], measured: list[dict]) -> dict:
    """Match by metric name; report deltas and within-CI flags only."""
    measured_by_metric = {}
    for m in measured:
        measured_by_metric[m["metric"]] = m

    rows, missing = [], []
    for exp in expected:
        got = measured_by_metric.get(exp["metric"])
        if got is None:
            missing.append(exp["metric"])
            continue
        e, g = parse_value(exp["value"]), parse_value(str(got.get("value")))
        if e["point"] is None or g["point"] is None:
            rows.append({"metric": exp["metric"], "paper": exp["value"],
                         "measured": got.get("value"), "delta": None,
                         "within_paper_ci": None})
            continue
        delta = g["point"] - e["point"]
        if e["ci"] is not None and g.get("episodes_evaluated"):
            # A measured value has its own sampling noise; a conservative
            # comparison uses the paper's CI as the tolerance band.
            within = abs(delta) <= e["ci"]
        elif e["ci"] is not None:
            within = abs(delta) <= e["ci"]
        else:
            within = None  # no CI reported — human judgment required
        rows.append({"metric": exp["metric"], "paper": exp["value"],
                     "measured": got.get("value"),
                     "delta_pp": round(delta, 2),
                     "within_paper_ci": within})
    return {"rows": rows, "missing_metrics": missing,
            "note": "Deltas and CI flags are mechanical observations. They are "
                    "not a judgment; the verdict belongs to the human-signed "
                    "verdict field."}


def build_run_record_skeleton(case_dir: str | Path, measured: list[dict],
                               what_was_run: dict | None = None,
                               environment_used: dict | None = None) -> dict:
    """Assemble the RunRecord payload for a student's run (verdict null)."""
    case_dir = Path(case_dir)
    expected = json.loads((case_dir / "expected_results.json").read_text())
    case_meta = json.loads((case_dir / "case.json").read_text()) \
        if (case_dir / "case.json").exists() else {}
    comparison = compare_results(expected["results"], measured)
    return {
        "paper_id": expected["paper"]["id"],
        "case": case_meta.get("paper", {}).get("id"),
        "what_was_run": what_was_run or {},
        "environment_actually_used": environment_used or {},
        "outputs": {"measured": measured},
        "comparison": comparison,
        "human_verdict": {
            "verdict": None,
            "notes": None,
            "professor_identity": None,
            "signed_at": None,
        },
    }
