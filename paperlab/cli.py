"""PaperLab CLI.

Commands:
  init       scaffold a new case directory for a paper
  fetch-pdf  download a case's paper PDF into the case directory
  check      run the machine-readable existence checklist (network)
  verify     verify expected_results.json against the paper (cached text or PDF)
  diff       compare a run's measured results against expected (deltas only)
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from . import checks, compare, records, verify
from .rules import guard_output, VerdictClaimError

CASE_TEMPLATE = {
    "case.json": {
        "paper": {
            "id": "arXiv:XXXX.XXXXX",
            "title": "TITLE",
            "url": "https://arxiv.org/abs/XXXX.XXXXX",
            "pdf_url": "https://arxiv.org/pdf/XXXX.XXXXX",
        },
        "scope": "DESCRIBE WHAT IS IN SCOPE FOR THIS CASE",
    },
    "environment.yaml": "# PaperLab environment record\n# Every item: provenance stated_in_paper (quote + page) / stated_in_repo /\n# inferred / not_stated\n",
    "run_guide.md": "# Run Guide\n\nSteps marked [paper, p.N] (quoted), [repo] (evidence URL), or [inferred] (needs human confirmation).\n",
    "expected_results.json": {
        "paper": {"id": "arXiv:XXXX.XXXXX", "title": "TITLE",
                  "url": "https://arxiv.org/abs/XXXX.XXXXX"},
        "results": [],
    },
    "checklist.json": {"checks": []},
    "run.json.example": {"results": [{"metric": "EXAMPLE METRIC", "value": "00.0%"}]},
}


def _load_json(path: Path):
    return json.loads(path.read_text())


def cmd_init(args):
    case_dir = Path(args.case_dir)
    if case_dir.exists() and any(case_dir.iterdir()):
        sys.exit(f"refusing to initialize: {case_dir} is not empty")
    case_dir.mkdir(parents=True)
    (case_dir / "paper_text").mkdir()
    for name, content in CASE_TEMPLATE.items():
        target = case_dir / name
        if name.endswith(".json"):
            target.write_text(json.dumps(content, indent=2))
        else:
            target.write_text(content)
    print(f"initialized case at {case_dir}")
    print("next: fill case.json, extract results, write checklist.json, "
          "then run: paperlab fetch-pdf / check / verify")


def cmd_fetch_pdf(args):
    case_dir = Path(args.case_dir)
    case = _load_json(case_dir / "case.json")
    pdf_url = case["paper"]["pdf_url"]
    dest = case_dir / "paper.pdf"
    print(f"fetching {pdf_url}")
    req = urllib.request.Request(pdf_url, headers={"User-Agent": checks.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    print(f"saved {dest} ({dest.stat().st_size} bytes)")
    if args.extract:
        import subprocess
        subprocess.run(["pdftotext", str(dest), str(case_dir / "paper_text" / "all.txt")], check=True)
        print("extracted text to paper_text/all.txt")


def _case_pdf(case_dir: Path):
    pdf = case_dir / "paper.pdf"
    return pdf if pdf.exists() else None


def cmd_check(args):
    case_dir = Path(args.case_dir)
    checklist = _load_json(case_dir / "checklist.json")
    report = checks.run_checklist(case_dir, checklist, _case_pdf(case_dir))
    out = case_dir / "existence_checks.json"
    checks.write_report_guarded(out, report)
    s = report["summary"]
    print(f"checks: {s['passed']}/{s['total']} passed; report written to {out}")
    if args.strict and s["passed"] != s["total"]:
        sys.exit(1)


def cmd_verify(args):
    case_dir = Path(args.case_dir)
    result = verify.verify_case(case_dir, _case_pdf(case_dir))
    p, g = result["presence"], result["pairing"]
    print(f"presence: {p['passed']}/{p['total']} values found on cited pages")
    if p.get("fails"):
        for f in p["fails"]:
            print(f"  FAIL: {f.get('metric')} = {f.get('value')} (p.{f.get('page')}) {f.get('error', '')}")
    if "skipped" in g:
        print(f"pairing: skipped — {g['skipped']}")
    else:
        print(f"pairing: {g['passed']}/{g['total']} values at correct table positions")
        if g.get("fails"):
            for f in g["fails"]:
                print(f"  FAIL: {f}")
    out = case_dir / "verify_report.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"report written to {out}")
    if args.strict and (p["passed"] != p["total"] or g.get("fails")):
        sys.exit(1)


def cmd_diff(args):
    case_dir = Path(args.case_dir)
    run = _load_json(Path(args.run_file))
    measured = run.get("results", run.get("outputs", {}).get("measured", []))
    skeleton = compare.build_run_record_skeleton(
        case_dir, measured,
        what_was_run=run.get("what_was_run"),
        environment_used=run.get("environment_actually_used"),
    )
    # Guard the emitted record against verdict claims before writing.
    guard_output(json.dumps(skeleton, indent=2), source="run record")
    out = Path(args.out) if args.out else case_dir / "run_record.json"
    out.write_text(json.dumps(skeleton, indent=2))
    rows = skeleton["comparison"]["rows"]
    print(f"compared {len(rows)} metrics "
          f"({len(skeleton['comparison']['missing_metrics'])} missing from run)")
    for row in rows:
        flag = "" if row.get("within_paper_ci") is None else \
            (" [within CI]" if row["within_paper_ci"] else " [outside CI]")
        print(f"  {row['metric']}: paper={row['paper']} measured={row['measured']} "
              f"delta={row.get('delta_pp')}{flag}")
    print("verdict: UNSET — professor fills human_verdict and signs")


def cmd_records(args):
    """Convert a case's expected results into signed-versioned records."""
    case_dir = Path(args.case_dir)
    case = _load_json(case_dir / "case.json")
    expected = _load_json(case_dir / "expected_results.json")
    producer = records.Producer(id="paperlab-cli", kind="ai_agent")
    recs = [records.ExpectedResultRecord.build(
        case["paper"]["id"], r["metric"], r["value"], r["table_or_figure"],
        r["page"], r["quote"], producer) for r in expected["results"]]
    out = case_dir / "expected_result_records.jsonl"
    with open(out, "w") as f:
        for rec in recs:
            f.write(json.dumps(rec.to_dict()) + "\n")
    print(f"wrote {len(recs)} records to {out} (content hashes: "
          f"{recs[0].content_sha256[:12]}... first)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="paperlab", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="scaffold a new case directory")
    p.add_argument("case_dir")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("fetch-pdf", help="download the case's paper PDF")
    p.add_argument("case_dir")
    p.add_argument("--extract", action="store_true", help="also run pdftotext")
    p.set_defaults(fn=cmd_fetch_pdf)

    p = sub.add_parser("check", help="run existence checklist (network)")
    p.add_argument("case_dir")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("verify", help="verify expected results against the paper")
    p.add_argument("case_dir")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("diff", help="compare a run against expected results")
    p.add_argument("case_dir")
    p.add_argument("run_file")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_diff)

    p = sub.add_parser("records", help="emit versioned record objects")
    p.add_argument("case_dir")
    p.set_defaults(fn=cmd_records)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
    except VerdictClaimError as e:
        sys.exit(f"BLOCKED by hard rules: {e}")


if __name__ == "__main__":
    main()
