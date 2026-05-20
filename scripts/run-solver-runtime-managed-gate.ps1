param([string]$BaseUrl="http://localhost:18116", [string]$OutputDir="artifacts/test-reports/v1.0.1-all-in-one-benchmark/solver-runtime")
$ErrorActionPreference="Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$summary=[ordered]@{version="v1.0.1-irx-all-in-one-benchmark-certified"; gate="solver-runtime-managed"}
try { & tools/vroom/vroom-wsl.cmd --version | Out-String | % { $summary.vroomVersion=$_; $summary.vroom="PASS" } } catch { $summary.vroom="FAIL"; $summary.vroomError=$_.Exception.Message }
try { py -3 -c "import pyvrp; print(getattr(pyvrp,'__version__','unknown'))" | Out-String | % { $summary.pyvrpVersion=$_; $summary.pyvrp="PASS" } } catch { $summary.pyvrp="FAIL"; $summary.pyvrpError=$_.Exception.Message }
try { & .\gradlew.bat compileJava --no-daemon --console=plain | Out-Host; if($LASTEXITCODE -ne 0){ throw "compileJava failed" }; $summary.ortools="PASS" } catch { $summary.ortools="FAIL"; $summary.ortoolsError=$_.Exception.Message }
try { $h=Invoke-RestMethod -Uri "$BaseUrl/v1/health" -Headers @{"X-Api-Key"="demo-key";"X-Tenant-Id"="demo"} -TimeoutSec 30; $summary.health=$h; $summary.healthReady=($h.externalSolvers.vroom -eq "AVAILABLE" -and $h.externalSolvers.ortools -eq "AVAILABLE" -and $h.externalSolvers.pyvrp -eq "AVAILABLE") } catch { $summary.healthReady=$false; $summary.healthError=$_.Exception.Message }
$summary.overallPass=($summary.vroom -eq "PASS" -and $summary.ortools -eq "PASS" -and $summary.pyvrp -eq "PASS" -and $summary.healthReady)
$path=Join-Path $OutputDir "solver-runtime-managed-summary.json"
$summary | ConvertTo-Json -Depth 30 | Set-Content $path
Write-Output "SUMMARY=$path"
if(-not $summary.overallPass){ exit 1 }
