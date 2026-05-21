import argparse
import datetime
import os
from http import HTTPStatus
from pathlib import Path
from typing import Dict

import numpy as np
import ray
from alibi_detect.cd import KSDrift
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
        self.drift_detector = None
        if self.reference_fp.exists():
            self.X_reference = np.load(self.reference_fp)
            self.drift_detector = KSDrift(self.X_reference, p_val=0.01)
            logger.info(f"Drift detector initialized from {self.reference_fp}.")
        else:
            self.X_reference = None
            logger.warning(
                f"Reference file not found at {self.reference_fp}. "
                "Drift monitoring is disabled until this file exists."
            )
        # ===== ADDED: DRIFT DETECTOR INIT (END) =====

    # ===== ADDED: DRIFT MONITORING HELPERS (START) =====
    def _extract_monitoring_features(self, items: list[dict]) -> np.ndarray:
        """Build simple numeric features for drift detection."""
        features = []
        for item in items:
            title = item.get("title", "") or ""
            description = item.get("description", "") or ""
            features.append([len(title), len(description)])
        return np.asarray(features, dtype=np.float32)

    def _monitor_drift(self, items: list[dict]) -> None:
        """Run drift check and log warning if drift is detected."""
        if self.drift_detector is None:
            return

        incoming_features = self._extract_monitoring_features(items)
        drift_output = self.drift_detector.predict(incoming_features)
        is_drift = int(drift_output["data"]["is_drift"])
        p_values = drift_output["data"]["p_val"]

        if is_drift == 1:
            warning_message = (
                f"[WARNING] {datetime.datetime.utcnow().isoformat()} "
                f"Data drift detected. p_values={p_values.tolist()}"
            )
            with open(Path(LOGS_DIR, "error.log"), "a", encoding="utf-8") as file:
                file.write(warning_message + "\n")
            logger.warning(warning_message)
    # ===== ADDED: DRIFT MONITORING HELPERS (END) =====

    @app.get("/")
    def _index(self) -> Dict:
        """Health check."""
        response = {
            "message": HTTPStatus.OK.phrase,
            "status-code": HTTPStatus.OK,
            "data": {},
        }
        return response

    @app.get("/run_id/")
    def _run_id(self) -> Dict:
        """Get the run ID."""
        return {"run_id": self.run_id}

    @app.post("/evaluate/")
    async def _evaluate(self, request: Request) -> Dict:
        data = await request.json()
        results = evaluate.evaluate(run_id=self.run_id, dataset_loc=data.get("dataset"))
        return {"results": results}

    @app.post("/predict/")
    async def _predict(self, request: Request):
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

        return {"results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_id", help="run ID to use for serving.")
    parser.add_argument("--threshold", type=float, default=0.9, help="threshold for `other` class.")
    args = parser.parse_args()
    ray.init(runtime_env={"env_vars": {"GITHUB_USERNAME": os.environ["GITHUB_USERNAME"]}})
    serve.run(ModelDeployment.bind(run_id=args.run_id, threshold=args.threshold))
