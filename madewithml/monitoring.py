from collections import Counter
from math import erf, sqrt
from typing import Dict, Iterable, List, Mapping, Sequence

import numpy as np


def text_length(title: str = "", description: str = "") -> int:
    """Return the token count for a prediction request."""
    text = f"{title or ''} {description or ''}".strip()
    return len(text.split()) if text else 0


def validate_prediction_input(title: str = "", description: str = "") -> List[str]:
    """Validate the basic input expectations for prediction requests."""
    failures = []
    if not str(title or "").strip():
        failures.append("title_empty")
    if not str(description or "").strip():
        failures.append("description_empty")
    return failures


def prediction_confidence(result: Mapping) -> float:
    """Extract the probability assigned to the predicted class."""
    prediction = result.get("prediction")
    probabilities = result.get("probabilities", {})
    if prediction in probabilities:
        return float(probabilities[prediction])
    if probabilities:
        return float(max(probabilities.values()))
    return 0.0


def summarize_predictions(results: Sequence[Mapping]) -> Dict:
    """Summarize prediction outputs for monitoring and reporting."""
    predictions = [result.get("prediction", "") for result in results]
    confidences = [prediction_confidence(result) for result in results]
    total = len(results)
    other_count = sum(prediction == "other" for prediction in predictions)
    return {
        "total": total,
        "class_counts": dict(Counter(predictions)),
        "avg_confidence": float(np.mean(confidences)) if confidences else 0.0,
        "min_confidence": float(np.min(confidences)) if confidences else 0.0,
        "other_rate": float(other_count / total) if total else 0.0,
    }


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def detect_text_length_drift(
    reference_lengths: Iterable[float],
    current_lengths: Iterable[float],
    z_threshold: float = 3.0,
) -> Dict:
    """Detect simple mean-shift drift in text length distributions."""
    reference = np.asarray(list(reference_lengths), dtype=float)
    current = np.asarray(list(current_lengths), dtype=float)
    if reference.size == 0 or current.size == 0:
        raise ValueError("reference_lengths and current_lengths must not be empty.")

    reference_mean = float(np.mean(reference))
    current_mean = float(np.mean(current))
    reference_std = float(np.std(reference, ddof=1)) if reference.size > 1 else 0.0
    standard_error = reference_std / sqrt(float(current.size)) if reference_std else 0.0
    z_score = (current_mean - reference_mean) / standard_error if standard_error else 0.0
    p_value = 2.0 * (1.0 - _normal_cdf(abs(z_score))) if standard_error else 1.0
    return {
        "is_drift": bool(abs(z_score) >= z_threshold),
        "measurement": "text_length_z_test",
        "reference_mean": reference_mean,
        "current_mean": current_mean,
        "z_score": float(z_score),
        "p_value": float(max(0.0, min(1.0, p_value))),
        "threshold": z_threshold,
    }


def detect_class_distribution_drift(
    reference_classes: Iterable[str],
    current_classes: Iterable[str],
    ratio_threshold: float = 0.2,
) -> Dict:
    """Detect categorical drift via total variation distance."""
    reference_counts = Counter(reference_classes)
    current_counts = Counter(current_classes)
    if not reference_counts or not current_counts:
        raise ValueError("reference_classes and current_classes must not be empty.")

    labels = sorted(set(reference_counts) | set(current_counts))
    reference_total = sum(reference_counts.values())
    current_total = sum(current_counts.values())
    distance = 0.5 * sum(
        abs((reference_counts[label] / reference_total) - (current_counts[label] / current_total)) for label in labels
    )
    return {
        "is_drift": bool(distance >= ratio_threshold),
        "measurement": "class_distribution_total_variation",
        "distance": float(distance),
        "threshold": ratio_threshold,
        "reference_distribution": {label: reference_counts[label] / reference_total for label in labels},
        "current_distribution": {label: current_counts[label] / current_total for label in labels},
    }
