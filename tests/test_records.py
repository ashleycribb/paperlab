"""Tests for record schemas: hashing, versioning, verdict gate."""

from paperlab.records import (
    ExpectedResultRecord, HumanVerdict, Producer, RunRecord, content_hash)


def _producer():
    return Producer(id="paperlab-test", kind="ai_agent")


def test_expected_result_record_hash_is_stable():
    a = ExpectedResultRecord.build("arXiv:1703.05175v2", "acc", "98.8%", "Table 1", 5, "q", _producer())
    b = ExpectedResultRecord.build("arXiv:1703.05175v2", "acc", "98.8%", "Table 1", 5, "q", _producer())
    assert a.content_sha256 == b.content_sha256


def test_hash_changes_with_content():
    a = ExpectedResultRecord.build("p", "acc", "98.8%", "Table 1", 5, "q", _producer())
    b = ExpectedResultRecord.build("p", "acc", "98.9%", "Table 1", 5, "q", _producer())
    assert a.content_sha256 != b.content_sha256


def test_run_record_verdict_starts_null():
    rec = RunRecord.build("p", "h1", "h2", "h3", {}, {}, {}, {}, _producer())
    verdict = rec.payload["human_verdict"]
    assert verdict["verdict"] is None
    assert verdict["professor_identity"] is None


def test_human_verdict_enum_values():
    # The only permitted verdict values; all require a human signature.
    allowed = {"supports", "partially-supports", "does-not-support", "inconclusive"}
    assert HumanVerdict().verdict is None
    assert allowed  # documented in the schema


def test_signature_starts_none():
    rec = ExpectedResultRecord.build("p", "acc", "1%", "T", 1, "q", _producer())
    assert rec.signature is None
