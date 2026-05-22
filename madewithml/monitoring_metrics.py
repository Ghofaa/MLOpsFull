from functools import lru_cache
from typing import Mapping

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest


@lru_cache(maxsize=1)
def registry() -> CollectorRegistry:
    return CollectorRegistry()


@lru_cache(maxsize=1)
def request_count() -> Counter:
    return Counter(
        "mlopsfull_requests_total",
        "Total HTTP requests handled by the model service.",
        ["endpoint", "method", "status"],
        registry=registry(),
    )


@lru_cache(maxsize=1)
def request_latency() -> Histogram:
    return Histogram(
        "mlopsfull_request_latency_seconds",
        "Prediction and evaluation request latency.",
        ["endpoint"],
        registry=registry(),
    )


@lru_cache(maxsize=1)
def prediction_count() -> Counter:
    return Counter(
        "mlopsfull_predictions_total",
        "Total predictions emitted by class.",
        ["prediction"],
        registry=registry(),
    )


@lru_cache(maxsize=1)
def prediction_confidence() -> Histogram:
    return Histogram(
        "mlopsfull_prediction_confidence",
        "Confidence score assigned to emitted predictions.",
        buckets=(0.0, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0),
        registry=registry(),
    )


@lru_cache(maxsize=1)
def input_text_length() -> Histogram:
    return Histogram(
        "mlopsfull_input_text_length_tokens",
        "Input title and description length in whitespace-delimited tokens.",
        buckets=(0, 5, 10, 25, 50, 100, 250, 500),
        registry=registry(),
    )


@lru_cache(maxsize=1)
def other_prediction_rate() -> Gauge:
    return Gauge(
        "mlopsfull_other_prediction_rate",
        "Rate of predictions mapped to the fallback other class in the latest request.",
        registry=registry(),
    )


@lru_cache(maxsize=1)
def validation_failures() -> Counter:
    return Counter(
        "mlopsfull_input_validation_failures_total",
        "Total input expectation failures.",
        ["failure"],
        registry=registry(),
    )


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(registry()), CONTENT_TYPE_LATEST


def record_request(endpoint: str, method: str, status: str) -> None:
    request_count().labels(endpoint=endpoint, method=method, status=status).inc()


def observe_latency(endpoint: str, seconds: float) -> None:
    request_latency().labels(endpoint=endpoint).observe(seconds)


def observe_input_text_length(length: int) -> None:
    input_text_length().observe(length)


def record_validation_failure(failure: str) -> None:
    validation_failures().labels(failure=failure).inc()


def record_prediction(result: Mapping, confidence: float) -> None:
    prediction_count().labels(prediction=result["prediction"]).inc()
    prediction_confidence().observe(confidence)


def set_other_rate(rate: float) -> None:
    other_prediction_rate().set(rate)
