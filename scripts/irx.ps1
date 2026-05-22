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
function Start-Local {
  Ensure-Runtime
  Write-Step "Checking Java"
  Get-Command java | Out-Null
  if(Test-Path $Vroom){ $env:VROOM_BIN = (Resolve-Path $Vroom).Path }
  if(-not $env:IRX_ROUTING_PROVIDER){ $env:IRX_ROUTING_PROVIDER = "osrm" }
  if(-not $env:IRX_ROUTING_BASE_URL){ $env:IRX_ROUTING_BASE_URL = "http://127.0.0.1:5001" }
  $env:GRADLE_USER_HOME = Join-Path $Root ".gradle-tmp"
  New-Item -ItemType Directory -Force -Path $env:GRADLE_USER_HOME | Out-Null
  Stop-Port $BackendPort "backend"
  Write-Step "Starting backend on $BackendPort"
  $backendCmd = "cd '$Root'; `$env:GRADLE_USER_HOME='$env:GRADLE_USER_HOME'; `$env:VROOM_BIN='$env:VROOM_BIN'; `$env:ROUTECHAIN_DISPATCH_V2_ROUTING_PROVIDER='$env:IRX_ROUTING_PROVIDER'; `$env:ROUTECHAIN_DISPATCH_V2_ROUTING_BASE_URL='$env:IRX_ROUTING_BASE_URL'; .\gradlew.bat bootRun --args='--server.port=$BackendPort --routechain.dispatch-v2.sidecar-required=false --routechain.dispatch-v2.routing.provider=$env:IRX_ROUTING_PROVIDER --routechain.dispatch-v2.routing.base-url=$env:IRX_ROUTING_BASE_URL' *> '$BackendLog'"
  $bp = Start-Process powershell.exe -ArgumentList @('-NoExit','-Command',$backendCmd) -WindowStyle Minimized -PassThru
  Set-Content $BackendPid $bp.Id
  Wait-Http "$BackendUrl/v1/health" 180 "API Health" | Out-Null
  Write-Host "IRX backend started: $BackendUrl"
}
function Stop-System {
  if($Profile -eq "docker"){ docker compose down; return }
  Ensure-Runtime
  Stop-PidFile $BackendPid "backend"
  Stop-Port $BackendPort "backend"
  Write-Host "IRX backend stopped."
}
function Show-Status {
  Ensure-Runtime
  $bpid = if(Test-Path $BackendPid){ (Get-Content $BackendPid -Raw).Trim() } else { "" }
  $bh = Test-Http "$BackendUrl/v1/health"
  Write-Host "Backend:"
  Write-Host "  URL: $BackendUrl"
  Write-Host "  Health: $(if($bh){'PASS'}else{'FAIL'})"
  Write-Host "  PID: $(if($bpid){$bpid}else{'none'})"
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
  "up" { if($Profile -eq "docker"){ docker compose up -d --build; Wait-Http "$BackendUrl/v1/health" 180 "API Health" | Out-Null } else { Start-Local } }
  "down" { Stop-System }
  "status" { Show-Status }
  "test" { Run-Test }
  "package" { Package-Release }
  "clean" { Stop-System; Remove-Item $RuntimeDir -Recurse -Force -ErrorAction SilentlyContinue }
}
