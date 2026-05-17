"""ADDED: CI train/evaluate quality gate for Jenkins.

Runs a lightweight training workload, evaluates on holdout data,
and fails with non-zero exit code when F1 is below threshold.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import ray

from madewithml import evaluate, train


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run lightweight MLOps CI quality gate.")
    parser.add_argument("--dataset", default="datasets/dataset.csv", help="Training dataset CSV path.")
    parser.add_argument("--holdout", default="datasets/holdout.csv", help="Holdout dataset CSV path.")
    parser.add_argument("--results-dir", default="artifacts", help="Directory for train/eval result files.")
    parser.add_argument("--num-samples", type=int, default=64, help="Number of samples to use for fast CI train.")
    parser.add_argument("--num-epochs", type=int, default=1, help="Epochs for fast CI train.")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size for fast CI train.")
    parser.add_argument("--f1-threshold", type=float, default=0.30, help="Minimum acceptable weighted F1.")
    parser.add_argument(
        "--experiment-name",
        default=None,
        help="Optional MLflow experiment name. If omitted, a build-based name is generated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    build_tag = os.environ.get("BUILD_TAG", "local")
    experiment_name = args.experiment_name or f"ci-mlops-{build_tag}".replace(" ", "-")

    train_results_fp = results_dir / "train_results.json"
    eval_results_fp = results_dir / "eval_results.json"
    summary_fp = results_dir / "quality_gate_summary.json"

    # Keep config intentionally small for CI speed.
    train_loop_config = {
        "dropout_p": 0.5,
        "lr": 1e-4,
        "lr_factor": 0.8,
        "lr_patience": 1,
    }

    try:
        if ray.is_initialized():
            ray.shutdown()
        # ===== ADDED: Force CPU-only Ray init for Jenkins Windows agent (START) =====
        ray.init(
            ignore_reinit_error=True,
            num_cpus=1,
            num_gpus=0,
            include_dashboard=False,
            runtime_env={"env_vars": {"GITHUB_USERNAME": os.environ.get("GITHUB_USERNAME", "ci-user")}},
        )
        # ===== ADDED: Force CPU-only Ray init for Jenkins Windows agent (END) =====

        train.train_model(
            experiment_name=experiment_name,
            dataset_loc=args.dataset,
            train_loop_config=json.dumps(train_loop_config),
            num_workers=1,
            cpu_per_worker=1,
            gpu_per_worker=0,
            num_samples=args.num_samples,
            num_epochs=args.num_epochs,
            batch_size=args.batch_size,
            results_fp=str(train_results_fp),
        )

        train_results = json.loads(train_results_fp.read_text(encoding="utf-8"))
        run_id = train_results["run_id"]

        eval_metrics = evaluate.evaluate(
            run_id=run_id,
            dataset_loc=args.holdout,
            results_fp=str(eval_results_fp),
        )
        f1 = float(eval_metrics["overall"]["f1"])
        passed = f1 >= args.f1_threshold

        summary = {
            "experiment_name": experiment_name,
            "run_id": run_id,
            "f1": f1,
            "threshold": args.f1_threshold,
            "passed": passed,
        }
        summary_fp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))

        return 0 if passed else 1
    finally:
        if ray.is_initialized():
            ray.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
