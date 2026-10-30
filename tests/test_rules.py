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


def test_guard_object_catches_json_string_hole():
    # Regression: a verdict claim as the first words of a JSON string value
    # is invisible to a serialized-text scan (the opening quote reads as
    # quoted context) but must be caught by the object-level guard.
    from paperlab.rules import guard_object
    obj = {"results": [{"metric": "m", "value": "1%"}],
           "note": "The experiment reproduces the paper."}
    with pytest.raises(VerdictClaimError):
        guard_object(obj)


def test_guard_object_passes_clean_nested():
    from paperlab.rules import guard_object
    obj = {"a": ["clean", {"b": "also clean"}], "c": 1}
    guard_object(obj)  # does not raise
