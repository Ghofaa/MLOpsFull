# Monitoring Implementation Log

Project: `MLOpsFull`  
Model API: `http://localhost:8000`  
Prometheus: `http://localhost:9090`  
Grafana: `http://localhost:3000` (admin / admin)

## Monitoring layers

| Layer | Implementation | Consumer |
|-------|----------------|----------|
| API + model metrics | `GET /metrics` via `monitoring_metrics.py` | Prometheus, Grafana |
| Log-based health | JSON `request_metrics` in `logs/info.log` | Log review, `monitor_alerts.py` |
| Alibi drift | KSDrift + ChiSquareDrift in `serve.py` | `logs/error.log`, `monitor_alerts.py` |
| Batch monitoring jobs | `scripts/monitor_*.py` | Jenkins `main` pipeline stages |
| Drift helpers | `monitoring.py` | Tests, reports, future scheduled jobs |

## Prometheus metrics

| Metric | Meaning |
|--------|---------|
| `mlopsfull_requests_total` | Requests by endpoint, method, status |
| `mlopsfull_request_latency_seconds` | Latency for predict/evaluate |
| `mlopsfull_predictions_total` | Predictions by class |
| `mlopsfull_prediction_confidence` | Confidence distribution |
| `mlopsfull_input_text_length_tokens` | Input token length |
| `mlopsfull_other_prediction_rate` | Latest `other` class rate |
| `mlopsfull_input_validation_failures_total` | Empty title/description counts |

## Prediction response summary

`POST /predict/` returns:

```json
{
  "results": [...],
  "monitoring": {
    "total": 1,
    "class_counts": {},
    "avg_confidence": 0.0,
    "other_rate": 0.0
  }
}
```

## Local observability stack

```powershell
docker compose up -d prometheus grafana
# Start API (venv or compose serve profile), then:
python scripts/send_monitoring_traffic.py --url http://localhost:8000/predict/ --requests 50
```

Grafana dashboard: **MLOps → MLOpsFull API And Model Monitoring**.

## Jenkins monitoring stages (main)

After train/evaluate on `main`:

1. `monitor_expectations.py` → `artifacts/monitoring/expectations_report.json`
2. `monitor_sliding_metrics.py` → `artifacts/monitoring/performance_timeseries.json`
3. `monitor_alerts.py` → `artifacts/alerts/latest_alert.json`
4. `monitor_act.py` → `artifacts/alerts/action_decision.json`

## Serving backends

```bash
python -m madewithml.serve --run_id <RUN_ID> --backend fastapi
python -m madewithml.serve --run_id <RUN_ID> --backend ray-serve
```

FastAPI is the default for Jenkins smoke tests and Docker Compose.
