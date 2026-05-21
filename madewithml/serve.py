import argparse
import datetime
import json
import os
import time
from http import HTTPStatus
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import ray
from alibi_detect.cd import ChiSquareDrift, KSDrift
from fastapi import FastAPI
from ray import serve
from starlette.requests import Request

from madewithml import evaluate, predict
from madewithml.config import MLFLOW_TRACKING_URI, mlflow, LOGS_DIR, ROOT_DIR, logger

# Define application
app = FastAPI(
    title="Made With ML",
    description="Classify machine learning projects.",
    version="0.1",
)


@serve.deployment(num_replicas="1", ray_actor_options={"num_cpus": 1, "num_gpus": 0})
@serve.ingress(app)
class ModelDeployment:
    def __init__(self, run_id: str, threshold: int = 0.9):
        """Initialize the model."""
        self.run_id = run_id
        self.threshold = threshold
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)  # so workers have access to model registry
        best_checkpoint = predict.get_best_checkpoint(run_id=run_id)
        self.predictor = predict.TorchPredictor.from_checkpoint(best_checkpoint)

        # ===== ADDED: DRIFT DETECTOR INIT (START) =====
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
        # ===== ADDED: DRIFT DETECTOR INIT (END) =====

    # ===== ADDED: DRIFT MONITORING HELPERS (START) =====
    @staticmethod
    def _count_tokens(text: str) -> int:
        return len((text or "").split())

    @staticmethod
    def _token_count_bucket(token_counts: np.ndarray) -> np.ndarray:
        """Bucketize token counts for categorical drift detection."""
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

    def _load_reference_token_counts(self) -> np.ndarray | None:
        """Load notebook-aligned reference token counts for drift detectors."""
        if self.reference_dataset_fp.exists():
            df = pd.read_csv(self.reference_dataset_fp)
            if {"title", "description"}.issubset(df.columns):
                text = (df["title"].fillna("") + " " + df["description"].fillna("")).astype(str)
                return text.apply(self._count_tokens).to_numpy(dtype=np.float32)

        # Backward compatibility with previous reference artifact formats.
        if self.reference_fp.exists():
            arr = np.load(self.reference_fp, allow_pickle=True)
            if arr.ndim == 1:
                return np.asarray(arr, dtype=np.float32)
            if arr.ndim == 2 and arr.shape[1] == 1:
                return np.asarray(arr[:, 0], dtype=np.float32)
            if arr.ndim == 2 and arr.shape[1] >= 2:
                # Legacy reference had title/description lengths; approximate token size.
                return np.maximum(1.0, np.asarray(arr[:, 0] + arr[:, 1], dtype=np.float32) / 5.0)
        return None

    def _extract_token_counts(self, items: list[dict]) -> np.ndarray:
        """Extract token-count feature for notebook-aligned drift checks."""
        counts = []
        for item in items:
            title = item.get("title", "") or ""
            description = item.get("description", "") or ""
            counts.append(self._count_tokens(f"{title} {description}".strip()))
        return np.asarray(counts, dtype=np.float32)

    def _monitor_drift(self, items: list[dict]) -> None:
        """Run notebook-aligned drift checks (KS + ChiSquare) and log warnings."""
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
    # ===== ADDED: DRIFT MONITORING HELPERS (END) =====

    # ===== ADDED: SYSTEM HEALTH MONITORING HELPERS (START) =====
    def _log_request_metrics(
        self,
        endpoint: str,
        start_time: float,
        http_status: int,
        status: str = "ok",
        error: Exception | None = None,
    ) -> None:
        """Log request-level health metrics for monitoring dashboards."""
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        payload = {
            "event": "request_metrics",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "endpoint": endpoint,
            "run_id": self.run_id,
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
    # ===== ADDED: SYSTEM HEALTH MONITORING HELPERS (END) =====

    @app.get("/")
    def _index(self) -> Dict:
        """Health check."""
        start_time = time.perf_counter()
        try:
            response = {
                "message": HTTPStatus.OK.phrase,
                "status-code": HTTPStatus.OK,
                "data": {},
            }
            self._log_request_metrics(endpoint="/", start_time=start_time, http_status=HTTPStatus.OK)
            return response
        except Exception as e:
            self._log_request_metrics(
                endpoint="/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                status="error",
                error=e,
            )
            raise

    @app.get("/run_id/")
    def _run_id(self) -> Dict:
        """Get the run ID."""
        start_time = time.perf_counter()
        try:
            response = {"run_id": self.run_id}
            self._log_request_metrics(endpoint="/run_id/", start_time=start_time, http_status=HTTPStatus.OK)
            return response
        except Exception as e:
            self._log_request_metrics(
                endpoint="/run_id/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                status="error",
                error=e,
            )
            raise

    @app.post("/evaluate/")
    async def _evaluate(self, request: Request) -> Dict:
        start_time = time.perf_counter()
        try:
            data = await request.json()
            results = evaluate.evaluate(run_id=self.run_id, dataset_loc=data.get("dataset"))
            self._log_request_metrics(endpoint="/evaluate/", start_time=start_time, http_status=HTTPStatus.OK)
            return {"results": results}
        except Exception as e:
            self._log_request_metrics(
                endpoint="/evaluate/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                status="error",
                error=e,
            )
            raise

    @app.post("/predict/")
    async def _predict(self, request: Request):
        start_time = time.perf_counter()
        try:
            data = await request.json()
            items = [{"title": data.get("title", ""), "description": data.get("description", ""), "tag": ""}]

            # ===== ADDED: DRIFT CHECK DURING PREDICT (START) =====
            self._monitor_drift(items)
            # ===== ADDED: DRIFT CHECK DURING PREDICT (END) =====

            sample_ds = ray.data.from_items(items)
            results = predict.predict_proba(ds=sample_ds, predictor=self.predictor)

            # Apply custom logic
            for i, result in enumerate(results):
                pred = result["prediction"]
                prob = result["probabilities"]
                if prob[pred] < self.threshold:
                    results[i]["prediction"] = "other"

            self._log_request_metrics(endpoint="/predict/", start_time=start_time, http_status=HTTPStatus.OK)
            return {"results": results}
        except Exception as e:
            self._log_request_metrics(
                endpoint="/predict/",
                start_time=start_time,
                http_status=HTTPStatus.INTERNAL_SERVER_ERROR,
                status="error",
                error=e,
            )
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_id", help="run ID to use for serving.")
    parser.add_argument("--threshold", type=float, default=0.9, help="threshold for `other` class.")
    args = parser.parse_args()
    ray.init(runtime_env={"env_vars": {"GITHUB_USERNAME": os.environ["GITHUB_USERNAME"]}})
    serve.run(ModelDeployment.bind(run_id=args.run_id, threshold=args.threshold))
