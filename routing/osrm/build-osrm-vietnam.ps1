$ErrorActionPreference = "Stop"

$DataFile = "vietnam-latest.osm.pbf"
$DataUrl = "https://download.geofabrik.de/asia/vietnam-latest.osm.pbf"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to build and run OSRM route data."
}

if (-not (Test-Path $DataFile)) {
    Write-Host "Downloading Vietnam OSM PBF..."
    Invoke-WebRequest -Uri $DataUrl -OutFile $DataFile
}

Write-Host "Extracting OSRM graph..."
docker run --rm -t -v ${PWD}:/data osrm/osrm-backend osrm-extract -p /opt/car.lua /data/$DataFile

Write-Host "Partitioning OSRM graph..."
docker run --rm -t -v ${PWD}:/data osrm/osrm-backend osrm-partition /data/vietnam-latest.osrm

Write-Host "Customizing OSRM graph..."
docker run --rm -t -v ${PWD}:/data osrm/osrm-backend osrm-customize /data/vietnam-latest.osrm

Write-Host "Done. Start OSRM with: .\run-osrm.ps1"
