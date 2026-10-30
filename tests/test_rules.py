"""Tests for the hard-rules guard."""

import pytest

from paperlab.rules import guard_output, scan_for_verdict_claims, VerdictClaimError


def test_blocks_direct_verdict_claims():
    text = "The experiment reproduces the paper's Table 1 results."
    assert scan_for_verdict_claims(text) == ["the experiment reproduces"]
    with pytest.raises(VerdictClaimError):
        guard_output(text)


def test_blocks_validity_claims():
    for text in [
        "The paper is correct.",
        "Our run validates the paper.",
        "The results are valid.",
    ]:
        with pytest.raises(VerdictClaimError):
            guard_output(text)


def test_allows_discussion_of_the_rule():
    text = ('The AI must not say the paper "reproduces" or "is correct"; '
            'the professor makes the final call.')
    assert scan_for_verdict_claims(text) == []
    guard_output(text)  # does not raise


def test_allows_neutral_reporting():
    text = ("Comparison: paper=98.8% measured=98.6% delta=-0.2. "
            "Verdict: UNSET — professor fills human_verdict.")
    assert scan_for_verdict_claims(text) == []
    guard_output(text)  # does not raise


def test_tolerates_negation_context():
    text = ("It is NOT a statement that the paper reproduces, is correct, or is valid. "
            "Those judgments belong to humans.")
    assert scan_for_verdict_claims(text) == []
    guard_output(text)  # does not raise
