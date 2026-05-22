# Verify API metrics -> Prometheus -> Grafana readiness.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Wait-HttpOk($url, $attempts = 60, $delaySec = 3) {
    for ($i = 1; $i -le $attempts; $i++) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { return $true }
        } catch {}
        Write-Host "Waiting for $url ($i/$attempts)..."
        Start-Sleep -Seconds $delaySec
    }
    return $false
}

Write-Host "=== Docker observability ==="
docker compose up -d prometheus grafana | Out-Host
docker compose restart prometheus | Out-Host
Start-Sleep -Seconds 5

Write-Host "=== API health ==="
if (-not (Wait-HttpOk "http://127.0.0.1:8000/metrics")) {
    throw "API /metrics not reachable on :8000. Start scripts/start_serve_for_monitoring.ps1 in another terminal."
}

$metrics = (Invoke-WebRequest -Uri "http://127.0.0.1:8000/metrics" -UseBasicParsing).Content
if ($metrics -notmatch "mlopsfull_requests_total") {
    throw "Metrics endpoint missing mlopsfull_requests_total"
}
Write-Host "API metrics OK"

Write-Host "=== Traffic ==="
python scripts/send_monitoring_traffic.py --url http://127.0.0.1:8000/predict/ --requests 30

Write-Host "=== Prometheus target ==="
$targets = Invoke-RestMethod -Uri "http://127.0.0.1:9090/api/v1/targets"
$api = $targets.data.activeTargets | Where-Object { $_.labels.job -eq "mlopsfull-api" }
if ($api.health -ne "up") {
    throw "Prometheus job mlopsfull-api is not UP: $($api.lastError)"
}
Write-Host "Prometheus mlopsfull-api UP"

Write-Host "=== Grafana ==="
Write-Host "Open http://127.0.0.1:3000 (admin/admin) -> MLOps -> MLOpsFull API And Model Monitoring"
Write-Host "MONITORING STACK READY"
