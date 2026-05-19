param(
  [string]$Version = "v0.9.13",
  [string]$PackageName = "IRX-Docker-Demo-v0.9.13",
  [string]$OutputRoot = "dist",
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packageDir = Join-Path (Join-Path $root $OutputRoot) $PackageName
$imagesDir = Join-Path $packageDir "images"
$docsDir = Join-Path $packageDir "docs"
$evidenceDir = Join-Path $packageDir "artifacts\demo-evidence"
$buildDir = Join-Path $packageDir ".build"
$backendCtx = Join-Path $buildDir "backend"
$dashboardCtx = Join-Path $buildDir "dashboard"

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

if(Test-Path $packageDir) { Remove-Item -Recurse -Force $packageDir }
New-Item -ItemType Directory -Force -Path $imagesDir, $docsDir, $evidenceDir, $backendCtx, $dashboardCtx | Out-Null

if(-not $SkipBuild) {
  Push-Location $root
  try { .\gradlew.bat bootJar --no-daemon --console=plain }
  finally { Pop-Location }
  Push-Location (Join-Path $root "dashboard")
  try { npm run build }
  finally { Pop-Location }
}

$jar = Get-ChildItem (Join-Path $root "build\libs") -Filter "*.jar" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if($null -eq $jar) { throw "backend jar not found under build/libs" }
Copy-Item $jar.FullName (Join-Path $backendCtx "irx-backend.jar")
Copy-Item -Recurse (Join-Path $root "dashboard\dist") (Join-Path $dashboardCtx "dashboard-dist")

Write-Utf8NoBom (Join-Path $backendCtx "Dockerfile") @'
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY irx-backend.jar /app/irx-backend.jar
EXPOSE 18116
ENTRYPOINT ["java", "-jar", "/app/irx-backend.jar", "--server.port=18116", "--spring.profiles.active=demo"]
'@

Write-Utf8NoBom (Join-Path $dashboardCtx "Dockerfile") @'
FROM nginx:alpine
COPY dashboard-dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
'@

Write-Utf8NoBom (Join-Path $dashboardCtx "nginx.conf") @'
server {
  listen 80;
  server_name localhost;
  location /api/ {
    proxy_pass http://irx-backend:18116/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }
  location / {
    root /usr/share/nginx/html;
    index index.html;
    try_files $uri /index.html;
  }
}
'@

docker build -t "irx-backend-demo:$Version" $backendCtx
docker build -t "irx-dashboard-demo:$Version" $dashboardCtx
docker pull swaggerapi/swagger-ui:latest
docker save "irx-backend-demo:$Version" -o (Join-Path $imagesDir "irx-backend-demo.tar")
docker save "irx-dashboard-demo:$Version" -o (Join-Path $imagesDir "irx-dashboard-demo.tar")
docker save "swaggerapi/swagger-ui:latest" -o (Join-Path $imagesDir "swagger-ui.tar")

New-Item -ItemType Directory -Force -Path (Join-Path $docsDir "openapi") | Out-Null
Copy-Item (Join-Path $root "docs\openapi\irx-api-v1.yaml") (Join-Path $docsDir "openapi\irx-api-v1.yaml")
Copy-Item (Join-Path $root "docs\API_DEMO_GUIDE.md") $docsDir -ErrorAction SilentlyContinue
Copy-Item (Join-Path $root "docs\DYNAMIC_DISPATCH.md") $docsDir -ErrorAction SilentlyContinue

$evidenceFiles = @(
  "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/final/final-summary.json",
  "artifacts/test-reports/v0.9.11-dynamic-ml-dispatch/dynamic-6case-benchmark/dynamic-6case-summary.json",
  "artifacts/test-reports/v0.9.12-live-dashboard/live-dashboard/live-dashboard-summary.json",
  "artifacts/test-reports/v0.9.12-live-dashboard/live-map/live-map-dashboard-summary.json"
)
foreach($relative in $evidenceFiles) {
  $source = Join-Path $root $relative
  if(Test-Path $source) { Copy-Item $source (Join-Path $evidenceDir (Split-Path $relative -Leaf)) }
}

@"
services:
  irx-backend:
    image: irx-backend-demo:$Version
    container_name: irx-backend-demo
    ports:
      - "18116:18116"
    environment:
      SPRING_PROFILES_ACTIVE: demo
      SERVER_PORT: 18116
      IRX_DEMO_MODE: "true"
      IRX_API_KEY: demo-key
      IRX_TENANT_ID: demo
  irx-dashboard:
    image: irx-dashboard-demo:$Version
    container_name: irx-dashboard-demo
    ports:
      - "5173:80"
    depends_on:
      - irx-backend
  swagger-ui:
    image: swaggerapi/swagger-ui:latest
    container_name: irx-swagger-demo
    ports:
      - "8088:8080"
    environment:
      SWAGGER_JSON: /api/irx-api-v1.yaml
    volumes:
      - ./docs/openapi:/api
"@ | Set-Content -Encoding UTF8 (Join-Path $packageDir "docker-compose.yml")

Write-Utf8NoBom (Join-Path $packageDir "run-demo.ps1") @'
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
function Invoke-DemoNative([scriptblock]$Command) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $Command
    if($LASTEXITCODE -ne 0) { throw "native command failed with exit code $LASTEXITCODE" }
  } finally { $ErrorActionPreference = $old }
}
Invoke-DemoNative { docker load -i (Join-Path $here "images\irx-backend-demo.tar") }
Invoke-DemoNative { docker load -i (Join-Path $here "images\irx-dashboard-demo.tar") }
Invoke-DemoNative { docker load -i (Join-Path $here "images\swagger-ui.tar") }
Invoke-DemoNative { docker compose -f (Join-Path $here "docker-compose.yml") up -d }
Write-Host "Dashboard realtime: http://localhost:5173/live-dispatch-demo"
Write-Host "Swagger UI:         http://localhost:8088"
Write-Host "Backend API:        http://localhost:18116/api/v1"
'@

Write-Utf8NoBom (Join-Path $packageDir "stop-demo.ps1") @'
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$old = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  docker compose -f (Join-Path $here "docker-compose.yml") down
  if($LASTEXITCODE -ne 0) { throw "docker compose down failed with exit code $LASTEXITCODE" }
} finally { $ErrorActionPreference = $old }
'@

Write-Utf8NoBom (Join-Path $packageDir "verify-demo.ps1") @'
$ErrorActionPreference = "Stop"
$headers = @{ "X-Api-Key" = "demo-key"; "X-Tenant-Id" = "demo" }
function Assert-HttpOk([string]$Url) {
  $code = & curl.exe -sS --max-time 30 -o NUL -w "%{http_code}" $Url
  if($LASTEXITCODE -ne 0 -or [int]$code -lt 200 -or [int]$code -ge 300) { throw "HTTP check failed $Url status=$code" }
}
Assert-HttpOk "http://localhost:18116/api/v1/health"
Assert-HttpOk "http://localhost:5173/live-dispatch-demo"
Assert-HttpOk "http://localhost:8088"
$job = Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs" -Headers $headers -ContentType "application/json" -Body '{"jobId":"portable-smoke","tenantId":"demo"}' -TimeoutSec 30
Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs/$($job.jobId)/orders" -Headers $headers -ContentType "application/json" -Body '{"orders":[{"orderId":"PORTABLE-1","pickup":{"lat":10.75,"lng":106.70},"dropoff":{"lat":10.82,"lng":106.78},"deadline":"2026-05-20T10:30:00Z","load":1,"priority":"HIGH"}]}' -TimeoutSec 30 | Out-Null
Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs/$($job.jobId)/drivers/D01/telemetry" -Headers $headers -ContentType "application/json" -Body '{"driverId":"D01","lat":10.76,"lng":106.71,"status":"EN_ROUTE","currentStopId":"PICKUP:PORTABLE-1"}' -TimeoutSec 30 | Out-Null
$cycle = Invoke-RestMethod -Method Post -Uri "http://localhost:18116/api/v1/live/jobs/$($job.jobId)/cycle" -Headers $headers -ContentType "application/json" -Body '{"returnDiagnostics":true}' -TimeoutSec 30
if(-not $cycle.forecastUsed -or -not $cycle.triModelRepairUsed) { throw "dynamic cycle smoke failed" }
Write-Host "IRX Docker demo verification PASS"
'@

$zip = Join-Path (Join-Path $root $OutputRoot) "$PackageName.zip"
[pscustomobject]@{ packageDir=$packageDir; zip=$zip; backendImage="irx-backend-demo:$Version"; dashboardImage="irx-dashboard-demo:$Version" } | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $packageDir "pack-summary.json")
if(Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $packageDir -DestinationPath $zip -Force

Write-Host "[DOCKER-PACK] package=$packageDir"
Write-Host "[DOCKER-PACK] zip=$zip"
