param(
  [Parameter(Position=0)]
  [ValidateSet("up", "down", "test", "status", "package", "clean")]
  [string]$Command = "status",
  [ValidateSet("local", "docker")]
  [string]$Profile = "local",
  [switch]$Quick,
  [int]$BackendPort = 18116
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $Root ".runtime"
$BackendPid = Join-Path $RuntimeDir "backend.pid"
$BackendLog = Join-Path $RuntimeDir "backend.log"
$BackendUrl = "http://localhost:$BackendPort"
$Vroom = Join-Path $Root "tools\vroom\vroom-wsl.cmd"
$OsrmDataDir = Join-Path $Root "artifacts\osrm"
$OsrmContainer = "intelligentroutex-osrm"
$OsrmUrl = "http://127.0.0.1:5001"
$OsrmTableProbe = "$OsrmUrl/table/v1/driving/106.7009,10.7769;106.6983,10.7721?annotations=duration,distance"

function Ensure-Runtime { New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null }
function Write-Step($m){ Write-Host "[IRX] $m" }
function Test-Http($url){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3; return $r.StatusCode -ge 200 -and $r.StatusCode -lt 500 } catch { return $false } }
function Wait-Http($url, [int]$seconds, [string]$name){
  $deadline = (Get-Date).AddSeconds($seconds)
  while((Get-Date) -lt $deadline){ if(Test-Http $url){ Write-Step "$name PASS $url"; return $true }; Start-Sleep -Seconds 2 }
  throw "$name timeout: $url"
}
function Port-Pid([int]$port){ (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess) }
function Stop-PidFile($path, $name){
  if(Test-Path $path){
    $pidText = (Get-Content $path -Raw).Trim()
    if($pidText){ $p = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue; if($p){ Write-Step "Stopping $name pid=$pidText"; Stop-Process -Id ([int]$pidText) -Force } }
    Remove-Item $path -Force -ErrorAction SilentlyContinue
  }
}
function Stop-Port([int]$port, [string]$name){ $portProcessId = Port-Pid $port; if($portProcessId){ Write-Step "Stopping $name port $port pid=$portProcessId"; Stop-Process -Id $portProcessId -Force -ErrorAction SilentlyContinue } }
function Start-Osrm {
  if(Test-Http $OsrmTableProbe){ Write-Step "OSRM PASS $OsrmUrl"; return }
  if(-not (Get-Command docker -ErrorAction SilentlyContinue)){ throw "OSRM required but Docker is not available" }
  if(-not (Test-Path (Join-Path $OsrmDataDir "hcmc-demo.osrm"))){ throw "Missing OSRM data: $OsrmDataDir\hcmc-demo.osrm" }
  Write-Step "Starting OSRM on 127.0.0.1:5001"
  if((docker ps -a --format "{{.Names}}") -contains $OsrmContainer){ docker rm -f $OsrmContainer | Out-Null }
  $mount = ($OsrmDataDir -replace "\\", "/")
  docker run -d --name $OsrmContainer -p 127.0.0.1:5001:5000 -v "${mount}:/data" osrm/osrm-backend:latest osrm-routed --algorithm ch /data/hcmc-demo.osrm | Out-Null
  Wait-Http $OsrmTableProbe 60 "OSRM Table" | Out-Null
}
function Stop-Osrm {
  if(Get-Command docker -ErrorAction SilentlyContinue){ if((docker ps -a --format "{{.Names}}") -contains $OsrmContainer){ docker rm -f $OsrmContainer | Out-Null } }
}
function Start-Local {
  Ensure-Runtime
  Write-Step "Checking Java"
  Get-Command java | Out-Null
  if(Test-Path $Vroom){ $env:VROOM_BIN = (Resolve-Path $Vroom).Path }
  if(-not $env:IRX_ROUTING_PROVIDER){ $env:IRX_ROUTING_PROVIDER = "osrm" }
  if(-not $env:IRX_ROUTING_BASE_URL){ $env:IRX_ROUTING_BASE_URL = $OsrmUrl }
  Start-Osrm
  $env:GRADLE_USER_HOME = Join-Path $Root ".gradle-tmp"
  New-Item -ItemType Directory -Force -Path $env:GRADLE_USER_HOME | Out-Null
  Stop-Port $BackendPort "backend"
  Write-Step "Starting backend on $BackendPort"
  try { Set-Content -Encoding UTF8 $BackendLog "" -ErrorAction Stop } catch { Write-Step "Backend log is locked; appending to existing log" }
  $backendCmd = "cd '$Root'; `$env:GRADLE_USER_HOME='$env:GRADLE_USER_HOME'; `$env:VROOM_BIN='$env:VROOM_BIN'; `$env:ROUTECHAIN_DISPATCH_V2_ROUTING_PROVIDER='$env:IRX_ROUTING_PROVIDER'; `$env:ROUTECHAIN_DISPATCH_V2_ROUTING_BASE_URL='$env:IRX_ROUTING_BASE_URL'; .\gradlew.bat bootRun --no-daemon --console=plain --args='--server.port=$BackendPort --routechain.dispatch-v2.sidecar-required=false --routechain.dispatch-v2.routing.provider=$env:IRX_ROUTING_PROVIDER --routechain.dispatch-v2.routing.base-url=$env:IRX_ROUTING_BASE_URL' *> '$BackendLog'"
  $bp = Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$backendCmd) -WindowStyle Minimized -PassThru
  Set-Content $BackendPid $bp.Id
  Wait-Http "$BackendUrl/v1/health" 240 "API Health" | Out-Null
  Write-Host "IRX backend started: $BackendUrl"
}
function Stop-System {
  if($Profile -eq "docker"){ docker compose down; return }
  Ensure-Runtime
  Stop-PidFile $BackendPid "backend"
  Stop-Port $BackendPort "backend"
  Stop-Osrm
  Write-Host "IRX backend and OSRM stopped."
}
function Show-Status {
  Ensure-Runtime
  $bpid = if(Test-Path $BackendPid){ (Get-Content $BackendPid -Raw).Trim() } else { "" }
  if(-not $bpid -or -not (Get-Process -Id ([int]$bpid) -ErrorAction SilentlyContinue)){ $portPid = Port-Pid $BackendPort; $bpid = if($portPid){ [string]$portPid } else { "" } }
  $bh = Test-Http "$BackendUrl/v1/health"
  $oh = Test-Http $OsrmTableProbe
  Write-Host "Backend:"
  Write-Host "  URL: $BackendUrl"
  Write-Host "  Health: $(if($bh){'PASS'}else{'FAIL'})"
  Write-Host "  PID: $(if($bpid){$bpid}else{'none'})"
  Write-Host "OSRM:"
  Write-Host "  URL: $OsrmUrl"
  Write-Host "  Table: $(if($oh){'PASS'}else{'FAIL'})"
  Write-Host "  Container: $OsrmContainer"
}
function Run-Test {
  $env:GRADLE_USER_HOME = Join-Path $Root ".gradle-tmp"
  & "$Root\gradlew.bat" compileJava --no-daemon --console=plain | Out-Host
}
function Package-Release {
  $env:GRADLE_USER_HOME = Join-Path $Root ".gradle-tmp"
  & "$Root\gradlew.bat" bootJar --no-daemon --console=plain | Out-Host
  Write-Host "Backend jar: build/libs"
}

switch($Command){
  "up" { if($Profile -eq "docker"){ docker compose up -d --build; Wait-Http "$BackendUrl/v1/health" 240 "API Health" | Out-Null } else { Start-Local } }
  "down" { Stop-System }
  "status" { Show-Status }
  "test" { Run-Test }
  "package" { Package-Release }
  "clean" { Stop-System; Remove-Item $RuntimeDir -Recurse -Force -ErrorAction SilentlyContinue }
}
