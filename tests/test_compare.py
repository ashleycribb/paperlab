"""Tests for the comparison engine (deltas only, never a verdict)."""

from paperlab.compare import compare_results, parse_value


def test_parse_value_with_ci():
    v = parse_value("49.42 ± 0.78%")
    assert v["point"] == 49.42
    assert v["ci"] == 0.78


def test_parse_value_plain():
    v = parse_value("98.8%")
    assert v["point"] == 98.8
    assert v["ci"] is None


def test_compare_within_ci():
    expected = [{"metric": "5-way 1-shot", "value": "98.8%"}]
    measured = [{"metric": "5-way 1-shot", "value": "98.6%"}]
    out = compare_results(expected, measured)
    row = out["rows"][0]
    assert row["delta_pp"] == -0.2
    assert row["within_paper_ci"] is None  # no CI reported -> human judgment


def test_compare_with_ci_band():
    expected = [{"metric": "mini 1-shot", "value": "49.42 ± 0.78%"}]
    measured = [{"metric": "mini 1-shot", "value": "49.9%"}]
    row = compare_results(expected, measured)["rows"][0]
    assert row["delta_pp"] == 0.48
    assert row["within_paper_ci"] is True


def test_compare_outside_ci_band():
    expected = [{"metric": "mini 1-shot", "value": "49.42 ± 0.78%"}]
    measured = [{"metric": "mini 1-shot", "value": "44.0%"}]
    row = compare_results(expected, measured)["rows"][0]
    assert row["within_paper_ci"] is False


def test_missing_metric_reported():
    out = compare_results([{"metric": "A", "value": "1.0%"}], [{"metric": "B", "value": "2.0%"}])
    assert out["missing_metrics"] == ["A"]
    assert out["rows"] == []


def test_no_verdict_language_in_output():
    expected = [{"metric": "A", "value": "1.0%"}]
    measured = [{"metric": "A", "value": "1.0%"}]
    out = compare_results(expected, measured)
    assert "verdict" not in str(out["rows"]).lower()
