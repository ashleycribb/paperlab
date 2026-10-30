"""PaperLab hard rules, enforced in code.

The AI only checks whether things exist. People make the judgments.
No PaperLab output may assert that a paper "reproduces", "is correct",
or "is valid" — those verdicts belong exclusively to a signed human field
on the reproduction run record.
"""

from __future__ import annotations

import re

# Phrases that constitute an AI verdict claim. Case-insensitive, word-boundary
# matched. Kept deliberately narrow to avoid false positives on prose that
# *discusses* the rule (e.g. quoting the rules themselves).
VERDICT_PHRASES = [
    r"the paper reproduces",
    r"the results reproduce",
    r"the experiment reproduces",
    r"successfully reproduced",
    r"reproduction succeeded",
    r"the paper is correct",
    r"the results are correct",
    r"the paper is valid",
    r"the results are valid",
    r"the method is valid",
    r"validates the paper",
    r"confirms the paper",
    r"the paper holds up",
    r"the paper holds",
]

# Matches context that quotes the rules rather than asserting a verdict
# (e.g. 'the AI must not say the paper "reproduces"').
QUOTED_CONTEXT = re.compile(r"[\"'\u201c(]")

# A match preceded by one of these anywhere earlier in the same clause is
# discussing or negating the rule, not asserting a verdict.
NEGATION_BEFORE = re.compile(
    r"\b(must not|may not|never|not|no|cannot|whether|if)\b", re.IGNORECASE)

_COMPILED = [(p, re.compile(p, re.IGNORECASE)) for p in VERDICT_PHRASES]


class VerdictClaimError(RuntimeError):
    """Raised when an output text contains an AI verdict claim."""


def _match_tolerated(line: str, match_start: int) -> bool:
    prefix = line[:match_start]
    if QUOTED_CONTEXT.search(prefix[-2:]):
        return True
    return bool(NEGATION_BEFORE.search(prefix))


def scan_for_verdict_claims(text: str) -> list[str]:
    """Return the list of verdict phrases found in ``text``.

    Lines that merely quote, negate, or question the rule (e.g. 'the AI must
    not say the paper "reproduces"', 'NOT a statement that the paper
    reproduces') are tolerated.
    """
    findings: list[str] = []
    for line in text.splitlines():
        for phrase, rx in _COMPILED:
            m = rx.search(line)
            if m and not _match_tolerated(line, m.start()):
                findings.append(phrase)
    return findings


def guard_output(text: str, source: str = "output") -> str:
    """Validate a PaperLab output before it is written or emitted.

    Raises :class:`VerdictClaimError` listing any verdict claims found.
    """
    findings = scan_for_verdict_claims(text)
    if findings:
        raise VerdictClaimError(
            f"{source} contains AI verdict claims (forbidden by PaperLab hard rules): "
            + "; ".join(sorted(set(findings)))
            + ". Verdicts belong only to the human-signed verdict field."
        )
    return text


# Provenance vocabulary for environment items and steps.
PROVENANCE_STATED_IN_PAPER = "stated_in_paper"
PROVENANCE_STATED_IN_REPO = "stated_in_repo"
PROVENANCE_INFERRED = "inferred"
PROVENANCE_NOT_STATED = "not_stated"

# Items with these provenance values require human confirmation.
NEEDS_HUMAN_PROVENANCE = {
    PROVENANCE_STATED_IN_REPO,
    PROVENANCE_INFERRED,
    PROVENANCE_NOT_STATED,
}
