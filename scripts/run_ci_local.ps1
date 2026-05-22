# Simulates Jenkins main-branch pipeline stages locally.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:GITHUB_USERNAME = if ($env:GITHUB_USERNAME) { $env:GITHUB_USERNAME } else { "ci-user" }
$env:PYTHONPATH = (Get-Location).Path

$python = if (Test-Path "venv\Scripts\python.exe") { "venv\Scripts\python.exe" } else { "python" }

Write-Host "=== pytest ==="
& $python -m pytest tests -q

Write-Host "=== ci_train_eval_gate ==="
New-Item -ItemType Directory -Force -Path artifacts | Out-Null
& $python scripts/ci_train_eval_gate.py `
    --dataset datasets/dataset.csv `
    --holdout datasets/holdout.csv `
    --results-dir artifacts `
    --num-samples 100 `
    --num-epochs 1 `
    --batch-size 16 `
    --f1-threshold 0.15
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== ci_deploy_smoke ==="
& $python scripts/ci_deploy_smoke.py `
    --summary artifacts/quality_gate_summary.json `
    --report artifacts/deploy_smoke.json `
    --metrics-report artifacts/metrics_smoke.txt `
    --backend fastapi
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== mkdocs build ==="
& $python -m mkdocs build --strict
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== monitor_expectations ==="
New-Item -ItemType Directory -Force -Path artifacts/monitoring, artifacts/alerts | Out-Null
& $python scripts/monitor_expectations.py --input datasets/holdout.csv --output artifacts/monitoring/expectations_report.json
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== monitor_sliding_metrics ==="
& $python scripts/monitor_sliding_metrics.py --input artifacts/eval_results.json --output artifacts/monitoring/performance_timeseries.json --window-size 24
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== monitor_alerts ==="
& $python scripts/monitor_alerts.py --drift-log logs/error.log --performance artifacts/monitoring/performance_timeseries.json --output artifacts/alerts/latest_alert.json --sliding-f1-threshold 0.0
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== monitor_act ==="
& $python scripts/monitor_act.py --alert artifacts/alerts/latest_alert.json --expectations artifacts/monitoring/expectations_report.json --output artifacts/alerts/action_decision.json --trigger-file artifacts/alerts/retrain.trigger
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== ALL CI STAGES PASSED ==="
