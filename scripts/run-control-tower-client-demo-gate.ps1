param(
  [string]$PlaygroundDir = "playground",
  [string]$BaseUrl = "http://localhost:18116",
  [string]$OutputDir = "artifacts/test-reports/v1.1.0-irx-control-tower-client"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$summary = [ordered]@{
  version = "v1.1.0-irx-control-tower-client"
  startedAt = (Get-Date).ToString("o")
}

function Invoke-Irx($Path, $Method = "GET", $Body = $null) {
  $headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo"; "Content-Type" = "application/json"; "Idempotency-Key" = "gate-$([Guid]::NewGuid())" }
  $uri = "$BaseUrl$Path"
  if ($Body -ne $null) {
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body ($Body | ConvertTo-Json -Depth 30)
  }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
}

function Get-FirstId($Object, [string[]]$Keys) {
  foreach ($key in $Keys) {
    if ($Object.PSObject.Properties.Name -contains $key -and $Object.$key) { return [string]$Object.$key }
  }
  return $null
}

try {
  Push-Location $PlaygroundDir
  npm install | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
  npm run build | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "playground build failed" }
  Pop-Location
  $summary.frontendBuild = "PASS"

  $health = Invoke-Irx "/v1/health"
  $version = Invoke-Irx "/v1/version"
  $summary.health = "PASS"
  $summary.version = "PASS"
  $summary.healthResponse = $health
  $summary.versionResponse = $version

  $staticBody = @{ requestId="ct-static-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId="demo"; datasetId="raw-s"; profile="QUALITY_SEEKING"; adaptiveMl=@{ enabled=$true; mode="QUALITY_SEEKING" }; options=@{ maxRuntimeMs=60000; returnDiagnostics=$true } }
  $static = Invoke-Irx "/v1/dispatch/jobs" "POST" $staticBody
  $staticJobId = Get-FirstId $static @("jobId", "id")
  $staticExecutionId = Get-FirstId $static @("executionId")
  if (-not $staticJobId) { throw "static dispatch did not return jobId/id" }
  $summary.staticDispatch = "PASS"
  $summary.staticStatus = Invoke-Irx "/v1/dispatch/jobs/$staticJobId"
  $summary.staticResult = Invoke-Irx "/v1/dispatch/jobs/$staticJobId/result"
  if ($staticExecutionId) {
    $summary.staticTimeline = Invoke-Irx "/v1/executions/$staticExecutionId/timeline"
    $summary.staticEvents = Invoke-Irx "/v1/executions/$staticExecutionId/events"
  } else {
    $summary.staticTimeline = "SKIP_NO_EXECUTION_ID"
    $summary.staticEvents = "SKIP_NO_EXECUTION_ID"
  }

  $compareBody = @{ requestId="ct-compare-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId="demo"; datasetId="raw-s"; profile="QUALITY_SEEKING"; solvers=@("IRX","VROOM","ORTOOLS","PYVRP"); options=@{ maxRuntimeMs=60000; returnDiagnostics=$true } }
  $compare = Invoke-Irx "/v1/compare/jobs" "POST" $compareBody
  $compareJobId = Get-FirstId $compare @("jobId", "id")
  if (-not $compareJobId) { throw "compare did not return jobId/id" }
  $summary.compareApi = "PASS"
  $summary.compareResult = Invoke-Irx "/v1/compare/jobs/$compareJobId/result"

  $live = Invoke-Irx "/v1/live/sessions" "POST" @{ requestId="ct-live-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; tenantId="demo"; cityId="hcm"; profile="LIVE_ROLLING" }
  $liveSessionId = Get-FirstId $live @("sessionId", "id")
  if (-not $liveSessionId) { throw "live session did not return sessionId/id" }
  $summary.liveSession = "PASS"
  $order = @{ orderId="gate-order-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; load=4; pickup=@{ lat=10.7626; lng=106.6601 }; dropoff=@{ lat=10.7812; lng=106.6923 }; deadline=(Get-Date).AddMinutes(45).ToString("o") }
  $summary.liveOrder = Invoke-Irx "/v1/live/sessions/$liveSessionId/orders" "POST" @{ requestId="ct-order-$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())"; order=$order }
  $summary.liveCycle = Invoke-Irx "/v1/live/sessions/$liveSessionId/cycles" "POST" @{ trigger="MANUAL"; reason="demo-gate"; options=@{ maxRuntimeMs=5000; returnDiagnostics=$true } }
  $summary.liveState = Invoke-Irx "/v1/live/sessions/$liveSessionId/state"

  $summary.overallPass = $true
} catch {
  try { Pop-Location } catch {}
  $summary.overallPass = $false
  $summary.error = $_.Exception.Message
}

$summary.finishedAt = (Get-Date).ToString("o")
$path = Join-Path $OutputDir "control-tower-client-summary.json"
$summary | ConvertTo-Json -Depth 60 | Set-Content $path
Write-Output "SUMMARY=$path"
if (-not $summary.overallPass) { exit 1 }
