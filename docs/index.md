# Made With ML — MLOps

This project classifies machine learning projects into tags (for example `computer-vision`, `natural-language-processing`, `mlops`) using a fine-tuned SciBERT model trained with Ray Train and tracked in MLflow.

## What this repo contains

- **Training** — distributed training with Ray and MLflow experiment tracking
- **Evaluation** — holdout metrics including overall, per-class, and slice-based F1
- **Serving** — FastAPI + Ray Serve deployment with drift monitoring
- **CI/CD** — Jenkins pipeline with PR validation, quality gate, and main-branch docs build

## Documentation sections

| Section | Description |
|---|---|
| [Getting Started](getting-started.md) | Install dependencies and run train, evaluate, serve, and tune |
| [CI/CD](ci-cd.md) | Jenkins workflow for pull requests and main-branch delivery |
| [Monitoring](monitoring.md) | Production logging and drift detection |
| [API Reference](api/train.md) | Auto-generated docs from `madewithml` module docstrings |

## Requirements

- Python 3.10 (recommended for the pinned dependency stack)
- Environment variable `GITHUB_USERNAME` for Ray runtime and MLflow storage paths
