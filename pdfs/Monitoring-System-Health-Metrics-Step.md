# Monitoring Step: System Health + Expectations + Drift + Sliding-Window + Alerts + Act + CI/CD Integration

## 1) Objective

This step implements seven monitoring layers requested in `4.Monitoring.pdf`:

1. **System health metrics** from serving endpoints.
2. **Data expectations validation** for incoming payload schema/quality.
3. **Notebook-aligned drift detection** (KS + ChiSquare) based on token-count features.
4. **Sliding-window performance monitoring** (cumulative vs rolling F1).
5. **Alert rule engine** combining drift and performance thresholds.
6. **Act workflow** for retrain/no-retrain decisions.
7. **CI/CD integration** to run monitoring checks automatically on main pushes.

The goal is to capture health telemetry for:

- request latency,
- request throughput (derivable from request count over time),
- request errors (error rate and failure details).

And to validate core expectations before drift analysis:

- required columns exist (`title`, `description`),
- non-null constraints,
- string type constraints,
- length-range sanity checks.

---

## 2) Files added/updated

### `madewithml/serve.py`

Added request-metrics instrumentation for the following endpoints:

- `GET /`
- `GET /run_id/`
- `POST /evaluate/`
- `POST /predict/`

Also upgraded drift logic from toy length features to notebook-aligned methods:

- `KSDrift` on token-count numeric feature (univariate drift)
- `ChiSquareDrift` on categorical token-size buckets (`small`, `medium`, `large`)

### `scripts/monitor_expectations.py`

Added a standalone expectations checker script that:

- loads input data (`csv`, `json`, `jsonl`),
- validates schema + quality with Great Expectations,
- writes structured output to `artifacts/monitoring/expectations_report.json`,
- returns non-zero exit code if validation fails.

### `scripts/monitor_sliding_metrics.py`

Added a sliding-window metrics script that:

- loads performance event data (`csv`, `json`, `jsonl`),
- computes cumulative F1 and rolling/sliding F1,
- writes `artifacts/monitoring/performance_timeseries.json`,
- returns non-zero exit code if no valid performance events are available.

### `scripts/monitor_alerts.py`

Added an alert-rule engine script that:

- reads drift events from `logs/error.log`,
- reads sliding metrics from `artifacts/monitoring/performance_timeseries.json`,
- applies configurable threshold rules (KS, Chi-square, sliding F1),
- writes alert ticket to `artifacts/alerts/latest_alert.json`,
- returns non-zero when alerts are triggered.

### `scripts/monitor_act.py`

Added an Act-workflow script that:

- reads `artifacts/alerts/latest_alert.json`,
- reads `artifacts/monitoring/expectations_report.json`,
- applies decision logic (`retrain_recommended` vs `monitor_only`),
- writes decision ticket to `artifacts/alerts/action_decision.json`,
- optionally writes retrain trigger file `artifacts/alerts/retrain.trigger`.

### `Jenkinsfile`

Added monitoring integration stage:

- `Monitoring Rules + Act (main push)`

This stage executes:

1. `monitor_expectations.py`
2. `monitor_sliding_metrics.py`
3. `monitor_alerts.py`
4. `monitor_act.py`

with fail-fast checks (`if errorlevel 1 exit /b 1`) and explicit artifact archiving.

---

## 3) What was implemented

### 3.1 Request metrics helper

Introduced a helper method:

- `_log_request_metrics(endpoint, start_time, http_status, status, error)`

This method computes:

- `latency_ms`
- `timestamp`
- `endpoint`
- `run_id`
- `status` (`ok` or `error`)
- `http_status`

On errors, it also logs:

- `error_type`
- `error_message`

The payload is logged as structured JSON.

### 3.2 Endpoint-level timing + error capture

Each endpoint now:

1. records `start_time` with `time.perf_counter()`,
2. runs endpoint logic inside `try/except`,
3. logs success metrics on completion,
4. logs error metrics on exception and re-raises.

This provides operational visibility without changing endpoint outputs.

### 3.3 Expectations validation script

Implemented `scripts/monitor_expectations.py` with:

1. Input parsing:
   - `--input` (default `datasets/holdout.csv`)
   - `--output` (default `artifacts/monitoring/expectations_report.json`)
   - `--mostly` threshold (default `1.0`)
2. Dataset loading:
   - supports `.csv`, `.json`, `.jsonl/.ndjson`
3. Great Expectations checks:
   - columns exist: `title`, `description`
   - non-null values
   - type is `str`
   - value lengths in acceptable ranges
4. Structured report output with:
   - `success`
   - `statistics`
   - `results`
   - input metadata (`input`, `num_rows`, `mostly`)
5. CI-friendly exit code:
   - `0` when expectations pass
   - `1` when expectations fail

### 3.4 Drift upgrade to notebook-aligned features (Step 4)

Implemented in `madewithml/serve.py`:

1. Added token-count feature extraction from request text:
   - `num_tokens = len((title + " " + description).split())`
2. Added reference token-count loading strategy:
   - primary source: `datasets/dataset.csv` (`title`, `description`)
   - fallback: existing `X_train_reference.npy` for backward compatibility
3. Added **two detectors**:
   - `KSDrift(reference_token_counts, p_val=0.01)` for numeric drift
   - `ChiSquareDrift(reference_buckets, p_val=0.01)` for categorical drift
4. Added token-size bucketization:
   - `small` (`<=10`)
   - `medium` (`<=25`)
   - `large` (`>25`)
5. During `/predict/`, run both detectors and trigger drift alert if either signals drift.
6. Log structured drift payload to `logs/error.log` with:
   - KS/Chi drift flags
   - p-values
   - distances
   - incoming token counts and bucket labels

### 3.5 Sliding-window monitoring script (Step 5)

Implemented `scripts/monitor_sliding_metrics.py`:

1. Input parsing:
   - `--input` (default `artifacts/monitoring/performance_events.jsonl`)
   - `--output` (default `artifacts/monitoring/performance_timeseries.json`)
   - `--window-size` (default `24`)
2. Event normalization:
   - supports `f1` directly
   - supports nested `overall.f1` style records
3. Time-series computation:
   - `cumulative_f1` via expanding mean
   - `sliding_f1` via rolling window mean
4. Structured output:
   - `summary` (latest values + event count)
   - full per-event series for visualization
5. CI-friendly behavior:
   - exits `1` on missing input or invalid events
   - exits `0` on successful computation

### 3.6 Alerting rule engine (Step 6)

Implemented `scripts/monitor_alerts.py`:

1. Input parsing:
   - `--drift-log` (default `logs/error.log`)
   - `--performance` (default `artifacts/monitoring/performance_timeseries.json`)
   - `--output` (default `artifacts/alerts/latest_alert.json`)
2. Rule thresholds:
   - `--ks-p-threshold` (default `0.01`)
   - `--chi-p-threshold` (default `0.01`)
   - `--sliding-f1-threshold` (default `0.55`)
3. Drift signal extraction:
   - parses recent `drift_alert` JSON events from logs
   - checks `ks_is_drift` / `chi_is_drift` with p-value thresholds
4. Performance signal extraction:
   - reads latest `sliding_f1` summary
   - triggers regression alert if below threshold
5. Alert ticket output:
   - `triggered_alerts`
   - `severity` (`none`, `medium`, `high`)
   - thresholds and measured values
   - context for inspection/RCA
6. CI-friendly exit code:
   - `0` if no alerts
   - `1` if one or more alerts are triggered

### 3.7 Act workflow (Step 8)

Implemented `scripts/monitor_act.py`:

1. Inputs:
   - alert ticket (`artifacts/alerts/latest_alert.json`)
   - expectations report (`artifacts/monitoring/expectations_report.json`)
2. Decision logic:
   - if expectations fail -> block retraining and require data-quality remediation
   - if alert severity is high -> recommend retraining
   - if sliding F1 regression is present and expectations pass -> recommend retraining
   - otherwise -> monitor-only state
3. Output ticket:
   - `artifacts/alerts/action_decision.json`
   - includes status, reasons, and recommended actions
4. Trigger artifact:
   - create `artifacts/alerts/retrain.trigger` when retraining is recommended
   - remove stale trigger file when retraining is not recommended
5. CI-friendly exit code:
   - `1` when retraining is recommended (action required)
   - `0` for monitor-only decisions

### 3.8 Monitoring integration in Jenkins (Step 9)

Integrated monitoring scripts into `Jenkinsfile` with a dedicated main-only stage:

- `Monitoring Rules + Act (main push)`

Execution order:

1. Ensure artifact directories exist:
   - `artifacts/monitoring`
   - `artifacts/alerts`
2. Run expectations checker:
   - `monitor_expectations.py`
3. Run sliding metrics:
   - `monitor_sliding_metrics.py` using `artifacts/eval_results.json`
4. Run alert engine:
   - `monitor_alerts.py`
5. Run act workflow:
   - `monitor_act.py`

Reliability controls:

- each critical command is followed by `if errorlevel 1 exit /b 1`
- stage fails immediately on invalid monitoring artifacts
- all monitoring outputs are archived in post actions

---

## 4) Example structured log records

### Success event (`logs/info.log`)

```json
{
  "event": "request_metrics",
  "timestamp": "2026-05-21T22:40:00.123456",
  "endpoint": "/predict/",
  "run_id": "abc123...",
  "status": "ok",
  "http_status": 200,
  "latency_ms": 37.42
}
```

### Error event (`logs/error.log`)

```json
{
  "event": "request_metrics",
  "timestamp": "2026-05-21T22:41:10.654321",
  "endpoint": "/evaluate/",
  "run_id": "abc123...",
  "status": "error",
  "http_status": 500,
  "latency_ms": 120.81,
  "error_type": "ValueError",
  "error_message": "..."
}
```

---

## 5) How this maps to `4.Monitoring.pdf`

This step directly covers two Monitoring lesson requirements:

### 5.1 System health

- **latency** -> `latency_ms` per request
- **throughput** -> count of `request_metrics` events over time
- **error rate** -> count of `status="error"` vs total requests

These are the foundational service-health indicators before higher-level drift and model-performance monitoring.

### 5.2 Expectations (rule-based validation)

The Monitoring lesson explicitly recommends expectation checks for:

- missing values,
- data types,
- value ranges.

`scripts/monitor_expectations.py` operationalizes this recommendation and produces a reusable report artifact.

### 5.3 Drift measurement alignment with teacher notebook

This upgrade aligns directly with `Monitoring-ML/monitoring.ipynb`:

- **Univariate KS drift** on token-count feature (`num_tokens`)
- **Categorical Chi-square drift** on token-count buckets

This replaces the earlier toy-only length heuristic and brings the serving monitor closer to course methodology.

### 5.4 Performance over time (cumulative vs sliding)

The Monitoring notebook stresses that cumulative-only metrics can hide degradation.  
`scripts/monitor_sliding_metrics.py` operationalizes this by producing both:

- **cumulative F1**
- **sliding-window F1**

This directly aligns with the notebook/PDF recommendation to inspect performance over significant windows (e.g., daily).

### 5.5 Alert phase implementation

The PDF requires moving from measurement to actionability:

- detect issues,
- trigger alerts,
- inspect context before acting.

`scripts/monitor_alerts.py` implements this Alert phase by converting drift/performance signals into a structured alert ticket with thresholds, measurements, and context.

### 5.6 Act phase implementation

The PDF requires deciding what to do after an alert (inspect/act loop):

- verify data expectations,
- assess drift/performance severity,
- choose retrain vs monitor,
- emit actionable outputs.

`scripts/monitor_act.py` implements this with deterministic decision rules and explicit artifacts for automation.

### 5.7 Production integration requirement

The Monitoring lesson emphasizes operationalization in production workflows.  
Step 9 satisfies this by executing monitor/alert/act scripts automatically in Jenkins on main-branch deployments.

---

## 6) Validation checklist

1. Start service with valid `run_id`.
2. Call `/`, `/run_id/`, `/predict/`, `/evaluate/`.
3. Confirm `request_metrics` JSON lines appear in `logs/info.log`.
4. Trigger one failing request (invalid payload/path).
5. Confirm error JSON appears in `logs/error.log` with `error_type` and `error_message`.
6. Run expectations checker:
   - `python scripts/monitor_expectations.py --input datasets/holdout.csv`
7. Confirm report exists at:
   - `artifacts/monitoring/expectations_report.json`
8. Confirm script exits non-zero when expectations fail (e.g., missing required column).
9. Send `/predict/` request windows that alter token-count distribution.
10. Confirm drift payload appears in `logs/error.log` with both:
   - `ks_*` fields (`ks_is_drift`, `ks_p_val`, `ks_distance`)
   - `chi_*` fields (`chi_is_drift`, `chi_p_val`, `chi_distance`)
11. Run sliding metrics script:
    - `python scripts/monitor_sliding_metrics.py --input artifacts/monitoring/performance_events.jsonl --window-size 24`
12. Confirm output exists:
    - `artifacts/monitoring/performance_timeseries.json`
13. Confirm report includes:
    - `summary.latest_cumulative_f1`
    - `summary.latest_sliding_f1`
14. Run alert engine:
    - `python scripts/monitor_alerts.py`
15. Confirm alert ticket exists:
    - `artifacts/alerts/latest_alert.json`
16. Confirm ticket fields include:
    - `triggered_alerts`
    - `severity`
    - `thresholds`
    - `measurements`
17. Confirm script exit code:
    - `0` when no alert
    - `1` when alerts are triggered
18. Run act workflow:
    - `python scripts/monitor_act.py`
19. Confirm decision output exists:
    - `artifacts/alerts/action_decision.json`
20. Confirm decision fields include:
    - `status`
    - `retrain_recommended`
    - `reason`
    - `recommended_actions`
21. Confirm retrain trigger behavior:
    - `artifacts/alerts/retrain.trigger` is created when retraining is recommended
    - trigger file is absent for monitor-only decisions
22. Trigger Jenkins main build and confirm stage executes:
    - `Monitoring Rules + Act (main push)`
23. Confirm build fails if any monitoring command fails.
24. Confirm archived outputs include:
    - `artifacts/monitoring/expectations_report.json`
    - `artifacts/monitoring/performance_timeseries.json`
    - `artifacts/alerts/latest_alert.json`
    - `artifacts/alerts/action_decision.json`

---

## 7) Output location and visualization path

### Current output

- `logs/info.log`
- `logs/error.log`
- `artifacts/monitoring/expectations_report.json`
- `artifacts/monitoring/performance_timeseries.json`
- `artifacts/alerts/latest_alert.json`
- `artifacts/alerts/action_decision.json`
- `artifacts/alerts/retrain.trigger` (conditional)
- Jenkins archived monitoring artifacts from `post { always { ... } }`

### How to visualize (next step)

These structured logs can be ingested into monitoring tools (e.g., Grafana stack with Loki/Promtail, or transformed to Prometheus metrics) to build dashboards for:

- p50/p95 latency by endpoint,
- requests per minute,
- error count/rate over time.

This step intentionally focuses on **instrumentation and data generation**; dashboard wiring is the next layer.

---

## 8) Step-by-step usage for this expectations step

1. Activate environment:
   - `.\venv\Scripts\Activate.ps1`
2. Run on reference file:
   - `python scripts/monitor_expectations.py --input datasets/holdout.csv`
3. Inspect report:
   - `artifacts/monitoring/expectations_report.json`
4. (Optional) tighten tolerance:
   - `python scripts/monitor_expectations.py --input datasets/holdout.csv --mostly 0.98`
5. Integrate into CI/CD later as a monitoring stage and archive the report JSON.

---

## 9) What Step 4 is implementing and adding

Step 4 improves drift monitoring from a minimal demo to a notebook-consistent implementation:

- **Implements** statistically grounded univariate + categorical drift checks.
- **Adds** richer drift evidence (p-values, distances, bucketed distributions) for alerting and RCA.
- **Improves** interpretability: drift decisions now tie to token-count behavior rather than only raw character lengths.

Practical impact:

- better alignment with course deliverables,
- better quality of monitoring signals,
- stronger foundation for upcoming alert/inspect/act steps and Grafana visualization.

---

## 10) What Step 5 is implementing and adding

Step 5 adds **performance-over-time observability** so you can detect degradation that cumulative metrics can hide.

It implements:

- cumulative F1 tracking,
- sliding-window F1 tracking,
- structured timeseries output for dashboarding.

It adds:

- `scripts/monitor_sliding_metrics.py`
- `artifacts/monitoring/performance_timeseries.json`

Practical impact:

- catches recent model regression earlier,
- provides notebook-aligned evidence for monitoring deliverables,
- gives direct Grafana-ready inputs for trend panels.

---

## 11) What Step 6 is implementing and adding

Step 6 adds the **Alert phase** from the monitoring lifecycle.

It implements:

- threshold-based drift alerts (KS + ChiSquare),
- threshold-based sliding-F1 regression alerts,
- severity classification and inspection-ready alert ticket output.

It adds:

- `scripts/monitor_alerts.py`
- `artifacts/alerts/latest_alert.json`

Practical impact:

- converts raw monitoring signals into actionable incidents,
- enables consistent alerting policy in CI/CD and production,
- prepares the project for Inspect/Act automation and Grafana alert panels.

---

## 12) What Step 8 is implementing and adding

Step 8 adds the **Act phase** from the monitoring lifecycle.

It implements:

- deterministic decision policy from alert + expectations context,
- retrain/no-retrain recommendation output,
- optional trigger artifact for downstream automation.

It adds:

- `scripts/monitor_act.py`
- `artifacts/alerts/action_decision.json`
- `artifacts/alerts/retrain.trigger` (when action required)

Practical impact:

- closes the monitoring loop from detection to decision,
- prevents ad-hoc/manual decisions after alerts,
- provides auditable action outcomes for CI/CD and reporting.

---

## 13) What Step 9 is implementing and adding

Step 9 integrates monitoring into the CI/CD pipeline so monitoring is no longer manual.

It implements:

- automatic execution of expectations + sliding metrics + alert + act scripts on `main`,
- fail-fast pipeline behavior for monitoring failures,
- explicit archival of monitoring artifacts for traceability.

It adds:

- Jenkins stage: `Monitoring Rules + Act (main push)`
- monitoring artifact archiving in `post` block

Practical impact:

- operationalizes monitoring as part of deployment governance,
- prevents silent monitoring regressions,
- produces reproducible evidence for grading, audits, and dashboards.

