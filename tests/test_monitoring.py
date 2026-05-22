import pytest

from madewithml import monitoring


def test_validate_prediction_input_reports_empty_fields():
    failures = monitoring.validate_prediction_input(title="", description="  ")

    assert failures == ["title_empty", "description_empty"]


def test_text_length_counts_title_and_description_tokens():
    length = monitoring.text_length("BERT Classifier", "NLP project with monitoring")

    assert length == 6


def test_prediction_summary_extracts_confidence_and_other_rate():
    results = [
        {"prediction": "natural-language-processing", "probabilities": {"natural-language-processing": 0.8, "mlops": 0.2}},
        {"prediction": "other", "probabilities": {"natural-language-processing": 0.4, "mlops": 0.6}},
    ]

    summary = monitoring.summarize_predictions(results)

    assert summary["total"] == 2
    assert summary["class_counts"] == {"natural-language-processing": 1, "other": 1}
    assert summary["avg_confidence"] == pytest.approx(0.7)
    assert summary["other_rate"] == pytest.approx(0.5)


def test_text_length_drift_detects_large_shift():
    result = monitoring.detect_text_length_drift(
        reference_lengths=[10, 11, 12, 9, 10, 11],
        current_lengths=[30, 31, 29],
    )

    assert result["is_drift"] is True
    assert result["measurement"] == "text_length_z_test"


def test_class_distribution_drift_detects_shift():
    result = monitoring.detect_class_distribution_drift(
        reference_classes=["mlops", "mlops", "nlp", "cv"],
        current_classes=["cv", "cv", "cv", "cv"],
        ratio_threshold=0.2,
    )

    assert result["is_drift"] is True
    assert result["measurement"] == "class_distribution_total_variation"
