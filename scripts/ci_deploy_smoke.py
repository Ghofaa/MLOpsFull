import argparse
import json
import os
import sys
import time
import urllib.request

import ray
from ray import serve

from madewithml.serve import ModelDeployment

def http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def http_post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--summary", default="artifacts/quality_gate_summary.json")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--threshold", type=float, default=0.9)
    p.add_argument("--report", default="artifacts/deploy_smoke.json")
    args = p.parse_args()

    summary = json.load(open(args.summary, "r", encoding="utf-8"))
    run_id = summary["run_id"]

    os.environ.setdefault("GITHUB_USERNAME", "ci-user")
    ray.init(ignore_reinit_error=True, num_cpus=1, num_gpus=0, include_dashboard=False)
    serve.start(detached=False, http_options={"host": args.host, "port": args.port})
    serve.run(ModelDeployment.bind(run_id=run_id, threshold=args.threshold), route_prefix="/")

    # small startup wait
    time.sleep(3)

    base = f"http://{args.host}:{args.port}"
    health = http_get(f"{base}/")
    pred = http_post(f"{base}/predict/", {"title": "Smoke test", "description": "CI deploy check"})

    ok = health.get("status-code") == 200 and "results" in pred
    report = {"run_id": run_id, "health": health, "predict": pred, "passed": ok}
    json.dump(report, open(args.report, "w", encoding="utf-8"), indent=2)

    serve.shutdown()
    ray.shutdown()
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())