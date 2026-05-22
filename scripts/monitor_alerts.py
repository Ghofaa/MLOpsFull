"""Generate monitoring alerts from drift + performance artifacts.

Implements the Alert phase from the monitoring lesson by combining:
- drift detector outputs (KS/ChiSquare)
- sliding performance metrics
- configurable thresholds
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate monitoring rules and emit alert tickets.")
    parser.add_argument(
        "--drift-log",
        default="logs/error.log",
        help="Path to log file containing drift_alert JSON entries.",
    )
    parser.add_argument(
        "--performance",
        default="artifacts/monitoring/performance_timeseries.json",
        help="Path to sliding metrics report JSON.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/alerts/latest_alert.json",
        help="Path to alert ticket output JSON.",
    )
    parser.add_argument(
        "--ks-p-threshold",
        type=float,
        default=0.01,
        help="Threshold for KS p-value alerting.",
    )
    parser.add_argument(
        "--chi-p-threshold",
        type=float,
        default=0.01,
        help="Threshold for ChiSquare p-value alerting.",
    )
    parser.add_argument(
        "--sliding-f1-threshold",
        type=float,
        default=0.55,
        help="Threshold for sliding F1 alerting.",
    )
    parser.add_argument(
        "--lookback-drift-events",
        type=int,
        default=5,
        help="How many recent drift events from logs to inspect.",
    )
    parser.add_argument(
        "--fail-on-alert",
        action="store_true",
        help="Exit with code 1 when any alert is triggered (default: write ticket only).",
    )
    return parser.parse_args()


def _coerce_float_list(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (float, int)):
        return [float(value)]
    if isinstance(value, list):
        out: list[float] = []
        for item in value:
            try:
                out.append(float(item))
            except (TypeError, ValueError):
                continue
        return out
    return []


def load_recent_drift_events(drift_log_path: Path, max_events: int) -> list[dict]:
    if not drift_log_path.exists():
        return []

    events: list[dict] = []
    for line in drift_log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("event") == "drift_alert":
            events.append(payload)
    return events[-max_events:]


def load_performance_summary(path: Path) -> dict:
    if not path.exists():
        return {"success": False, "error": f"Performance file not found: {path}"}
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return {"success": False, "error": "Invalid performance JSON structure."}
    return obj


def main() -> int:
    args = parse_args()
    drift_events = load_recent_drift_events(Path(args.drift_log), max_events=args.lookback_drift_events)
    perf = load_performance_summary(Path(args.performance))

    triggered_alerts: list[str] = []
    latest_drift = drift_events[-1] if drift_events else {}

    # Drift rules (latest event)
    ks_p_vals = _coerce_float_list(latest_drift.get("ks_p_val"))
    chi_p_vals = _coerce_float_list(latest_drift.get("chi_p_val"))
    ks_is_drift = int(latest_drift.get("ks_is_drift", 0))
    chi_is_drift = int(latest_drift.get("chi_is_drift", 0))

    if ks_is_drift == 1 and any(p < args.ks_p_threshold for p in ks_p_vals):
        triggered_alerts.append("ks_drift")
    if chi_is_drift == 1 and any(p < args.chi_p_threshold for p in chi_p_vals):
        triggered_alerts.append("chi_drift")

    # Performance rule
    sliding_f1 = None
    if perf.get("success") and isinstance(perf.get("summary"), dict):
        try:
            sliding_f1 = float(perf["summary"].get("latest_sliding_f1"))
            if sliding_f1 < args.sliding_f1_threshold:
                triggered_alerts.append("sliding_f1_regression")
        except (TypeError, ValueError):
            sliding_f1 = None

    alert_ticket = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "triggered_alerts": triggered_alerts,
        "severity": "high" if len(triggered_alerts) >= 2 else ("medium" if len(triggered_alerts) == 1 else "none"),
        "thresholds": {
            "ks_p_threshold": args.ks_p_threshold,
            "chi_p_threshold": args.chi_p_threshold,
            "sliding_f1_threshold": args.sliding_f1_threshold,
        },
        "measurements": {
            "ks_is_drift": ks_is_drift,
            "ks_p_val": ks_p_vals,
            "chi_is_drift": chi_is_drift,
            "chi_p_val": chi_p_vals,
            "latest_sliding_f1": sliding_f1,
        },
        "context": {
            "drift_events_considered": len(drift_events),
            "latest_drift_event": latest_drift,
            "performance_report_path": str(args.performance),
            "drift_log_path": str(args.drift_log),
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(alert_ticket, indent=2), encoding="utf-8")
    print(json.dumps(alert_ticket, indent=2))
    if args.fail_on_alert and triggered_alerts:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
