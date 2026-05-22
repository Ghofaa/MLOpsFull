# CI/CD

The Jenkins pipeline in `Jenkinsfile` implements the event-driven workflow described in the CI/CD lesson.

## Event triggers

| Event | Stages that run |
|---|---|
| Pull request to `main` | Setup → CI Workloads → Train + Evaluate Gate (PR) |
| Push to `main` (not a PR) | Setup → Train + Evaluate Gate (main) → CD Serve + Docs |

## Pipeline stages

### Setup Python

Creates a virtual environment, installs `requirements.txt`, and stabilizes the packaging toolchain for Ray.

### CI Workloads (PR validation)

Runs CLI smoke checks:

```bash
python -m madewithml.train --help
python -m madewithml.evaluate --help
```

### MLOps Train + Evaluate Gate

Runs `scripts/ci_train_eval_gate.py` which:

1. Trains a lightweight model on a CI sample (`CI_NUM_SAMPLES`, `CI_NUM_EPOCHS`, `CI_BATCH_SIZE`)
2. Evaluates on `datasets/holdout.csv`
3. Fails the build if weighted F1 is below `F1_THRESHOLD` (default `0.30`)
4. Writes artifacts to `artifacts/`:
   - `train_results.json`
   - `eval_results.json`
   - `quality_gate_summary.json`

### CD Serve + Docs (main push)

Runs only after a successful quality gate on `main`:

```bash
python scripts/ci_deploy_smoke.py --summary artifacts/quality_gate_summary.json --backend fastapi
mkdocs build --strict
```

The smoke test starts the FastAPI backend, verifies health, `run_id`, Prometheus `/metrics`, and a sample prediction. Artifacts:

- `artifacts/deploy_smoke.json`
- `artifacts/metrics_smoke.txt`

Built documentation is output to `site/` and archived as a Jenkins artifact.

## Artifacts

Each build archives:

- `Jenkinsfile`
- `requirements.txt`
- `artifacts/*.json`
- `artifacts/*.txt`
- `artifacts/monitoring/*.json`
- `artifacts/alerts/*.json`
- `site/**` (HTML documentation, main-branch builds only)

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `F1_THRESHOLD` | `0.30` | Minimum acceptable weighted F1 |
| `CI_NUM_SAMPLES` | `256` | Training sample size for CI |
| `CI_NUM_EPOCHS` | `3` | Epochs for CI training |
| `CI_BATCH_SIZE` | `16` | Batch size for CI training |
| `GITHUB_USERNAME` | `ci-user` | Ray runtime env fallback in CI |

## Continual learning

The pipeline enforces model-aware governance: low-quality models are blocked before the serve and docs stages run. Future extensions can trigger retraining from monitoring alerts or new data events.
