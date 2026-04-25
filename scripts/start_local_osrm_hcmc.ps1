param(
    [string]$DataDir = "artifacts/osrm",
    [string]$ContainerName = "irx-osrm-hcmc",
    [int]$Port = 5000,
    [string]$BBox = "10.72,106.62,10.92,106.92",
    [switch]$RefreshOsm,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Require-Command docker
Require-Command curl.exe

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$dataPath = Join-Path $root $DataDir
New-Item -ItemType Directory -Force -Path $dataPath | Out-Null

$queryPath = Join-Path $dataPath "hcmc-demo.overpassql"
$osmPath = Join-Path $dataPath "hcmc-demo.osm"
$osrmPath = Join-Path $dataPath "hcmc-demo.osrm"

if ($RefreshOsm -or -not (Test-Path $osmPath)) {
    $parts = $BBox.Split(",") | ForEach-Object { $_.Trim() }
    if ($parts.Count -ne 4) {
        throw "BBox must be south,west,north,east. Received: $BBox"
    }
    @"
[out:xml][timeout:180];
(
  way["highway"]($($parts[0]),$($parts[1]),$($parts[2]),$($parts[3]));
);
(._;>;);
out meta;
"@ | Out-File -Encoding ascii $queryPath
    curl.exe -L --fail --retry 2 --connect-timeout 20 --max-time 240 `
        --data-urlencode "data@$queryPath" `
        https://overpass-api.de/api/interpreter `
        -o $osmPath
}

docker pull osrm/osrm-backend | Out-Host

if ($Rebuild -or -not (Test-Path $osrmPath)) {
    docker run --rm -t -v "${dataPath}:/data" osrm/osrm-backend `
        osrm-extract -p /opt/car.lua /data/hcmc-demo.osm | Out-Host
    docker run --rm -t -v "${dataPath}:/data" osrm/osrm-backend `
        osrm-contract /data/hcmc-demo.osrm | Out-Host
}

docker rm -f $ContainerName 2>$null | Out-Null
docker run -d --name $ContainerName -p "${Port}:5000" -v "${dataPath}:/data" osrm/osrm-backend `
    osrm-routed --algorithm ch /data/hcmc-demo.osrm | Out-Host

Start-Sleep -Seconds 2
$probe = "http://127.0.0.1:$Port/route/v1/driving/106.80492595201288,10.82623405271979;106.80231414260554,10.845983709900159?overview=full&geometries=geojson&steps=false"
$response = curl.exe -s -S $probe
if ($LASTEXITCODE -ne 0 -or $response -notmatch '"code"\s*:\s*"Ok"') {
    throw "OSRM probe failed on port $Port. Response: $response"
}

Write-Host "OSRM ready: http://127.0.0.1:$Port"
Write-Host "Use: `$env:IRX_ROUTING_PROVIDER='osrm'; `$env:IRX_ROUTING_BASE_URL='http://127.0.0.1:$Port'"
