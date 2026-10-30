"""Run-capture harness: record what was actually run, in what environment.

Wraps the student's commands and produces the ``run.json`` that
``paperlab diff`` consumes:

- what_was_run: each command, exit code, start/end timestamps, log paths
  and content hashes (logs stored under run_logs/, tails embedded)
- environment_actually_used: OS, CPU, RAM, GPU, Python, pip freeze,
  git HEAD of the working directory
- dataset hashes: SHA-256 of files under --hash-dir directories
- results: taken from --results-file (JSON list of {metric, value}) or
  left empty for the student to fill

Hard rules honored:
- Records, never judges: the snapshot is purely descriptive. It never
  compares the actual environment against environment.yaml, never marks
  an environment correct/incorrect or expected/unexpected, and reads no
  case files other than where to write. Evaluation is the professor's.
- No secrets: environment variables are never captured, and log text is
  scanned and redacted for credential patterns before it is written.
- No verdicts: the output is guarded by paperlab.rules.guard_output.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .rules import guard_object

# ---------------------------------------------------------------------------
# Secret redaction (defense in depth: env vars are not captured at all)
# ---------------------------------------------------------------------------

SECRET_RX = re.compile(
    r"(?i)\b(api[_-]?key|apikey|secret|access[_-]?token|auth|password|passwd|"
    r"authorization|credential)s?\b\s*[=:]\s*([^\s\"']+)")

# Long high-entropy tokens that look like keys (AWS-style, JWTs, hex/b64 blobs)
_BLOB_RX = re.compile(r"\b(AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9._-]{20,}|[a-f0-9]{32,})\b")


def redact_secrets(text: str) -> str:
    text = SECRET_RX.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    return _BLOB_RX.sub("[REDACTED]", text)


# ---------------------------------------------------------------------------
# Environment snapshots
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_os() -> dict:
    info = {"kernel": platform.release(), "machine": platform.machine()}
    osr = Path("/etc/os-release")
    if osr.exists():
        for line in osr.read_text().splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                if k in ("NAME", "VERSION_ID", "ID"):
                    info[f"os_{k.lower()}"] = v.strip('"')
    if not any(k.startswith("os_") for k in info):
        info["os_name"] = platform.system()
    return info


def snapshot_hardware() -> dict:
    hw: dict = {}
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                hw["cpu"] = line.split(":", 1)[1].strip()
                break
    hw["cpu_count"] = __import__("os").cpu_count()
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal"):
                hw["ram_total_kb"] = int(line.split()[1])
                break
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=15, check=True)
        gpus = [g.strip() for g in out.stdout.strip().splitlines() if g.strip()]
        hw["gpus"] = gpus
    except Exception:  # noqa: BLE001 — no GPU, no nvidia-smi, or timeout
        hw["gpus"] = []
    return hw


def snapshot_python() -> dict:
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "executable": sys.executable,
    }


def snapshot_packages() -> dict:
    """pip freeze of the running interpreter. Falls back to importlib.metadata."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True, text=True, timeout=120, check=True)
        return {"pip_freeze": sorted(out.stdout.strip().splitlines())}
    except Exception:  # noqa: BLE001
        from importlib.metadata import distributions
        return {"packages": sorted(
            f"{d.metadata['Name']}=={d.version}" for d in distributions()
            if d.metadata["Name"])}


def snapshot_git(cwd: Path) -> dict:
    """HEAD of the directory the commands run in, so the code is pinned."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd,
                              capture_output=True, text=True, timeout=15, check=True)
        return {"git_head": head.stdout.strip()}
    except Exception:  # noqa: BLE001 — not a git checkout
        return {"git_head": None}


def snapshot_dirs(dirs: list[Path]) -> dict:
    """SHA-256 every file under the given directories (dataset pinning)."""
    out: dict = {}
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            out[str(d)] = {"error": "not a directory"}
            continue
        entries = {}
        for p in sorted(d.rglob("*")):
            if p.is_file():
                entries[str(p.relative_to(d))] = {
                    "sha256": sha256_file(p), "bytes": p.stat().st_size}
        out[str(d)] = {"files": entries,
                       "total_files": len(entries)}
    return out


# ---------------------------------------------------------------------------
# Command capture
# ---------------------------------------------------------------------------

def _slug(cmd: list[str]) -> str:
    base = Path(cmd[0] if cmd else "cmd").name
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", base)[:40] or "cmd"


def run_command(cmd: list[str], cwd: Path, logs_dir: Path, seq: int,
                stop_on_failure: bool = True) -> dict:
    """Run one command under capture; write logs; return the record."""
    slug = _slug(cmd)
    started = _utc_now()
    t0 = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    duration = round(time.monotonic() - t0, 3)
    finished = _utc_now()

    logs_dir.mkdir(parents=True, exist_ok=True)
    out_path = logs_dir / f"{seq:02d}_{slug}.out"
    err_path = logs_dir / f"{seq:02d}_{slug}.err"
    stdout = redact_secrets(proc.stdout or "")
    stderr = redact_secrets(proc.stderr or "")
    out_path.write_text(stdout)
    err_path.write_text(stderr)

    record = {
        "command": cmd,
        "cwd": str(cwd),
        "exit_code": proc.returncode,
        "started_at": started,
        "finished_at": finished,
        "duration_sec": duration,
        "logs": {
            "stdout": {"path": str(out_path), "sha256": hashlib.sha256(
                stdout.encode()).hexdigest(), "bytes": len(stdout.encode())},
            "stderr": {"path": str(err_path), "sha256": hashlib.sha256(
                stderr.encode()).hexdigest(), "bytes": len(stderr.encode())},
        },
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
    }
    if proc.returncode != 0 and stop_on_failure:
        record["note"] = ("command failed and --stop-on-failure is active "
                          "(default); later commands were not run")
    return record


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------

def capture_run(case_dir: Path, commands: list[list[str]], *,
                cwd: Path | None = None,
                results: list[dict] | None = None,
                hash_dirs: list[Path] | None = None,
                stop_on_failure: bool = True) -> dict:
    """Run commands under capture and assemble run.json contents."""
    case_dir = Path(case_dir)
    cwd = Path(cwd) if cwd else Path.cwd()
    logs_dir = case_dir / "run_logs"

    environment_used = {}
    environment_used.update(snapshot_os())
    environment_used.update(snapshot_hardware())
    environment_used.update(snapshot_python())
    environment_used.update(snapshot_packages())
    environment_used.update(snapshot_git(cwd))
    if hash_dirs:
        environment_used["dataset_hashes"] = snapshot_dirs(hash_dirs)

    what_ran = []
    for i, cmd in enumerate(commands):
        rec = run_command(cmd, cwd, logs_dir, i + 1, stop_on_failure)
        what_ran.append(rec)
        if rec["exit_code"] != 0 and stop_on_failure:
            break

    run = {
        "captured_at": _utc_now(),
        "captured_by": "paperlab capture (automated harness)",
        "what_was_run": {
            "commands": what_ran,
            "stop_on_failure": stop_on_failure,
        },
        "environment_actually_used": environment_used,
        "results": results or [],
    }
    return run


def write_run_file(path: Path, run: dict) -> None:
    """Write run.json only if it passes the verdict guard."""
    guard_object(run, source=str(path))
    path.write_text(json.dumps(run, indent=2))
