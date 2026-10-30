"""Tests for the run-capture harness."""

import json
import subprocess
import sys
from pathlib import Path

from paperlab.capture import (
    capture_run, redact_secrets, sha256_file, snapshot_git, snapshot_os)


def test_redact_secrets_kv_patterns():
    text = "API_KEY=abc123123123123123123123 and password: hunter2secure"
    out = redact_secrets(text)
    assert "abc123" not in out
    assert "hunter2secure" not in out
    assert "[REDACTED]" in out


def test_redact_secrets_blob_patterns():
    out = redact_secrets("token AKIAIOSFODNN7EXAMPLE and jwt eyJhbGciOiJIUzI1NiJ9.x.y")
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "eyJhbGciOiJIUzI1NiJ9" not in out


def test_redact_leaves_normal_logs():
    text = "epoch 12 loss 0.421 acc 0.9821 CUDA_VISIBLE_DEVICES=0"
    assert redact_secrets(text) == text


def test_snapshot_os_has_fields():
    s = snapshot_os()
    assert "machine" in s and "kernel" in s


def test_snapshot_git(tmp_path):
    # A plain directory is not a git checkout: head is None, no crash.
    assert snapshot_git(tmp_path)["git_head"] is None


def test_capture_run_end_to_end(tmp_path):
    # Minimal case files so the diff skeleton can be built from this dir.
    (tmp_path / "expected_results.json").write_text(json.dumps(
        {"paper": {"id": "test"}, "results": [
            {"metric": "demo", "value": "98.8%", "table_or_figure": "T",
             "page": 1, "quote": "q"}]}))
    (tmp_path / "case.json").write_text(json.dumps(
        {"paper": {"id": "test"}}))
    run = capture_run(
        tmp_path,
        [[sys.executable, "-c", "print('acc=0.988')"]],
        cwd=tmp_path,
        results=[{"metric": "demo", "value": "98.8%"}],
        stop_on_failure=True,
    )
    cmd = run["what_was_run"]["commands"][0]
    assert cmd["exit_code"] == 0
    assert cmd["duration_sec"] >= 0
    assert "acc=0.988" in cmd["stdout_tail"]
    assert cmd["logs"]["stdout"]["sha256"]
    log_files = list((tmp_path / "run_logs").glob("*.out"))
    assert log_files, "logs were written to run_logs/"
    assert run["environment_actually_used"]["python"]
    assert isinstance(run["environment_actually_used"].get("pip_freeze", None), list)
    assert run["results"] == [{"metric": "demo", "value": "98.8%"}]
    # Diff compatibility: diff reads what_was_run/commands (list) and results.
    from paperlab.compare import build_run_record_skeleton
    skeleton = build_run_record_skeleton(
        tmp_path, run["results"],
        what_was_run={"commands": [c["command"] for c in run["what_was_run"]["commands"]]},
        environment_used=run["environment_actually_used"])
    assert skeleton["human_verdict"]["verdict"] is None


def test_capture_stops_on_failure(tmp_path):
    run = capture_run(
        tmp_path,
        [[sys.executable, "-c", "import sys; sys.exit(3)"],
         [sys.executable, "-c", "print('should not run')"]],
        cwd=tmp_path, stop_on_failure=True)
    cmds = run["what_was_run"]["commands"]
    assert len(cmds) == 1 and cmds[0]["exit_code"] == 3
    assert cmds[0]["note"]


def test_capture_no_stop_records_all(tmp_path):
    run = capture_run(
        tmp_path,
        [[sys.executable, "-c", "import sys; sys.exit(3)"],
         [sys.executable, "-c", "print('ran anyway')"]],
        cwd=tmp_path, stop_on_failure=False)
    assert len(run["what_was_run"]["commands"]) == 2


def test_write_run_file_guards_verdict(tmp_path):
    from paperlab.capture import write_run_file
    from paperlab.rules import VerdictClaimError
    import pytest
    with pytest.raises(VerdictClaimError):
        write_run_file(tmp_path / "run.json",
                       {"results": [{"metric": "m", "value": "1%"}],
                        "note": "The experiment reproduces the paper."})
    assert not (tmp_path / "run.json").exists()


def test_secrets_never_captured(tmp_path):
    # Env vars must not appear anywhere in the run file.
    import os
    os.environ["PAPERLAB_TEST_SECRET"] = "supersecret123"
    try:
        run = capture_run(tmp_path, [[sys.executable, "-c", "print('ok')"]],
                          cwd=tmp_path)
    finally:
        del os.environ["PAPERLAB_TEST_SECRET"]
    blob = json.dumps(run)
    assert "PAPERLAB_TEST_SECRET" not in blob
    assert "supersecret123" not in blob


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_keys(v)


def test_capture_is_purely_descriptive(tmp_path):
    # The harness records what was actually run. It must not judge the
    # environment: no evaluative keys, no comparison against
    # environment.yaml, no pass/fail of the environment itself.
    run = capture_run(tmp_path, [[sys.executable, "-c", "print('x')"]], cwd=tmp_path)
    judgment_keys = {
        "correct", "incorrect", "expected", "unexpected", "matches",
        "mismatch", "verdict", "judgment", "judgement", "evaluation",
        "valid", "invalid", "approved", "rejected", "score", "pass",
        "fail", "ok", "good", "bad", "assessment", "comparison",
    }
    bad = [k for k in _walk_keys(run) if k.lower() in judgment_keys]
    assert bad == [], f"capture emitted judgment keys: {bad}"
    # Exit codes and notes are observations, not environment verdicts.
    assert run["what_was_run"]["commands"][0]["exit_code"] == 0


def test_capture_ignores_environment_yaml(tmp_path):
    # The harness must not read the case's environment.yaml (that would
    # invite comparison); its input is only the command and the machine.
    (tmp_path / "environment.yaml").write_text("software: [{name: torch}]\n")
    before = (tmp_path / "environment.yaml").read_text()
    run = capture_run(tmp_path, [[sys.executable, "-c", "print('y')"]], cwd=tmp_path)
    assert (tmp_path / "environment.yaml").read_text() == before
    blob = json.dumps(run)
    assert "environment.yaml" not in blob
    assert "torch" not in blob
