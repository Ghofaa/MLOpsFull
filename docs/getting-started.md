# Getting Started

## Installation

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

Set your GitHub username (used by Ray and MLflow storage paths):

```bash
# Windows PowerShell
$env:GITHUB_USERNAME = "your-username"

# Linux/macOS
export GITHUB_USERNAME=your-username
```

## Datasets

| File | Purpose |
|---|---|
| `datasets/dataset.csv` | Training data |
| `datasets/holdout.csv` | Evaluation holdout |
| `datasets/projects.csv` | Raw project records |
| `datasets/tags.csv` | Project tag labels |

## Train

```bash
python -m madewithml.train \
  --experiment-name my-experiment \
  --dataset-loc datasets/dataset.csv \
  --num-samples 256 \
  --num-epochs 3 \
  --batch-size 16 \
  --results-fp artifacts/train_results.json
```

Training logs the MLflow `run_id` in the results JSON. Use that ID for evaluation and serving.

## Evaluate

```bash
python -m madewithml.evaluate \
  --run-id <run_id> \
  --dataset-loc datasets/holdout.csv \
  --results-fp artifacts/eval_results.json
```

## Serve

```bash
python -m madewithml.serve --run-id <run_id> --threshold 0.9
```

The service exposes:

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check |
| `/run_id/` | GET | Returns the deployed run ID |
| `/predict/` | POST | Classify a project from `title` and `description` |
| `/evaluate/` | POST | Run evaluation on a dataset path |

Example prediction request:

```bash
curl -X POST http://127.0.0.1:8000/predict/ \
  -H "Content-Type: application/json" \
  -d '{"title": "My project", "description": "A deep learning classifier."}'
```

## Tune

Run hyperparameter search with Ray Tune:

```bash
python -m madewithml.tune tune-models \
  --experiment-name tune-experiment \
  --dataset-loc datasets/dataset.csv \
  --num-runs 2 \
  --num-samples 256 \
  --num-epochs 1
```

## Build documentation locally

```bash
# From project root
set PYTHONPATH=.          # Windows cmd
$env:PYTHONPATH = "."     # PowerShell
export PYTHONPATH=.       # Linux/macOS

mkdocs build --strict
mkdocs serve              # preview at http://127.0.0.1:8000
```
