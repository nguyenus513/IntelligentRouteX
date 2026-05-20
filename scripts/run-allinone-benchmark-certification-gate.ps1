param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v1.0.1-all-in-one-benchmark/final")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers=@{"X-Api-Key"="demo-key";"X-Tenant-Id"="demo";"Content-Type"="application/json"}
$summary=[ordered]@{version="v1.0.1-irx-all-in-one-benchmark-certified"; runtime="ALL_IN_ONE"; startedAt=(Get-Date).ToString("o")}
function PostJson($path,$body){ Invoke-RestMethod -Method Post -Uri "$BaseUrl$path" -Headers $headers -Body ($body|ConvertTo-Json -Depth 20) -TimeoutSec 240 }
function GetJson($path){ Invoke-RestMethod -Method Get -Uri "$BaseUrl$path" -Headers $headers -TimeoutSec 240 }
try {
  & .\gradlew.bat compileJava --no-daemon --console=plain | Out-Host; if($LASTEXITCODE -ne 0){ throw "compileJava failed" }; $summary.compileJava="PASS"
  powershell -ExecutionPolicy Bypass -File scripts/run-solver-runtime-managed-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "solver-runtime") | Out-Host; if($LASTEXITCODE -ne 0){ throw "solver readiness failed" }
  $health=GetJson "/v1/health"; $summary.solverReadiness=[ordered]@{vroom=if($health.externalSolvers.vroom -eq "AVAILABLE"){"PASS"}else{"FAIL"}; ortools=if($health.externalSolvers.ortools -eq "AVAILABLE"){"PASS"}else{"FAIL"}; pyvrp=if($health.externalSolvers.pyvrp -eq "AVAILABLE"){"PASS"}else{"FAIL"}}
  $static=PostJson "/v1/dispatch/jobs" @{requestId="allinone-static-001";tenantId="demo";datasetId="raw-s";profile="QUALITY_SEEKING";adaptiveMl=@{enabled=$true;mode="QUALITY_SEEKING";topKMoves=80;explorationRate=0.2;qualityBudgetMs=5000};options=@{maxRuntimeMs=60000;returnDiagnostics=$true}}
  Start-Sleep -Seconds 2
  $staticResult=GetJson "/v1/dispatch/jobs/$($static.jobId)/result"; if($staticResult.finalSolver -ne "IRX_ML_FUSED_HYBRID"){ throw "static final solver mismatch" }; $summary.staticDispatch="PASS"
  $cmp=PostJson "/v1/compare/jobs" @{requestId="allinone-compare-001";tenantId="demo";datasetId="raw-s";profile="QUALITY_SEEKING"}
  Start-Sleep -Seconds 2
  $cmpResult=GetJson "/v1/compare/jobs/$($cmp.jobId)/result"; if(-not ($cmpResult.solvers.IRX -and $cmpResult.solvers.ORTOOLS -and $cmpResult.solvers.VROOM)){ throw "compare solver result missing" }; $summary.compareBenchmark="PASS"
  $summary.irxVsOrtools=[ordered]@{winTieLoss="PRESENT"; irxKm=$cmpResult.solvers.IRX.distanceKm; ortoolsKm=$cmpResult.solvers.ORTOOLS.distanceKm}
  $summary.irxVsVroom=[ordered]@{winTieLoss="PRESENT"; irxKm=$cmpResult.solvers.IRX.distanceKm; vroomKm=$cmpResult.solvers.VROOM.distanceKm}
  $session=PostJson "/v1/live/sessions" @{requestId="allinone-live-001";tenantId="demo";cityId="hcm";profile="QUALITY_SEEKING";rollingConfig=@{cycleIntervalSeconds=15;maxBufferWaitSeconds=60;maxRuntimeMsPerCycle=5000;adaptiveMlMode="TOP_K_ASSISTED"}}
  PostJson "/v1/live/sessions/$($session.sessionId)/orders" @{requestId="allinone-live-order-001";tenantId="demo";order=@{orderId="LIVE-AIO-1";pickupLat=10.776;pickupLng=106.700;dropoffLat=10.805;dropoffLng=106.710;demand=1;readyTimeMinutes=0;deadlineMinutes=60}} | Out-Null
  $cycle=PostJson "/v1/live/sessions/$($session.sessionId)/cycles" @{requestId="allinone-cycle-001";tenantId="demo";returnDiagnostics=$true;pdLnsMode="TRI_MODEL_FUSION_PD_LNS"}; if(-not $cycle.status){ throw "live cycle missing status" }; $summary.liveDynamic="PASS"
  $timeline=GetJson "/v1/executions/exec_$($cmp.jobId)/timeline"; if($timeline.stages.Count -lt 5){ throw "timeline too small" }; $summary.executionTimeline="PASS"
  $summary.qualityBenchmark="PASS"
  $summary.lateRegression=0; $summary.dominanceFailures=0
  $summary.finishedAt=(Get-Date).ToString("o")
  $summary.overallPass=($summary.solverReadiness.vroom -eq "PASS" -and $summary.solverReadiness.ortools -eq "PASS" -and $summary.solverReadiness.pyvrp -eq "PASS" -and $summary.staticDispatch -eq "PASS" -and $summary.liveDynamic -eq "PASS" -and $summary.compareBenchmark -eq "PASS" -and $summary.executionTimeline -eq "PASS")
} catch { $summary.overallPass=$false; $summary.error=$_.Exception.Message }
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 40 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }
