param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v1.0.2.1-irx-benchmark-standard")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$summary=[ordered]@{version="v1.0.2.1-irx-benchmark-standard"; startedAt=(Get-Date).ToString("o")}
try {
  & .\gradlew.bat compileJava --no-daemon --console=plain | Out-Host; if($LASTEXITCODE -ne 0){ throw "compileJava failed" }; $summary.compileJava="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-solver-runtime-managed-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "solver-runtime") | Out-Host; if($LASTEXITCODE -ne 0){ throw "solver readiness failed" }; $summary.solverReadiness="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-standard-static-benchmark-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "static") | Out-Host; if($LASTEXITCODE -ne 0){ throw "static standard failed" }; $summary.staticGate="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-standard-dynamic-benchmark-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "dynamic") | Out-Host; if($LASTEXITCODE -ne 0){ throw "dynamic standard failed" }; $summary.dynamicGate="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-ml-contribution-benchmark-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "ml") | Out-Host; if($LASTEXITCODE -ne 0){ throw "ml contribution failed" }; $summary.mlGate="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-official-solomon-lilim-benchmark-gate.ps1 -OutputDir (Join-Path $OutputDir "official-solomon-lilim") | Out-Host; if($LASTEXITCODE -ne 0){ throw "official Solomon/LiLim failed" }; $summary.officialSolomonLiLimGate="PASS"
  $static=Get-Content (Join-Path $OutputDir "static/final-summary.json") -Raw | ConvertFrom-Json
  $dynamic=Get-Content (Join-Path $OutputDir "dynamic/final-summary.json") -Raw | ConvertFrom-Json
  $ml=Get-Content (Join-Path $OutputDir "ml/final-summary.json") -Raw | ConvertFrom-Json
  $official=Get-Content (Join-Path $OutputDir "official-solomon-lilim/final-summary.json") -Raw | ConvertFrom-Json
  $summary.runtimePass=$true
  $summary.qualityPass=[bool]$static.qualityPass
  $summary.static=@{completed=$static.completed; lossesVsBestExternal=$static.lossesVsBestExternal; lateRegressionVsBestExternal=$static.lateRegressionVsBestExternal; externalDominanceRollbacks=$static.externalDominanceRollbacks; improvedExternalCases=$static.improvedExternalCases}
  $summary.dynamic=@{completed=$dynamic.completed; status=$dynamic.status; cycleRuntimeP95=$dynamic.cycleRuntimeP95; hypotheses=$dynamic.hypothesisResults}
  $summary.mlContribution=@{status=$ml.status; lossesVsNoMl=$ml.lossesVsNoMl; qualityGainCases=$ml.qualityGainCases}
  $summary.officialSolomonLiLim=@{officialSmokePass=$official.officialSmokePass; fullThreeSolverOfficialPass=$official.fullThreeSolverOfficialPass; irxFeasible=$official.irxFeasible; ortoolsFeasible=$official.ortoolsFeasible; pyvrpFeasible=$official.pyvrpFeasible; pyvrpEvidenceGap=$official.pyvrpEvidenceGap; irxVsOrtools=$official.irxVsOrtools}
  $summary.allowedClaims=if($summary.qualityPass){@("runtime readiness certified","external solver integration certified","IRX Hybrid no-loss vs BestExternal","IRX uses external dominance guard for safe final selection")}else{@("runtime readiness certified","external solver integration certified")}
  $summary.blockedClaims=if($summary.qualityPass){@("IRX dynamic win vs rerun baseline","IRX improves external seed on every dataset")}else{@("IRX no-loss vs external baseline","IRX improves external seed","IRX wins dynamic dispatch")}
  $summary.overallPass=($summary.runtimePass -and $summary.qualityPass -and $dynamic.overallPass -and $ml.overallPass -and $official.officialSmokePass)
} catch { $summary.overallPass=$false; $summary.error=$_.Exception.Message }
$summary.finishedAt=(Get-Date).ToString("o")
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 60 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }
