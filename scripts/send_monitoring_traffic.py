import argparse
import json
import random
import time
from collections import Counter
from urllib import error, request


SCENARIOS = [
    {
        "name": "nlp_transformers",
        "title": "Text classification with transformers",
        "description": "A project using BERT and SciBERT for NLP classification and semantic search.",
    },
    {
        "name": "computer_vision",
        "title": "YOLO object detection for traffic cameras",
        "description": "Real-time computer vision pipeline for detecting cars, pedestrians, and road signs.",
    },
    {
        "name": "mlops",
        "title": "MLflow model registry and Jenkins pipeline",
        "description": "An MLOps project with experiment tracking, model registry, Docker deployment, and monitoring.",
    },
    {
        "name": "graph_learning",
        "title": "Graph neural networks for recommendation",
        "description": "Node embeddings and graph classification for product recommendation on user-item networks.",
    },
    {
        "name": "reinforcement_learning",
        "title": "Deep reinforcement learning for robot control",
        "description": "Policy optimization agent trained with rewards for navigation and continuous control.",
    },
    {
        "name": "short_text",
        "title": "BERT",
        "description": "Classifier",
    },
    {
        "name": "long_text",
        "title": "Large-scale machine learning platform with monitoring and automation",
        "description": " ".join(
            [
                "This project builds a full machine learning platform with data validation, feature processing,",
                "transformer training, model evaluation, CI/CD automation, serving, Prometheus metrics,",
                "Grafana dashboards, alerting, drift analysis, and a retraining workflow for production systems.",
            ]
        ),
    },
    {
        "name": "empty_title",
        "title": "",
        "description": "Description is present but title is missing to trigger input validation monitoring.",
    },
    {
        "name": "empty_description",
        "title": "Missing description example",
        "description": "",
    },
    {
        "name": "unknown_topic",
        "title": "Inventory dashboard for coffee shop sales",
        "description": "A business dashboard for stock levels, invoices, daily revenue, and supplier orders.",
    },
]


def post_json(url: str, payload: dict, timeout: int) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except error.URLError as exc:
        return 0, str(exc.reason)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send sample prediction traffic for monitoring dashboards.")
    parser.add_argument("--url", default="http://localhost:8000/predict/", help="Prediction endpoint URL.")
    parser.add_argument("--requests", type=int, default=40, help="Number of requests to send.")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds to sleep between requests.")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for repeatable scenario ordering.")
    parser.add_argument(
        "--valid-only",
        action="store_true",
        help="Skip scenarios with intentionally empty title or description fields.",
    )
    parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first non-200 response.")
    args = parser.parse_args()

    random.seed(args.seed)
    scenarios = SCENARIOS
    if args.valid_only:
        scenarios = [scenario for scenario in SCENARIOS if scenario["title"].strip() and scenario["description"].strip()]

    counts = Counter()
    statuses = Counter()

    print(f"Sending {args.requests} requests to {args.url}")
    for i in range(args.requests):
        scenario = random.choice(scenarios)
        status, body = post_json(args.url, scenario, timeout=args.timeout)
        counts[scenario["name"]] += 1
        statuses[status] += 1

        if status == 200:
            response = json.loads(body)
            monitoring_summary = response.get("monitoring", {})
            predictions = monitoring_summary.get("class_counts", {})
            confidence = monitoring_summary.get("avg_confidence", 0.0)
            other_rate = monitoring_summary.get("other_rate", 0.0)
            print(
                f"{i + 1:03d}/{args.requests} {scenario['name']:<24} "
                f"status={status} predictions={predictions} "
                f"avg_confidence={confidence:.4f} other_rate={other_rate:.2f}"
            )
        else:
            print(f"{i + 1:03d}/{args.requests} {scenario['name']:<24} status={status} error={body[:180]}")
            if args.stop_on_error:
                break

        if args.sleep:
            time.sleep(args.sleep)

    print("\nScenario counts:")
    for name, count in sorted(counts.items()):
        print(f"- {name}: {count}")

    print("\nHTTP status counts:")
    for status, count in sorted(statuses.items()):
        print(f"- {status}: {count}")


if __name__ == "__main__":
    main()
