# Monitoring

Production monitoring uses **three layers**: Prometheus metrics, structured logs, and Jenkins batch monitoring scripts.

## Prometheus and Grafana

The API exposes Prometheus metrics at `GET /metrics` (see `madewithml/monitoring_metrics.py`).

Start the observability stack:

```powershell
docker compose up -d prometheus grafana
```

Open Grafana at `http://localhost:3000` (admin / admin). Dashboard: **MLOps → MLOpsFull API And Model Monitoring**.

Generate traffic:

```powershell
python scripts/send_monitoring_traffic.py --url http://localhost:8000/predict/ --requests 50
```

## Logging and Alibi drift

Logging is configured in `madewithml/config.py`:

| Log file | Level | Purpose |
|---|---|---|
| `logs/info.log` | INFO | General runtime and `request_metrics` events |
| `logs/error.log` | ERROR / warnings | Errors and drift alerts |

On startup, `madewithml/serve.py` initializes **KSDrift** and **ChiSquareDrift** from `datasets/dataset.csv` (or `X_train_reference.npy`). Each `/predict/` request runs drift checks; alerts are appended to `logs/error.log` without blocking inference.

## Jenkins monitoring stages (main branch)

After the quality gate on `main`:

| Script | Output |
|--------|--------|
| `monitor_expectations.py` | `artifacts/monitoring/expectations_report.json` |
| `monitor_sliding_metrics.py` | `artifacts/monitoring/performance_timeseries.json` |
| `monitor_alerts.py` | `artifacts/alerts/latest_alert.json` |
| `monitor_act.py` | `artifacts/alerts/action_decision.json` |

## Prediction monitoring block

`POST /predict/` includes a `monitoring` summary (class counts, confidence, `other` rate) for dashboards and reports.

## Helpers

`madewithml/monitoring.py` provides validation, summarization, and lightweight drift statistics used in tests and documentation.

## Operational checklist

1. Start API: `python -m madewithml.serve --run_id <RUN_ID> --backend fastapi`
2. Confirm `/metrics` returns `mlopsfull_requests_total`
3. Run traffic script or send manual predictions
4. Check Grafana panels and `logs/error.log` for drift
5. Review Jenkins `artifacts/monitoring/` and `artifacts/alerts/` on `main` builds
