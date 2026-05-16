param(
  [string]$BaseUrl = "http://localhost:8080",
  [string[]]$Datasets = @(
    "raw-s",
    "raw-m",
    "random-spread",
    "driver-scarcity-case",
    "tight-deadline-case",
    "wide-deadline-case",
    "driver-imbalanced-case",
    "many-orders-few-drivers",
    "few-orders-many-drivers",
    "opposite-direction-dropoffs",
    "clustered-pickups-random-dropoffs",
    "random-pickups-clustered-dropoffs",
    "long-tail-distance",
    "tight-capacity",
    "high-priority-orders",
    "active-route-insertion",
    "driver-location-shift",
    "deferred-order-aging",
    "rescue-like-rebalance",
    "high-density-lunch-rush"
  ),
  [int]$DatasetTimeoutSeconds = 420,
  [string]$OutputDir = "artifacts/test-reports/quality"
)

$ErrorActionPreference = "Stop"
& "$PSScriptRoot/run-clean-cache-gate.ps1" `
  -BaseUrl $BaseUrl `
  -Datasets $Datasets `
  -Mode "QUALITY_BENCHMARK" `
  -DatasetTimeoutSeconds $DatasetTimeoutSeconds `
  -OutputDir $OutputDir
