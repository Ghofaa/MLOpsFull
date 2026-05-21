"""Compute cumulative and sliding-window model performance metrics.

This script operationalizes the monitoring notebook concept of comparing
cumulative performance against sliding-window performance over time.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute cumulative and sliding-window F1 metrics.")
    parser.add_argument(
        "--input",
        default="artifacts/monitoring/performance_events.jsonl",
        help="Input events file (.csv, .json, .jsonl) with timestamp + f1 values.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/monitoring/performance_timeseries.json",
        help="Where to write computed performance timeseries.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=24,
        help="Sliding window size (number of observations).",
    )
    return parser.parse_args()


def load_events(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in {".jsonl", ".ndjson"}:
        df = pd.read_json(path, lines=True)
    elif suffix == ".json":
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            df = pd.DataFrame(obj)
        elif isinstance(obj, dict):
            if "events" in obj and isinstance(obj["events"], list):
                df = pd.DataFrame(obj["events"])
            else:
                # single-event JSON fallback
                df = pd.DataFrame([obj])
        else:
            raise ValueError("Unsupported JSON structure for performance events.")
    else:
        raise ValueError(f"Unsupported input format: {suffix}")

    if df.empty:
        return df

    # Support nested eval-style schema: overall.f1
    if "f1" not in df.columns and "overall" in df.columns:
        df["f1"] = df["overall"].apply(
            lambda x: x.get("f1") if isinstance(x, dict) else None
        )

    if "timestamp" not in df.columns:
        # Fallback synthetic ordering if timestamps absent
        df["timestamp"] = pd.RangeIndex(start=0, stop=len(df), step=1).astype(str)

    required = {"timestamp", "f1"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    return df


def compute_metrics(df: pd.DataFrame, window_size: int) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["f1"])
    df["f1"] = pd.to_numeric(df["f1"], errors="coerce")
    df = df.dropna(subset=["f1"])

    if not df["timestamp"].isna().all():
        df = df.sort_values("timestamp")
    df = df.reset_index(drop=True)

    if df.empty:
        return df

    df["cumulative_f1"] = df["f1"].expanding(min_periods=1).mean()
    df["sliding_f1"] = df["f1"].rolling(window=window_size, min_periods=1).mean()
    return df


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        report = {
            "success": False,
            "error": f"Input file not found: {input_path}",
            "input": str(input_path),
            "window_size": int(args.window_size),
        }
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    df = load_events(input_path)
    df_metrics = compute_metrics(df, window_size=args.window_size)

    if df_metrics.empty:
        report = {
            "success": False,
            "error": "No valid f1 events available after normalization.",
            "input": str(input_path),
            "window_size": int(args.window_size),
            "num_events": 0,
        }
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    records = []
    for row in df_metrics.itertuples(index=False):
        ts_val = row.timestamp
        ts = ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val)
        records.append(
            {
                "timestamp": ts,
                "f1": float(row.f1),
                "cumulative_f1": float(row.cumulative_f1),
                "sliding_f1": float(row.sliding_f1),
            }
        )

    summary = {
        "latest_f1": records[-1]["f1"],
        "latest_cumulative_f1": records[-1]["cumulative_f1"],
        "latest_sliding_f1": records[-1]["sliding_f1"],
        "num_events": len(records),
        "window_size": int(args.window_size),
    }

    report = {
        "success": True,
        "input": str(input_path),
        "summary": summary,
        "events": records,
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
