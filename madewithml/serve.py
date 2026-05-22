import argparse
import datetime
import json
import os
import time
from http import HTTPStatus
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import ray
import uvicorn
from alibi_detect.cd import ChiSquareDrift, KSDrift
from fastapi import FastAPI
from ray import serve
from starlette.requests import Request
from starlette.responses import Response

from madewithml import evaluate, monitoring, monitoring_metrics, predict
from madewithml.config import LOGS_DIR, MLFLOW_TRACKING_URI, ROOT_DIR, logger, mlflow

os.environ.setdefault("RAY_SERVE_PROXY_READY_CHECK_TIMEOUT_S", "60")

app = FastAPI(
    title="Made With ML",
    description="Classify machine learning projects.",
    version="0.1",
)


@app.get("/metrics")
def metrics() -> Response:
    """Expose Prometheus metrics."""
    body, media_type = monitoring_metrics.render_metrics()
    return Response(body, media_type=media_type)


def apply_prediction_threshold(results, threshold: float):
    """Map low-confidence predictions to the fallback class."""
    for i, result in enumerate(results):
        pred = result["prediction"]
        prob = result["probabilities"]
        if prob[pred] < threshold:
            results[i]["prediction"] = "other"
    return results


def record_prediction_request(title: str, description: str, results):
    """Record Prometheus metrics and return request summary."""
    monitoring_metrics.observe_input_text_length(monitoring.text_length(title=title, description=description))
    for failure in monitoring.validate_prediction_input(title=title, description=description):
        monitoring_metrics.record_validation_failure(failure)

    summary = monitoring.summarize_predictions(results)
    monitoring_metrics.set_other_rate(summary["other_rate"])
    for result in results:
        monitoring_metrics.record_prediction(result, confidence=monitoring.prediction_confidence(result))
    return summary


class DriftMonitor:
    """Notebook-aligned KS + Chi-square drift checks (logs to error.log)."""

    def __init__(self, run_id: str = ""):
        self.run_id = run_id
        self.reference_fp = Path(ROOT_DIR, "X_train_reference.npy")
        self.reference_dataset_fp = Path(ROOT_DIR, "datasets", "dataset.csv")
        self.ks_drift_detector = None
        self.chi_drift_detector = None

        reference_token_counts = self._load_reference_token_counts()
        if reference_token_counts is not None and reference_token_counts.size > 0:
            self.ks_drift_detector = KSDrift(reference_token_counts, p_val=0.01)
            reference_buckets = self._token_count_bucket(reference_token_counts)
            self.chi_drift_detector = ChiSquareDrift(reference_buckets, p_val=0.01)
            logger.info(
                "Drift detectors initialized (KSDrift + ChiSquareDrift) "
                f"with {len(reference_token_counts)} reference points."
            )
        else:
            logger.warning(
                "No valid reference data found for drift monitoring. "
                "Drift checks are disabled until reference data is available."
            )

    @staticmethod
    def _count_tokens(text: str) -> int:
        return len((text or "").split())

    @staticmethod
    def _token_count_bucket(token_counts: np.ndarray) -> np.ndarray:
        buckets = []
        for val in token_counts:
            count = int(val)
            if count <= 10:
                buckets.append("small")
            elif count <= 25:
                buckets.append("medium")
            else:
                buckets.append("large")
        return np.asarray(buckets, dtype=object)

    def _load_reference_token_counts(self) -> Optional[np.ndarray]:
        if self.reference_dataset_fp.exists():
            df = pd.read_csv(self.reference_dataset_fp)
            if {"title", "description"}.issubset(df.columns):
                text = (df["title"].fillna("") + " " + df["description"].fillna("")).astype(str)
                return text.apply(self._count_tokens).to_numpy(dtype=np.float32)

        if self.reference_fp.exists():
            arr = np.load(self.reference_fp, allow_pickle=True)
            if arr.ndim == 1:
                return np.asarray(arr, dtype=np.float32)
            if arr.ndim == 2 and arr.shape[1] == 1:
                return np.asarray(arr[:, 0], dtype=np.float32)
            if arr.ndim == 2 and arr.shape[1] >= 2:
                return np.maximum(1.0, np.asarray(arr[:, 0] + arr[:, 1], dtype=np.float32) / 5.0)
        return None

    def _extract_token_counts(self, items: list) -> np.ndarray:
        counts = []
        for item in items:
            title = item.get("title", "") or ""
            description = item.get("description", "") or ""
            counts.append(self._count_tokens(f"{title} {description}".strip()))
        return np.asarray(counts, dtype=np.float32)

    def monitor_drift(self, items: list) -> None:
        if self.ks_drift_detector is None or self.chi_drift_detector is None:
            return

        incoming_token_counts = self._extract_token_counts(items)
        incoming_buckets = self._token_count_bucket(incoming_token_counts)

        ks_output = self.ks_drift_detector.predict(incoming_token_counts, return_p_val=True, return_distance=True)
        chi_output = self.chi_drift_detector.predict(incoming_buckets, return_p_val=True, return_distance=True)

        ks_is_drift = int(ks_output["data"]["is_drift"])
        chi_is_drift = int(chi_output["data"]["is_drift"])
        is_drift = 1 if (ks_is_drift == 1 or chi_is_drift == 1) else 0

        if is_drift == 1:
            warning_payload = {
                "event": "drift_alert",
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "run_id": self.run_id,
                "ks_is_drift": ks_is_drift,
                "ks_p_val": np.asarray(ks_output["data"]["p_val"]).tolist(),
                "ks_distance": np.asarray(ks_output["data"]["distance"]).tolist(),
                "chi_is_drift": chi_is_drift,
                "chi_p_val": np.asarray(chi_output["data"]["p_val"]).tolist(),
                "chi_distance": np.asarray(chi_output["data"]["distance"]).tolist(),
                "incoming_token_counts": incoming_token_counts.tolist(),
                "incoming_buckets": incoming_buckets.tolist(),
            }
            warning_message = json.dumps(warning_payload)
            with open(Path(LOGS_DIR, "error.log"), "a", encoding="utf-8") as file:
                file.write(warning_message + "\n")
            logger.warning(warning_message)


def _log_request_metrics(
    endpoint: str,
    start_time: float,
    http_status: int,
    run_id: str = "",
    status: str = "ok",
    error: Exception | None = None,
) -> None:
    """Log request-level health metrics for monitoring dashboards."""
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    payload = {
        "event": "request_metrics",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "endpoint": endpoint,
        "run_id": run_id,
        "status": status,
        "http_status": int(http_status),
        "latency_ms": latency_ms,
    }
    if error is not None:
        payload["error_type"] = type(error).__name__
        payload["error_message"] = str(error)

    message = json.dumps(payload)
    if status == "error":
        logger.error(message)
    else:
        logger.info(message)


def create_standalone_app(run_id: str, threshold: float = 0.9) -> FastAPI:
    """Plain FastAPI app for reliable Jenkins/Docker serving."""
    standalone_app = FastAPI(
        title="Made With ML",
        description="Classify machine learning projects.",
        version="0.1",
    )
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    best_checkpoint = predict.get_best_checkpoint(run_id=run_id)
    predictor = predict.TorchPredictor.from_checkpoint(best_checkpoint)
    drift_monitor = DriftMonitor(run_id=run_id)

    @standalone_app.get("/metrics")
    def _metrics() -> Response:
        body, media_type = monitoring_metrics.render_metrics()
        return Response(body, media_type=media_type)

    @standalone_app.get("/")
    def _index() -> Dict:
        monitoring_metrics.record_request(endpoint="/", method="GET", status="success")
        return {
            "message": HTTPStatus.OK.phrase,
            "status-code": HTTPStatus.OK,
            "data": {},
        }

    @standalone_app.get("/run_id/")
    def _run_id() -> Dict:
        monitoring_metrics.record_request(endpoint="/run_id/", method="GET", status="success")
        return {"run_id": run_id}

    @standalone_app.post("/evaluate/")
    async def _evaluate(request: Request) -> Dict:
        start_time = time.perf_counter()
        try:
            data = await request.json()
            results = evaluate.evaluate(run_id=run_id, dataset_loc=data.get("dataset"))
            monitoring_metrics.record_request(endpoint="/evaluate/", method="POST", status="success")
            return {"results": results}
        except Exception as exc:
            monitoring_metrics.record_request(endpoint="/evaluate/", method="POST", status="error")
            _log_request_metrics(
                endpoint="/evaluate/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                run_id=run_id,
                status="error",
                error=exc,
            )
            raise
        finally:
            monitoring_metrics.observe_latency(endpoint="/evaluate/", seconds=time.perf_counter() - start_time)

    @standalone_app.post("/predict/")
    async def _predict(request: Request):
        start_time = time.perf_counter()
        try:
            data = await request.json()
            title = data.get("title", "")
            description = data.get("description", "")
            items = [{"title": title, "description": description, "tag": ""}]
            drift_monitor.monitor_drift(items)

            results = predict.predict_proba_items(items=items, predictor=predictor)
            results = apply_prediction_threshold(results=results, threshold=threshold)
            summary = record_prediction_request(title=title, description=description, results=results)
            monitoring_metrics.record_request(endpoint="/predict/", method="POST", status="success")
            _log_request_metrics(endpoint="/predict/", start_time=start_time, http_status=HTTPStatus.OK, run_id=run_id)
            return {"results": results, "monitoring": summary}
        except Exception as exc:
            monitoring_metrics.record_request(endpoint="/predict/", method="POST", status="error")
            _log_request_metrics(
                endpoint="/predict/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                run_id=run_id,
                status="error",
                error=exc,
            )
            raise
        finally:
            monitoring_metrics.observe_latency(endpoint="/predict/", seconds=time.perf_counter() - start_time)

    return standalone_app


@serve.deployment(num_replicas="1", ray_actor_options={"num_cpus": 1, "num_gpus": 0})
@serve.ingress(app)
class ModelDeployment:
    def __init__(self, run_id: str, threshold: float = 0.9):
        self.run_id = run_id
        self.threshold = threshold
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        best_checkpoint = predict.get_best_checkpoint(run_id=run_id)
        self.predictor = predict.TorchPredictor.from_checkpoint(best_checkpoint)
        self.drift_monitor = DriftMonitor(run_id=run_id)

    @app.get("/")
    def _index(self) -> Dict:
        start_time = time.perf_counter()
        try:
            monitoring_metrics.record_request(endpoint="/", method="GET", status="success")
            response = {
                "message": HTTPStatus.OK.phrase,
                "status-code": HTTPStatus.OK,
                "data": {},
            }
            _log_request_metrics(endpoint="/", start_time=start_time, http_status=HTTPStatus.OK, run_id=self.run_id)
            return response
        except Exception as exc:
            _log_request_metrics(
                endpoint="/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                run_id=self.run_id,
                status="error",
                error=exc,
            )
            raise

    @app.get("/run_id/")
    def _run_id(self) -> Dict:
        start_time = time.perf_counter()
        try:
            monitoring_metrics.record_request(endpoint="/run_id/", method="GET", status="success")
            _log_request_metrics(endpoint="/run_id/", start_time=start_time, http_status=HTTPStatus.OK, run_id=self.run_id)
            return {"run_id": self.run_id}
        except Exception as exc:
            _log_request_metrics(
                endpoint="/run_id/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                run_id=self.run_id,
                status="error",
                error=exc,
            )
            raise

    @app.post("/evaluate/")
    async def _evaluate(self, request: Request) -> Dict:
        start_time = time.perf_counter()
        try:
            data = await request.json()
            results = evaluate.evaluate(run_id=self.run_id, dataset_loc=data.get("dataset"))
            monitoring_metrics.record_request(endpoint="/evaluate/", method="POST", status="success")
            _log_request_metrics(endpoint="/evaluate/", start_time=start_time, http_status=HTTPStatus.OK, run_id=self.run_id)
            return {"results": results}
        except Exception as exc:
            monitoring_metrics.record_request(endpoint="/evaluate/", method="POST", status="error")
            _log_request_metrics(
                endpoint="/evaluate/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                run_id=self.run_id,
                status="error",
                error=exc,
            )
            raise
        finally:
            monitoring_metrics.observe_latency(endpoint="/evaluate/", seconds=time.perf_counter() - start_time)

    @app.post("/predict/")
    async def _predict(self, request: Request):
        start_time = time.perf_counter()
        try:
            data = await request.json()
            title = data.get("title", "")
            description = data.get("description", "")
            items = [{"title": title, "description": description, "tag": ""}]
            self.drift_monitor.monitor_drift(items)

            sample_ds = ray.data.from_items(items)
            results = predict.predict_proba(ds=sample_ds, predictor=self.predictor)
            results = apply_prediction_threshold(results=results, threshold=self.threshold)
            summary = record_prediction_request(title=title, description=description, results=results)
            monitoring_metrics.record_request(endpoint="/predict/", method="POST", status="success")
            _log_request_metrics(endpoint="/predict/", start_time=start_time, http_status=HTTPStatus.OK, run_id=self.run_id)
            return {"results": results, "monitoring": summary}
        except Exception as exc:
            monitoring_metrics.record_request(endpoint="/predict/", method="POST", status="error")
            _log_request_metrics(
                endpoint="/predict/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                run_id=self.run_id,
                status="error",
                error=exc,
            )
            raise
        finally:
            monitoring_metrics.observe_latency(endpoint="/predict/", seconds=time.perf_counter() - start_time)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_id", required=True, help="run ID to use for serving.")
    parser.add_argument("--threshold", type=float, default=0.9, help="threshold for `other` class.")
    parser.add_argument("--backend", choices=["fastapi", "ray-serve"], default="fastapi", help="serving backend.")
    args = parser.parse_args()
    os.environ.setdefault("GITHUB_USERNAME", "local-user")
    ray.init(
        num_cpus=1,
        num_gpus=0,
        include_dashboard=False,
        ignore_reinit_error=True,
        object_store_memory=200 * 1024 * 1024,
        runtime_env={"env_vars": {"GITHUB_USERNAME": os.environ["GITHUB_USERNAME"]}},
    )
    if args.backend == "ray-serve":
        serve.start(http_options={"host": "0.0.0.0", "port": 8000})
        serve.run(ModelDeployment.bind(run_id=args.run_id, threshold=args.threshold))
        while True:
            time.sleep(3600)

    uvicorn.run(create_standalone_app(run_id=args.run_id, threshold=args.threshold), host="0.0.0.0", port=8000)
