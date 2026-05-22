"""Deploy smoke test for Jenkins CD stage."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def http_get(url: str, timeout: int = 30) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")


def http_post_json(url: str, payload: dict, timeout: int = 30) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8")


def wait_for_service(base_url: str, attempts: int = 30, delay: float = 2.0) -> None:
    last_error = None
    for _ in range(attempts):
        try:
            status, _ = http_get(f"{base_url}/")
            if status == 200:
                return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(delay)
    raise RuntimeError(f"Service did not become healthy at {base_url}: {last_error}")


def start_fastapi_server(run_id: str, host: str, port: int, threshold: float) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("GITHUB_USERNAME", "ci-user")
    command = [
        sys.executable,
        "-m",
        "madewithml.serve",
        "--run_id",
        run_id,
        "--threshold",
        str(threshold),
        "--backend",
        "fastapi",
    ]
    return subprocess.Popen(command, env=env)


def start_ray_serve(run_id: str, host: str, port: int, threshold: float) -> subprocess.Popen:
    import ray
    from ray import serve

    from madewithml.serve import ModelDeployment

    os.environ.setdefault("GITHUB_USERNAME", "ci-user")
    ray.init(ignore_reinit_error=True, num_cpus=1, num_gpus=0, include_dashboard=False)
    serve.start(detached=False, http_options={"host": host, "port": port})
    serve.run(ModelDeployment.bind(run_id=run_id, threshold=threshold), route_prefix="/")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default="artifacts/quality_gate_summary.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--backend", choices=["fastapi", "ray-serve"], default="fastapi")
    parser.add_argument("--report", default="artifacts/deploy_smoke.json")
    parser.add_argument("--metrics-report", default="artifacts/metrics_smoke.txt")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    run_id = summary["run_id"]

    base = f"http://{args.host}:{args.port}"
    process = None
    report = {"run_id": run_id, "backend": args.backend, "passed": False}

    try:
        if args.backend == "fastapi":
            process = start_fastapi_server(run_id=run_id, host=args.host, port=args.port, threshold=args.threshold)
            wait_for_service(base)
        else:
            start_ray_serve(run_id=run_id, host=args.host, port=args.port, threshold=args.threshold)
            time.sleep(5)
            wait_for_service(base)

        health_status, health_body = http_get(f"{base}/")
        health = json.loads(health_body)
        run_status, run_body = http_get(f"{base}/run_id/")
        run_info = json.loads(run_body)

        metrics_status, metrics_body = http_get(f"{base}/metrics")
        Path(args.metrics_report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.metrics_report).write_text(metrics_body, encoding="utf-8")

        predict_status, predict_body = http_post_json(
            f"{base}/predict/",
            {
                "title": "Text classification with transformers",
                "description": "A project using BERT for NLP classification",
            },
        )
        predict_response = json.loads(predict_body)

        ok = (
            health_status == 200
            and health.get("status-code") == 200
            and run_status == 200
            and run_info.get("run_id") == run_id
            and metrics_status == 200
            and "mlopsfull_requests_total" in metrics_body
            and predict_status == 200
            and "results" in predict_response
        )
        report.update(
            {
                "health": health,
                "run_info": run_info,
                "metrics_status": metrics_status,
                "predict_status": predict_status,
                "predict_keys": sorted(predict_response.keys()),
                "passed": ok,
            }
        )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        if args.backend == "ray-serve":
            try:
                from ray import serve

                serve.shutdown()
                import ray

                if ray.is_initialized():
                    ray.shutdown()
            except Exception:
                pass

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
