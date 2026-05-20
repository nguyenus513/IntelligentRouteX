param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v1.0.0-production-api-core/contract")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$checks=[ordered]@{}
& .\gradlew.bat compileJava --no-daemon --console=plain | Out-Host
$checks.compileJava = if($LASTEXITCODE -eq 0){"PASS"}else{"FAIL"}
$checks.openapiExists = Test-Path "docs/openapi/irx-api-v1.yaml"
$checks.asyncapiExists = Test-Path "docs/asyncapi/irx-events-v1.yaml"
$openapi = Get-Content "docs/openapi/irx-api-v1.yaml" -Raw
$checks.dispatchPath = $openapi.Contains("/v1/dispatch/jobs")
$checks.livePath = $openapi.Contains("/v1/live/sessions")
$checks.comparePath = $openapi.Contains("/v1/compare/jobs")
$checks.executionPath = $openapi.Contains("/v1/executions/{executionId}/timeline")
$checks.securityScheme = $openapi.Contains("ApiKeyAuth")
$pass = $true
foreach($value in $checks.Values){ if(($value -is [bool] -and -not $value) -or ($value -is [string] -and $value -eq "FAIL")){ $pass = $false } }
$summary=[ordered]@{ gate="api-contract"; overallPass=$pass; checks=$checks }
$path=Join-Path $OutputDir "api-contract-summary.json"
$summary | ConvertTo-Json -Depth 20 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $pass){ exit 1 }


