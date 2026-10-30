"""PaperLab record schemas.

Maps onto the S3A Scholar pack primitives (crates/s3a-pack-scholar):
- quote_sha256 + passage_page anchoring (ScholarNoteClaimRecord)
- producer / verification-statement UUIDs (dual-trace provenance)
- Ed25519 signing via s3a-vault-style identities (s3a-vault)
- Merkle-sealed version history via s3a-vcs (content hash + version bump)

Every record is content-addressed (SHA-256 of canonical JSON), versioned,
and signable. The AI producer signs what it produced; humans sign
confirmations and the verdict. No record type exposes an AI-fillable
"reproduces" field — the only verdict field lives on RunRecord and
requires a human signature.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Producer:
    id: str                      # agent id or human vault identity
    kind: str                    # "ai_agent" | "human"


@dataclass
class BaseRecord:
    record_type: str
    producer: Optional[Producer] = None
    created_at: str = field(default_factory=utc_now_iso)
    version: int = 1
    payload: dict = field(default_factory=dict)
    # Ed25519 detached signature over canonical_json(record minus signature).
    # None until signed; signing is a separate, auditable action.
    signature: Optional[str] = None
    previous_version_hash: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def content_sha256(self) -> str:
        d = self.to_dict()
        d.pop("signature", None)
        return content_hash(d)


@dataclass
class EnvironmentRecord(BaseRecord):
    """environment.yaml as a record: items[] with provenance + quote anchors."""
    record_type: str = "paperlab.environment"

    @staticmethod
    def build(paper_id: str, items: list[dict], producer: Producer) -> "EnvironmentRecord":
        return EnvironmentRecord(
            producer=producer,
            payload={"paper_id": paper_id, "items": items},
        )


@dataclass
class RunStepRecord(BaseRecord):
    """One numbered run-guide step, anchored to methods text."""
    record_type: str = "paperlab.run_step"

    @staticmethod
    def build(paper_id: str, step_no: int, text: str, quote: str, page: int,
              command: Optional[str] = None, evidence_url: Optional[str] = None,
              provenance: str = "stated_in_paper", producer: Producer = None) -> "RunStepRecord":
        return RunStepRecord(
            producer=producer,
            payload={
                "paper_id": paper_id, "step_no": step_no, "text": text,
                "quote": quote, "passage_page": page, "command": command,
                "evidence_url": evidence_url, "provenance": provenance,
            },
        )


@dataclass
class ExpectedResultRecord(BaseRecord):
    """One reported result: {metric, value, table_or_figure, page, quote}."""
    record_type: str = "paperlab.expected_result"

    @staticmethod
    def build(paper_id: str, metric: str, value: str, table_or_figure: str,
              page: int, quote: str, producer: Producer = None) -> "ExpectedResultRecord":
        return ExpectedResultRecord(
            producer=producer,
            payload={
                "paper_id": paper_id, "metric": metric, "value": value,
                "table_or_figure": table_or_figure, "passage_page": page, "quote": quote,
            },
        )


@dataclass
class CheckRecord(BaseRecord):
    """One automated existence check with evidence URL and result."""
    record_type: str = "paperlab.check"

    @staticmethod
    def build(item: str, check: str, result: str, evidence_url: str,
              checked_at: str, producer: Producer = None) -> "CheckRecord":
        return CheckRecord(
            producer=producer,
            payload={"item": item, "check": check, "result": result,
                     "evidence_url": evidence_url, "checked_at": checked_at},
        )


@dataclass
class HumanVerdict:
    """The ONLY verdict field in PaperLab. Null until the professor signs."""
    verdict: Optional[str] = None   # supports | partially-supports | does-not-support | inconclusive
    notes: Optional[str] = None
    professor_identity: Optional[str] = None
    signed_at: Optional[str] = None


@dataclass
class RunRecord(BaseRecord):
    """What happened when a student actually ran the experiment."""
    record_type: str = "paperlab.run"

    @staticmethod
    def build(paper_id: str, environment_record_hash: str,
              expected_results_hash: str, run_guide_hash: str,
              what_was_run: dict, environment_used: dict,
              outputs: dict, comparison: dict,
              producer: Producer = None) -> "RunRecord":
        return RunRecord(
            producer=producer,
            payload={
                "paper_id": paper_id,
                "environment_record": environment_record_hash,
                "expected_results_record": expected_results_hash,
                "run_guide_record": run_guide_hash,
                "what_was_run": what_was_run,
                "environment_actually_used": environment_used,
                "outputs": outputs,
                "comparison": comparison,     # deltas only — never a judgment
                "human_verdict": asdict(HumanVerdict()),
            },
        )


def sign_record(record: BaseRecord, private_key_pem: str) -> str:
    """Ed25519-sign a record. Returns base64 signature; requires `cryptography`.

    Signing is optional at the prototype stage: records without signatures are
    'unsigned drafts'; the verdict gate refuses to close without one.
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import base64
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Ed25519 signing requires the 'cryptography' package (Apache-2.0/BSD-3). "
            "Install paperlab[signing] or treat this record as an unsigned draft."
        ) from e
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, Ed25519PrivateKey):  # pragma: no cover
        raise ValueError("Not an Ed25519 private key")
    d = record.to_dict()
    d.pop("signature", None)
    sig = key.sign(canonical_json(d).encode("utf-8"))
    record.signature = base64.b64encode(sig).decode()
    return record.signature
