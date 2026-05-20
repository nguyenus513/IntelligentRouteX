param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v1.0.3-external-seed-no-regress-recovery")
$ErrorActionPreference="Stop"
powershell -ExecutionPolicy Bypass -File scripts/run-v1.0.2-benchmark-suite-certification-gate.ps1 -BaseUrl $BaseUrl -OutputDir $OutputDir
exit $LASTEXITCODE
