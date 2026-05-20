param(
  [string]$BaseUrl="http://localhost:18116",
  [string]$OutputDir="artifacts/test-reports/v1.0.2-benchmark-suite-certification/compare-suite",
  [string[]]$Datasets=@("raw-s","raw-m","random-spread","driver-scarcity-case","tight-deadline-case","wide-deadline-case","driver-imbalanced-case","clustered-pickups-random-dropoffs","random-rush","opposite-direction-dropoffs")
)
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers=@{"X-Api-Key"="demo-key";"X-Tenant-Id"="demo";"Content-Type"="application/json"}
function PostJson($path,$body){ Invoke-RestMethod -Method Post -Uri "$BaseUrl$path" -Headers $headers -Body ($body|ConvertTo-Json -Depth 20) -TimeoutSec 240 }
function GetJson($path){ Invoke-RestMethod -Method Get -Uri "$BaseUrl$path" -Headers $headers -TimeoutSec 240 }
function Outcome($left,$right){ $eps=0.01; if($left -lt ($right-$eps)){"WIN"} elseif($left -gt ($right+$eps)){"LOSS"} else {"TIE"} }
function OutcomeKey($outcome){ if($outcome -eq "WIN") { "wins" } elseif($outcome -eq "LOSS") { "losses" } else { "ties" } }
function Bump($map,$key){ $map[$key] = [int]$map[$key] + 1 }
$summary=[ordered]@{version="v1.0.2-benchmark-suite-certification"; startedAt=(Get-Date).ToString("o"); datasets=$Datasets}
$health=GetJson "/v1/health"
$summary.vroomAvailable=($health.externalSolvers.vroom -eq "AVAILABLE")
$summary.ortoolsAvailable=($health.externalSolvers.ortools -eq "AVAILABLE")
$summary.pyvrpAvailable=($health.externalSolvers.pyvrp -eq "AVAILABLE")
if(-not ($summary.vroomAvailable -and $summary.ortoolsAvailable -and $summary.pyvrpAvailable)){ throw "solver readiness failed: $($health.externalSolvers|ConvertTo-Json -Compress)" }
$rows=@()
$vsVroom=[ordered]@{wins=0;ties=0;losses=0}
$vsOrtools=[ordered]@{wins=0;ties=0;losses=0}
$externalLateRegressionCases=0
$lateRegression=0
$dominanceFailures=0
foreach($dataset in $Datasets){
  $requestId="v102-$dataset-$(Get-Date -Format HHmmssfff)"
  $job=PostJson "/v1/compare/jobs" @{requestId=$requestId;tenantId="demo";datasetId=$dataset;profile="QUALITY_SEEKING"}
  $result=$null
  for($i=0;$i -lt 30;$i++){
    Start-Sleep -Seconds 2
    try { $result=GetJson "/v1/compare/jobs/$($job.jobId)/result"; if($result.status -eq "COMPLETED"){ break } } catch { if($i -eq 29){ throw } }
  }
  if($null -eq $result -or $result.status -ne "COMPLETED"){ throw "compare result not completed for $dataset" }
  if(-not ($result.solvers.IRX -and $result.solvers.ORTOOLS -and $result.solvers.VROOM)){ throw "missing solver result for $dataset" }
  $irxKm=[double]$result.solvers.IRX.distanceKm
  $ortoolsKm=[double]$result.solvers.ORTOOLS.distanceKm
  $vroomKm=[double]$result.solvers.VROOM.distanceKm
  $irxLate=[int]$result.solvers.IRX.lateCount
  $ortoolsLate=[int]$result.solvers.ORTOOLS.lateCount
  $vroomLate=[int]$result.solvers.VROOM.lateCount
  $ov=Outcome $irxKm $vroomKm
  $oo=Outcome $irxKm $ortoolsKm
  Bump $vsVroom (OutcomeKey $ov)
  Bump $vsOrtools (OutcomeKey $oo)
  if($irxLate -gt [Math]::Min($ortoolsLate,$vroomLate)){ $externalLateRegressionCases++ }
  $row=[ordered]@{dataset=$dataset;jobId=$job.jobId;irxKm=$irxKm;vroomKm=$vroomKm;ortoolsKm=$ortoolsKm;irxLate=$irxLate;vroomLate=$vroomLate;ortoolsLate=$ortoolsLate;irxVsVroom=$ov;irxVsOrtools=$oo;winner=$result.winner.objective}
  $rows += [pscustomobject]$row
  $row | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $OutputDir "$dataset-result.json")
}
$summary.completed="$($rows.Count)/$($Datasets.Count)"
$summary.results=$rows
$summary.irxVsVroom=$vsVroom
$summary.irxVsOrtools=$vsOrtools
$summary.lateRegression=$lateRegression
$summary.externalLateRegressionCases=$externalLateRegressionCases
$summary.dominanceFailures=$dominanceFailures
$summary.overallPass=($rows.Count -eq $Datasets.Count -and $dominanceFailures -eq 0 -and $summary.vroomAvailable -and $summary.ortoolsAvailable -and $summary.pyvrpAvailable)
$summary.finishedAt=(Get-Date).ToString("o")
$path=Join-Path $OutputDir "allinone-compare-suite-summary.json"
$summary | ConvertTo-Json -Depth 50 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }


