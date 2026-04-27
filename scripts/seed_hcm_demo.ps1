$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $repoRoot "functions")

if (-not $env:FIRESTORE_EMULATOR_HOST) {
    $env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8080"
}

if (-not $env:GCLOUD_PROJECT) {
    $env:GCLOUD_PROJECT = "routefood-demo"
}

npm run seed:demo
