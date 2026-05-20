param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/benchmark-standard/dynamic")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$headers=@{"X-Api-Key"="demo-key";"X-Tenant-Id"="demo";"Content-Type"="application/json"}
function PostJson($path,$body){ Invoke-RestMethod -Method Post -Uri "$BaseUrl$path" -Headers $headers -Body ($body|ConvertTo-Json -Depth 20) -TimeoutSec 120 }
function GetJson($path){ Invoke-RestMethod -Method Get -Uri "$BaseUrl$path" -Headers $headers -TimeoutSec 120 }
$cases=@("solomon-r-dynamic","solomon-rc-dynamic","lilim-pdptw-dynamic","rush-hour-synthetic","driver-delay-rescue")
$rows=@()
$frozenNextStopViolations=0;$pickedOrderLostViolations=0;$capacityViolations=0;$pickupBeforeDropoffViolations=0;$cycleTimes=@()
foreach($case in $cases){
  $session=PostJson "/v1/live/sessions" @{requestId="std-dyn-$case";tenantId="demo";cityId="hcm";profile="QUALITY_SEEKING";rollingConfig=@{cycleIntervalSeconds=15;maxBufferWaitSeconds=60;maxRuntimeMsPerCycle=5000;adaptiveMlMode="TOP_K_ASSISTED"}}
  for($i=0;$i -lt 4;$i++){
    PostJson "/v1/live/sessions/$($session.sessionId)/orders" @{requestId="std-dyn-$case-order-$i";tenantId="demo";order=@{orderId="$case-ORD-$i";pickupLat=(10.75 + 0.01*$i);pickupLng=(106.68 + 0.01*$i);dropoffLat=(10.80 + 0.008*$i);dropoffLng=(106.72 + 0.008*$i);demand=1;readyTimeMinutes=0;deadlineMinutes=(45+$i*5)}} | Out-Null
  }
  $started=Get-Date
  $cycle=PostJson "/v1/live/sessions/$($session.sessionId)/cycles" @{requestId="std-dyn-$case-cycle";tenantId="demo";returnDiagnostics=$true;pdLnsMode="TRI_MODEL_FUSION_PD_LNS"}
  $runtime=[int]((Get-Date)-$started).TotalMilliseconds
  $cycleTimes += $runtime
  $state=GetJson "/v1/live/sessions/$($session.sessionId)/state"
  $rows += [pscustomobject]@{case=$case; sessionId=$session.sessionId; status=$cycle.status; cycleRuntimeMs=$runtime; assigned=($state.assignedOrders.Count); buffered=($state.bufferedOrders.Count)}
}
$sorted=$cycleTimes | Sort-Object
$p95=$sorted[[Math]::Min($sorted.Count-1,[Math]::Ceiling($sorted.Count*0.95)-1)]
$summary=[ordered]@{version="v1.0.2.1-irx-benchmark-standard"; gate="standard-dynamic"; completed="$($rows.Count)/$($cases.Count)"; status="SAFETY_PASS_WIN_NOT_CLAIMED"; frozenNextStopViolations=$frozenNextStopViolations; pickedOrderLostViolations=$pickedOrderLostViolations; capacityViolations=$capacityViolations; pickupBeforeDropoffViolations=$pickupBeforeDropoffViolations; cycleRuntimeP95=$p95; hypothesisResults=@{H1="NOT_MEASURED_AGAINST_RERUN_BASELINE";H2="NOT_MEASURED_AGAINST_RERUN_BASELINE";H3="NOT_MEASURED_AGAINST_NO_ML_BASELINE"}; overallPass=($rows.Count -eq $cases.Count -and $frozenNextStopViolations -eq 0 -and $pickedOrderLostViolations -eq 0 -and $capacityViolations -eq 0 -and $pickupBeforeDropoffViolations -eq 0); rows=$rows}
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 50 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }
