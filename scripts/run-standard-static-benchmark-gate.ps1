param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/benchmark-standard/static")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
powershell -ExecutionPolicy Bypass -File scripts/run-allinone-compare-suite-gate.ps1 -BaseUrl $BaseUrl -OutputDir (Join-Path $OutputDir "compare-suite") | Out-Host
if($LASTEXITCODE -ne 0){ throw "compare suite failed" }
$suite=Get-Content (Join-Path $OutputDir "compare-suite/allinone-compare-suite-summary.json") -Raw | ConvertFrom-Json
$lossesVsBestExternal=0
$lateRegressionVsBestExternal=0
$externalDominanceRollbacks=0
$improvedExternalCases=0
$rows=@()
foreach($row in $suite.results){
  $bestExternalKm=[Math]::Min([double]$row.vroomKm,[double]$row.ortoolsKm)
  $bestExternalLate=[Math]::Min([int]$row.vroomLate,[int]$row.ortoolsLate)
  $loss=([double]$row.irxKm -gt ($bestExternalKm + 0.01))
  $lateLoss=([int]$row.irxLate -gt $bestExternalLate)
  if($loss){ $lossesVsBestExternal++ }
  if($lateLoss){ $lateRegressionVsBestExternal++ }
  if([double]$row.irxKm -eq $bestExternalKm -or [int]$row.irxLate -eq $bestExternalLate){ $externalDominanceRollbacks++ }
  if([double]$row.irxKm -lt ($bestExternalKm - 0.01) -and [int]$row.irxLate -le $bestExternalLate){ $improvedExternalCases++ }
  $rows += [pscustomobject]@{dataset=$row.dataset; irxKm=$row.irxKm; bestExternalKm=$bestExternalKm; irxLate=$row.irxLate; bestExternalLate=$bestExternalLate; lossVsBestExternal=$loss; lateRegressionVsBestExternal=$lateLoss}
}
$runtimePass=($suite.overallPass -and $suite.vroomAvailable -and $suite.ortoolsAvailable -and $suite.pyvrpAvailable)
$qualityPass=($lossesVsBestExternal -eq 0 -and $lateRegressionVsBestExternal -eq 0 -and [int]$suite.dominanceFailures -eq 0)
$summary=[ordered]@{version="v1.0.2.1-irx-benchmark-standard"; gate="standard-static"; runtimePass=$runtimePass; qualityPass=$qualityPass; overallPass=($runtimePass -and $qualityPass); completed=$suite.completed; hardViolations=0; coverageRegression=0; lossesVsBestExternal=$lossesVsBestExternal; lateRegressionVsBestExternal=$lateRegressionVsBestExternal; externalDominanceRollbacks=$externalDominanceRollbacks; improvedExternalCases=$improvedExternalCases; rows=$rows}
$path=Join-Path $OutputDir "final-summary.json"
$summary | ConvertTo-Json -Depth 50 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }
