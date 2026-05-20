param([string]$SummaryPath="artifacts/test-reports/v1.0.0-production-api-core/final/final-summary.json", [string]$Output="artifacts/test-reports/v1.0.0-production-api-core/final/failure-analysis.json")
$ErrorActionPreference="Stop"
$summary = if(Test-Path $SummaryPath){ Get-Content $SummaryPath -Raw | ConvertFrom-Json } else { $null }
$classes=@()
if($null -eq $summary){ $classes += "API_CONTRACT_FAILURE" }
elseif(-not $summary.overallPass){
  foreach($p in $summary.results.PSObject.Properties){
    if($p.Value -ne "PASS"){
      $classes += switch($p.Name){
        "apiContract" { "API_CONTRACT_FAILURE"; break }
        "runtimeStore" { "JOB_RUNTIME_FAILURE"; break }
        "executionTimeline" { "TIMELINE_FAILURE"; break }
        "staticDispatchApi" { "STATIC_DISPATCH_FAILURE"; break }
        "liveDynamicApi" { "LIVE_DYNAMIC_FAILURE"; break }
        "freezePolicy" { "FREEZE_POLICY_FAILURE"; break }
        "compareApi" { "COMPARE_FAILURE"; break }
        "security" { "AUTH_FAILURE"; break }
        "idempotency" { "IDEMPOTENCY_FAILURE"; break }
        "rateLimit" { "RATE_LIMIT_FAILURE"; break }
        "artifactStore" { "ARTIFACT_ACCESS_FAILURE"; break }
        "eventStream" { "EVENT_STREAM_FAILURE"; break }
        "observability" { "OBSERVABILITY_FAILURE"; break }
        "dockerComposeSmoke" { "DOCKER_RUNTIME_FAILURE"; break }
        default { "JOB_RUNTIME_FAILURE" }
      }
    }
  }
}
$result=[ordered]@{ overallPass=($classes.Count -eq 0); classes=$classes; source=$SummaryPath }
New-Item -ItemType Directory -Force -Path (Split-Path $Output) | Out-Null
$result | ConvertTo-Json -Depth 20 | Set-Content $Output
Write-Output "SUMMARY=$Output"
if($classes.Count -gt 0){ exit 1 }
