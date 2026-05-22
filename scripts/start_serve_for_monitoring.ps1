# Start FastAPI for local Grafana/Prometheus (Jenkins model + venv, project logs).
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot

$jenkinsRoot = "C:\ProgramData\Jenkins\.jenkins\workspace\mlops-cicd"
$localPython = Join-Path $projectRoot "venv\Scripts\python.exe"
$jenkinsPython = Join-Path $jenkinsRoot "venv\Scripts\python.exe"
$python = if (Test-Path $jenkinsPython) { $jenkinsPython } else { $localPython }
$efs = Join-Path $jenkinsRoot "efs"
$summary = Join-Path $jenkinsRoot "artifacts\quality_gate_summary.json"

if (-not (Test-Path $python)) {
    throw "Jenkins venv not found: $python"
}
if (-not (Test-Path $summary)) {
    throw "Missing quality_gate_summary.json at $summary"
}

$runId = (Get-Content $summary -Raw | ConvertFrom-Json).run_id
$env:GITHUB_USERNAME = if ($env:GITHUB_USERNAME) { $env:GITHUB_USERNAME } else { "Ghofaa" }
$env:MLOPS_STORAGE_DIR = $efs
$env:MLOPS_INSECURE_SSL = "1"
$env:HF_HOME = Join-Path $env:USERPROFILE ".cache\huggingface"

Write-Host "Starting serve run_id=$runId (storage=$efs)"
Write-Host "Set MLOPS_INSECURE_SSL=1 only for local dev when HuggingFace SSL fails."
& $python -m madewithml.serve --run_id $runId --backend fastapi
