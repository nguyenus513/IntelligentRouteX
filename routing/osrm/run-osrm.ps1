$ErrorActionPreference = "Stop"

if (-not (Test-Path "vietnam-latest.osrm")) {
    throw "OSRM graph is missing. Run .\build-osrm-vietnam.ps1 first."
}

docker run --rm -t -i `
    -p 5000:5000 `
    -v ${PWD}:/data `
    osrm/osrm-backend `
    osrm-routed --algorithm mld /data/vietnam-latest.osrm
