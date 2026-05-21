"""Monitoring expectations check for production-style payloads.

Validates schema and basic data quality constraints for title/description
features and writes a structured JSON report for CI/CD artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import great_expectations as ge
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate input expectations for monitoring.")
    parser.add_argument(
        "--input",
        default="datasets/holdout.csv",
        help="Input file path (csv, json, or jsonl) containing title/description columns.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/monitoring/expectations_report.json",
        help="Where to write the expectations validation report.",
    )
    parser.add_argument(
        "--mostly",
        type=float,
        default=1.0,
        help="Great Expectations mostly threshold (0-1).",
    )
    return parser.parse_args()


def load_dataframe(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".json", ".js"}:
        return pd.read_json(path)
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported input format: {suffix}")


def validate(df: pd.DataFrame, mostly: float) -> dict:
    ge_df = ge.dataset.PandasDataset(df.copy())
    expected_columns = ["title", "description"]

    missing_columns = [col for col in expected_columns if col not in ge_df.columns]
    if missing_columns:
        return {
            "success": False,
            "statistics": {},
            "missing_columns": missing_columns,
            "results": [],
        }

    ge_df.expect_column_values_to_not_be_null("title", mostly=mostly)
    ge_df.expect_column_values_to_not_be_null("description", mostly=mostly)
    ge_df.expect_column_values_to_be_of_type("title", type_="str", mostly=mostly)
    ge_df.expect_column_values_to_be_of_type("description", type_="str", mostly=mostly)
    ge_df.expect_column_value_lengths_to_be_between(
        "title", min_value=1, max_value=300, mostly=mostly
    )
    ge_df.expect_column_value_lengths_to_be_between(
        "description", min_value=1, max_value=10000, mostly=mostly
    )

    suite = ge_df.get_expectation_suite()
    result = ge_df.validate(expectation_suite=suite, only_return_failures=False)

    return {
        "success": bool(result["success"]),
        "statistics": result["statistics"],
        "missing_columns": [],
        "results": result["results"],
    }


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict
    if not input_path.exists():
        report = {
            "success": False,
            "error": f"Input file not found: {input_path}",
            "input": str(input_path),
        }
    else:
        df = load_dataframe(input_path)
        report = validate(df=df, mostly=args.mostly)
        report["input"] = str(input_path)
        report["num_rows"] = int(len(df))
        report["mostly"] = float(args.mostly)

    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report.get("statistics", {}), indent=2))
    return 0 if report.get("success", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
