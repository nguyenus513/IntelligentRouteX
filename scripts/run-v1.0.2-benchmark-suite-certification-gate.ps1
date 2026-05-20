param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v1.0.2-benchmark-suite-certification")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$summary=[ordered]@{version="v1.0.3-external-seed-no-regress-recovery"; startedAt=(Get-Date).ToString("o")}
try {
  & .\gradlew.bat compileJava --no-daemon --console=plain | Out-Host; if($LASTEXITCODE -ne 0){ throw "compileJava failed" }; $summary.compileJava="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-solver-runtime-managed-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "solver-runtime") | Out-Host; if($LASTEXITCODE -ne 0){ throw "solver runtime failed" }; $summary.solverRuntime="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-allinone-benchmark-certification-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "smoke") | Out-Host; if($LASTEXITCODE -ne 0){ throw "all-in-one smoke failed" }; $summary.allInOneSmoke="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-allinone-compare-suite-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "compare-suite") | Out-Host; if($LASTEXITCODE -ne 0){ throw "compare suite failed" }; $summary.compareSuite="PASS"
  $suite=Get-Content (Join-Path $OutputDir "compare-suite/allinone-compare-suite-summary.json") -Raw | ConvertFrom-Json
  $summary.completed=$suite.completed
  $summary.irxVsVroom=$suite.irxVsVroom
  $summary.irxVsOrtools=$suite.irxVsOrtools
  $summary.lateRegression=$suite.lateRegression
  $summary.externalLateRegressionCases=$suite.externalLateRegressionCases
  $summary.dominanceFailures=$suite.dominanceFailures
  $summary.vroomAvailable=$suite.vroomAvailable
  $summary.ortoolsAvailable=$suite.ortoolsAvailable
  $summary.pyvrpAvailable=$suite.pyvrpAvailable
  $summary.overallPass=($summary.compileJava -eq "PASS" -and $summary.solverRuntime -eq "PASS" -and $summary.allInOneSmoke -eq "PASS" -and $summary.compareSuite -eq "PASS" -and $summary.irxVsVroom.losses -eq 0 -and $summary.irxVsOrtools.losses -eq 0 -and $summary.externalLateRegressionCases -eq 0 -and $summary.dominanceFailures -eq 0)
} catch { $summary.overallPass=$false; $summary.error=$_.Exception.Message }
$summary.finishedAt=(Get-Date).ToString("o")
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 50 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }



