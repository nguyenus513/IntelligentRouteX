param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/benchmark-standard/ml")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers=@{"X-Api-Key"="demo-key";"X-Tenant-Id"="demo";"Content-Type"="application/json"}
function PostJson($path,$body){ Invoke-RestMethod -Method Post -Uri "$BaseUrl$path" -Headers $headers -Body ($body|ConvertTo-Json -Depth 20) -TimeoutSec 180 }
function GetJson($path){ Invoke-RestMethod -Method Get -Uri "$BaseUrl$path" -Headers $headers -TimeoutSec 180 }
$modes=@("NO_ML_HEURISTIC","TOP_K_ASSISTED","QUALITY_SEEKING","QUALITY_SEEKING_EXTERNAL_DOMINANCE")
$rows=@()
foreach($mode in $modes){
  $mlMode=if($mode -eq "NO_ML_HEURISTIC"){"OFF"}elseif($mode -eq "TOP_K_ASSISTED"){"TOP_K_ASSISTED"}else{"QUALITY_SEEKING"}
  $job=PostJson "/v1/dispatch/jobs" @{requestId="std-ml-$mode";tenantId="demo";datasetId="raw-s";profile="QUALITY_SEEKING";adaptiveMl=@{enabled=($mode -ne "NO_ML_HEURISTIC");mode=$mlMode;topKMoves=80;explorationRate=0.2;qualityBudgetMs=3000};options=@{maxRuntimeMs=60000;returnDiagnostics=$true}}
  Start-Sleep -Seconds 2
  $result=GetJson "/v1/dispatch/jobs/$($job.jobId)/result"
  $rows += [pscustomobject]@{mode=$mode; jobId=$job.jobId; distanceKm=$result.metrics.distanceKm; lateCount=$result.metrics.lateCount; coverageRate=$result.metrics.coverageRate; runtimeMs=$result.metrics.runtimeMs}
}
$baseline=$rows | Where-Object mode -eq "NO_ML_HEURISTIC" | Select-Object -First 1
$quality=$rows | Where-Object mode -eq "QUALITY_SEEKING" | Select-Object -First 1
$lossesVsNoMl=if($quality.lateCount -gt $baseline.lateCount -or $quality.distanceKm -gt ($baseline.distanceKm+0.01)){1}else{0}
$qualityGainCases=if($quality.distanceKm -lt ($baseline.distanceKm-0.01) -and $quality.lateCount -le $baseline.lateCount){1}else{0}
$summary=[ordered]@{version="v1.0.2.1-irx-benchmark-standard"; gate="ml-contribution"; rows=$rows; lossesVsNoMl=$lossesVsNoMl; qualityGainCases=$qualityGainCases; runtimeSearchGainCases=0; status=if($qualityGainCases -gt 0){"ML_GAIN_MEASURED"}else{"NO_REGRESS_ONLY"}; overallPass=($lossesVsNoMl -eq 0)}
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 50 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }
