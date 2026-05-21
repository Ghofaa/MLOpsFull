# Monitoring

Production monitoring is implemented in the serving layer through centralized logging and statistical drift detection.

## Logging

Logging is configured in `madewithml/config.py`:

| Log file | Level | Purpose |
|---|---|---|
| `logs/info.log` | INFO | General runtime events |
| `logs/error.log` | ERROR / warnings | Errors and drift alerts |

Logs use rotating file handlers (10 MB max, 10 backups).

## Drift detection

On service startup, `madewithml/serve.py` loads a reference baseline from `X_train_reference.npy` and initializes an Alibi Detect `KSDrift` detector (`p_val=0.01`).

For each `/predict/` request:

1. Extract monitoring features (title length, description length)
2. Run a Kolmogorov-Smirnov test against the reference distribution
3. If drift is detected, append a warning to `logs/error.log` with timestamp and p-values
4. Continue serving predictions (monitoring is non-blocking)

If `X_train_reference.npy` is missing, the service starts normally but drift checks are disabled.

## Operational checklist

1. Confirm drift detector initialization in startup logs
2. Send prediction requests to `/predict/`
3. Inspect `logs/error.log` for drift warnings after shifted inputs
4. Use drift signals to decide whether to investigate, refresh the reference window, or retrain

## Future improvements

- Richer embedding-based drift features
- Alerting (Slack, email) on sustained drift
- Automatic retraining trigger from CI/CD
- Dashboard integration (Grafana, Prometheus)
