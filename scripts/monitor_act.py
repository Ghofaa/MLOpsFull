"""Act workflow for monitoring alerts.

Consumes alert + expectations artifacts and emits an action decision ticket
to operationalize the "Act" phase from the monitoring lesson.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate action decision from monitoring alerts.")
    parser.add_argument(
        "--alert",
        default="artifacts/alerts/latest_alert.json",
        help="Path to alert ticket JSON.",
    )
    parser.add_argument(
        "--expectations",
        default="artifacts/monitoring/expectations_report.json",
        help="Path to expectations report JSON.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/alerts/action_decision.json",
        help="Path to action decision output JSON.",
    )
    parser.add_argument(
        "--trigger-file",
        default="artifacts/alerts/retrain.trigger",
        help="File path to create when retraining is recommended.",
    )
    parser.add_argument(
        "--fail-on-retrain",
        action="store_true",
        help="Exit with code 1 when retraining is recommended (default: record decision only).",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def main() -> int:
    args = parse_args()
    alert_path = Path(args.alert)
    expectations_path = Path(args.expectations)
    output_path = Path(args.output)
    trigger_path = Path(args.trigger_file)

    alert = _load_json(alert_path)
    expectations = _load_json(expectations_path)

    triggered_alerts = alert.get("triggered_alerts", []) if isinstance(alert.get("triggered_alerts"), list) else []
    severity = str(alert.get("severity", "none"))
    expectations_ok = bool(expectations.get("success", False))

    should_retrain = False
    action_reason = []
    recommended_actions: list[str] = []

    if not expectations_ok:
        action_reason.append("Data expectations failed.")
        recommended_actions.append("Block retraining until schema/data quality checks pass.")
        recommended_actions.append("Inspect failed expectations in expectations_report.json.")
    elif severity == "high":
        should_retrain = True
        action_reason.append("High-severity monitoring alert triggered.")
        recommended_actions.append("Trigger retraining pipeline on latest validated dataset.")
        recommended_actions.append("Compare new model against current production model before promotion.")
    elif severity == "medium":
        action_reason.append("Medium-severity alert triggered; monitor for persistence.")
        recommended_actions.append("Increase monitoring frequency and inspect drift slices.")
        recommended_actions.append("Retrain only if alert persists across additional windows.")
    else:
        action_reason.append("No active alerts requiring intervention.")
        recommended_actions.append("Continue normal monitoring cadence.")

    if "sliding_f1_regression" in triggered_alerts and expectations_ok:
        should_retrain = True
        if "Sliding-window F1 regression detected." not in action_reason:
            action_reason.append("Sliding-window F1 regression detected.")
        recommended_actions.append("Prioritize retraining with recent production-like samples.")

    decision = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "alert_path": str(alert_path),
            "expectations_path": str(expectations_path),
        },
        "status": "action_required" if should_retrain else "monitor_only",
        "retrain_recommended": should_retrain,
        "triggered_alerts": triggered_alerts,
        "severity": severity,
        "expectations_success": expectations_ok,
        "reason": action_reason,
        "recommended_actions": recommended_actions,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(decision, indent=2), encoding="utf-8")

    if should_retrain:
        trigger_path.parent.mkdir(parents=True, exist_ok=True)
        trigger_payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": action_reason,
            "triggered_alerts": triggered_alerts,
        }
        trigger_path.write_text(json.dumps(trigger_payload, indent=2), encoding="utf-8")
    elif trigger_path.exists():
        trigger_path.unlink()

    print(json.dumps(decision, indent=2))
    if args.fail_on_retrain and should_retrain:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
