# Jenkins CI/CD Implementation Log

Project: `MLOpsFull`  
Pipeline file: [Jenkinsfile](../Jenkinsfile)  
Default branch: `main`  
Model API: `http://localhost:8000`

## Purpose

This project uses a **Windows Jenkins agent with a per-build Python virtual environment**. The pipeline follows the course CI/CD model:

- **Pull requests to `main`** run validation and a lightweight train/evaluate quality gate.
- **Pushes to `main`** run the same gate, then deployment smoke tests and documentation build, then monitoring rule stages.

## Pipeline stages

| Stage | When | Action |
|-------|------|--------|
| Checkout | Always | Clone repository |
| Setup Python | Always | Create `venv`, install `requirements.txt`, pin setuptools/wheel for Ray |
| CI Workloads | PR only | `train --help`, `evaluate --help` |
| MLOps Train + Evaluate Gate | PR and main | `scripts/ci_train_eval_gate.py` |
| CD Serve + Docs | main push | `scripts/ci_deploy_smoke.py` (FastAPI) + `mkdocs build` |
| Monitoring Rules + Act | main push | expectations, sliding metrics, alerts, act scripts |

## Quality gate

`scripts/ci_train_eval_gate.py` writes:

| Artifact | Purpose |
|----------|---------|
| `artifacts/train_results.json` | Training output and `run_id` |
| `artifacts/eval_results.json` | Holdout metrics |
| `artifacts/quality_gate_summary.json` | F1 vs threshold decision |

Jenkins fails the build when weighted F1 is below `F1_THRESHOLD` (default `0.30`).

## Deployment smoke

`scripts/ci_deploy_smoke.py` starts the API with `--backend fastapi` and verifies:

- `GET /`
- `GET /run_id/`
- `GET /metrics` (Prometheus format)
- `POST /predict/`

Artifacts: `artifacts/deploy_smoke.json`, `artifacts/metrics_smoke.txt`.

## Optional local Docker

For reproducible runtime and Prometheus/Grafana demos:

```powershell
docker compose up -d prometheus grafana
docker compose --profile serve up -d mlopsfull-serve
```

Set `RUN_ID` to a trained MLflow run before starting the serve profile.

## Parameters (Jenkinsfile environment)

| Variable | Default | Purpose |
|----------|---------|---------|
| `F1_THRESHOLD` | `0.30` | Minimum weighted F1 |
| `CI_NUM_SAMPLES` | `256` | CI training sample size |
| `CI_NUM_EPOCHS` | `3` | CI training epochs |
| `CI_BATCH_SIZE` | `16` | CI batch size |
