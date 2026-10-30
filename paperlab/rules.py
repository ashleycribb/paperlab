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

# Verb-level claims: any "<subject> reproduces/reproduce" is a verdict claim
# regardless of subject wording ("this run reproduces it", "our code
# reproduces Table 1"). Past-tense 'reproduced' is adjective-safe ("the
# reproduced results"), so only first-person subjects are matched there.
VERB_CLAIM_PATTERNS = [
    r"\b\w+\s+reproduces\b",
    r"\b\w+\s+reproduce\b",
    r"\b(?:we|i|they)\s+reproduced\b",
]

# Matches context that quotes the rules rather than asserting a verdict
# (e.g. 'the AI must not say the paper "reproduces"').
QUOTED_CONTEXT = re.compile(r"[\"'\u201c(]")

# A match preceded by one of these anywhere earlier in the same clause is
# discussing or negating the rule, not asserting a verdict.
NEGATION_BEFORE = re.compile(
    r"\b(must not|may not|never|not|no|cannot|whether|if)\b", re.IGNORECASE)

# Non-assertive contexts: ease/attempt/modality wording before the verb
# ("easy to reproduce", "aiming to reproduce") is not a claim.
NON_ASSERTIVE_BEFORE = re.compile(
    r"\b(easy|easier|hard|harder|difficult|impossible|simple|try|tries|trying|"
    r"tried|attempt|attempts|attempting|aim|aims|aiming|hope|hopes|hoping|"
    r"meant|designed|help|helps|helping|allow|allows|enables?|need|needs|"
    r"needed|able|unable|how|what|whether)\b", re.IGNORECASE)

_COMPILED = [(p, re.compile(p, re.IGNORECASE)) for p in VERDICT_PHRASES]
_COMPILED_VERBS = [(p, re.compile(p, re.IGNORECASE)) for p in VERB_CLAIM_PATTERNS]


class VerdictClaimError(RuntimeError):
    """Raised when an output text contains an AI verdict claim."""


def _match_tolerated(line: str, match_start: int) -> bool:
    prefix = line[:match_start]
    if QUOTED_CONTEXT.search(prefix[-2:]):
        return True
    if NEGATION_BEFORE.search(prefix):
        return True
    return bool(NON_ASSERTIVE_BEFORE.search(prefix))


def scan_for_verdict_claims(text: str) -> list[str]:
    """Return the list of verdict phrases found in ``text``.

    Tolerated: lines that quote, negate, question, or modalize the claim
    ('the AI must not say the paper "reproduces"', 'NOT a statement that
    the paper reproduces', 'whether the run reproduces', 'easy to
    reproduce'). A negation AFTER the match does NOT tolerate anything:
    'this run reproduces it, not partially' is a verdict claim with
    clever wording and is flagged.
    """
    findings: list[str] = []
    for line in text.splitlines():
        for phrase, rx in _COMPILED:
            m = rx.search(line)
            if m and not _match_tolerated(line, m.start()):
                findings.append(phrase)
        for phrase, rx in _COMPILED_VERBS:
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


def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)


def guard_object(obj, source: str = "output") -> object:
    """Guard a structured object (dict/list) before serialization.

    Scans every string value as prose. This avoids the JSON-quoting hole:
    a verdict claim as the first words of a JSON string value is invisible
    to a serialized-text scan (the string's opening quote reads as a
    'quoted context'), but is caught here.
    """
    for s in _iter_strings(obj):
        findings = scan_for_verdict_claims(s)
        if findings:
            raise VerdictClaimError(
                f"{source} contains AI verdict claims (forbidden by PaperLab hard rules): "
                + "; ".join(sorted(set(findings)))
                + f" (in string: {s[:120]!r})"
                + ". Verdicts belong only to the human-signed verdict field."
            )
    return obj


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
