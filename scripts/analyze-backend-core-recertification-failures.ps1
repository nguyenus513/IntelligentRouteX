param(
  [string]$InputDir="artifacts/test-reports/v1.0.1-backend-core-recertified",
  [string]$Output="artifacts/test-reports/v1.0.1-backend-core-recertified/failure-analysis.json"
)
$ErrorActionPreference="Stop"
$summaryPath=Join-Path $InputDir "final-summary.json"
$summary=if(Test-Path $summaryPath){ Get-Content $summaryPath -Raw | ConvertFrom-Json } else { $null }
$classes=@()
if($null -eq $summary){ $classes += "COMPILE_FAILURE" }
else {
  $map=@{
    compileJava="COMPILE_FAILURE"; health="HEALTH_FAILURE"; staticDispatchApi="STATIC_DISPATCH_FAILURE"; executionTimeline="TIMELINE_FAILURE"; compareApi="COMPARE_FAILURE"; liveDynamicApi="LIVE_DYNAMIC_FAILURE"; security="SECURITY_FAILURE"; idempotency="IDEMPOTENCY_FAILURE"; rateLimit="RATE_LIMIT_FAILURE"; eventStream="EVENT_STREAM_FAILURE"; observability="OBSERVABILITY_FAILURE"; backendOnly="LEGACY_DASHBOARD_DEPENDENCY"
  }
  foreach($key in $map.Keys){ if($summary.PSObject.Properties.Name -contains $key){ $value=$summary.$key; if($value -ne "PASS" -and $value -ne $true){ $classes += $map[$key] } } }
}
$result=[ordered]@{ overallPass=($classes.Count -eq 0); classes=$classes; source=$summaryPath }
New-Item -ItemType Directory -Force -Path (Split-Path $Output) | Out-Null
$result | ConvertTo-Json -Depth 20 | Set-Content $Output
Write-Output "SUMMARY=$Output"
if($classes.Count -gt 0){ exit 1 }
