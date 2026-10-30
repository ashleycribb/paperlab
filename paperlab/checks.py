"""Existence checks: does the thing exist / resolve / appear on the cited page?

These checks NEVER judge correctness or reproduction — they only verify
existence, and every result carries an evidence URL.
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone

from .rules import guard_output

USER_AGENT = "PaperLab/0.1 (research existence checks)"
VALUE_RX = re.compile(r"\d+\.\d+\s*±\s*\d+\.\d+%|\d+\.\d+%")


def _http_status(url: str, timeout: int = 20) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def _get_json(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def check_url_resolves(url: str, expect: int = 200) -> dict:
    try:
        status = _http_status(url)
        return {"result": "pass" if status == expect else f"unexpected status {status}",
                "evidence_url": url}
    except Exception as e:  # noqa: BLE001 — any transport failure is a check failure
        return {"result": f"fail ({type(e).__name__})", "evidence_url": url,
                "detail": str(e)[:200]}


def check_pypi_package(package: str, version: str | None = None) -> dict:
    url = f"https://pypi.org/pypi/{package}/json" if version is None \
        else f"https://pypi.org/pypi/{package}/{version}/json"
    try:
        _get_json(url)
        return {"result": "pass", "evidence_url": url}
    except urllib.error.HTTPError as e:
        result = "pass (latest only)" if e.code == 404 and version is None else f"fail (HTTP {e.code})"
        return {"result": result, "evidence_url": url}
    except Exception as e:  # noqa: BLE001
        return {"result": f"fail ({type(e).__name__})", "evidence_url": url}


def load_page_text(case_dir, page: int, pdf_path=None) -> str:
    """Return the text of one PDF page, using cached page files or pdftotext."""
    cache = case_dir / "paper_text" / f"page{page:02d}.txt"
    if cache.exists():
        return cache.read_text()
    if pdf_path is None:
        raise FileNotFoundError(
            f"No cached text for page {page} and no PDF provided. "
            f"Run 'paperlab fetch-pdf' or place the PDF in the case directory."
        )
    import subprocess
    out = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
        capture_output=True, text=True, check=True)
    return out.stdout


def check_string_on_page(case_dir, page: int, needle: str, pdf_path=None) -> dict:
    text = load_page_text(case_dir, page, pdf_path)
    norm = re.sub(r"\s+", " ", text)
    found = re.sub(r"\s+", " ", needle) in norm
    return {"result": "pass" if found else "fail (string not found on page)",
            "evidence_url": f"page {page}"}


def check_value_on_page(case_dir, page: int, value: str, pdf_path=None) -> dict:
    text = load_page_text(case_dir, page, pdf_path)
    values = VALUE_RX.findall(text)
    return {"result": "pass" if value in values else "fail (value not on page)",
            "evidence_url": f"page {page}"}


def run_checklist(case_dir, checklist: dict, pdf_path=None) -> dict:
    """Run a machine-readable checklist and produce a report.

    Checklist entry kinds:
      - {"kind": "url", "item": ..., "url": ...}
      - {"kind": "pypi", "item": ..., "package": ..., "version": ...?}
      - {"kind": "quote_on_page", "item": ..., "page": ..., "needle": ...}
      - {"kind": "value_on_page", "item": ..., "page": ..., "value": ...}
    """
    from pathlib import Path
    case_dir = Path(case_dir)
    report = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checked_by": "PaperLab CLI (automated existence checks)",
        "rules": "Existence checks only. A pass means an item exists or appears "
                 "on the cited page. It is NOT a statement that the paper "
                 "reproduces, is correct, or is valid.",
        "checks": [],
    }
    for entry in checklist.get("checks", []):
        kind = entry.get("kind")
        if kind == "url":
            out = check_url_resolves(entry["url"])
        elif kind == "pypi":
            out = check_pypi_package(entry["package"], entry.get("version"))
        elif kind == "quote_on_page":
            out = check_string_on_page(case_dir, entry["page"], entry["needle"], pdf_path)
        elif kind == "value_on_page":
            out = check_value_on_page(case_dir, entry["page"], entry["value"], pdf_path)
        elif kind == "absent_from_pdf":
            # Used for 'not stated in paper' checks: the needle must NOT
            # appear anywhere in the cached page text.
            needles = entry.get("needles", [entry.get("needle")])
            hits = []
            for pg in entry.get("pages", range(1, 14)):
                try:
                    text = load_page_text(case_dir, pg, pdf_path)
                except FileNotFoundError:
                    continue
                for needle in needles:
                    if needle.lower() in text.lower():
                        hits.append(f"p{pg}: {needle}")
            out = {"result": "fail (found: " + "; ".join(hits) + ")" if hits else "pass",
                   "evidence_url": f"pages {entry.get('pages', '1-13')}"}
        else:
            out = {"result": f"fail (unknown kind {kind})", "evidence_url": ""}
        report["checks"].append({
            "item": entry.get("item", entry.get("url", "")),
            "check": entry.get("check", kind or ""),
            "result": out["result"],
            "evidence_url": out["evidence_url"],
            **({"detail": out["detail"]} if "detail" in out else {}),
        })
    passes = sum(1 for c in report["checks"] if c["result"].startswith("pass"))
    report["summary"] = {"total": len(report["checks"]), "passed": passes}
    # Preserve the case's needs-a-human queue: the human decision backlog
    # that no automated check can close.
    nah = case_dir / "needs_a_human.json"
    if nah.exists():
        report["needs_a_human"] = json.loads(nah.read_text())
    return report


def write_report_guarded(path, report) -> None:
    """Write a report only if it contains no AI verdict claims."""
    guard_output(json.dumps(report, indent=2), source=str(path))
    path.write_text(json.dumps(report, indent=2))
