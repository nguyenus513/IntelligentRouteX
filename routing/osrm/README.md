# IntelligentRouteX OSRM Route Data Server

This is the production-free route-data path for the Driver app.

The app does not draw or invent routes. It sends the fixed stop order from IntelligentRouteX to OSRM, and OSRM returns road geometry from a prebuilt OSM routing graph.

```text
OSM PBF -> OSRM graph -> osrm-routed -> Android MapLibre route line
```

## Build Vietnam OSRM Graph

```powershell
cd routing/osrm
.\build-osrm-vietnam.ps1
```

This downloads:

```text
https://download.geofabrik.de/asia/vietnam-latest.osm.pbf
```

Then runs:

```text
osrm-extract -> osrm-partition -> osrm-customize
```

## Run OSRM

```powershell
cd routing/osrm
.\run-osrm.ps1
```

Host URL:

```text
http://localhost:5000
```

Android emulator URL:

```text
http://10.0.2.2:5000
```

## Test

```powershell
Invoke-RestMethod "http://localhost:5000/route/v1/driving/106.704,10.776;106.7038,10.7741?overview=full&geometries=geojson&steps=true"
```

## Android Config

Default debug build uses:

```text
OSRM_BASE_URL=http://10.0.2.2:5000
PUBLIC_OSRM_BASE_URL=https://router.project-osrm.org
```

Build override:

```powershell
cd android/routefood-app
.\gradlew.bat :app:assembleDebug -POSRM_BASE_URL=http://10.0.2.2:5000
```

## Rule

OSRM must only calculate road geometry for the fixed route order chosen by IntelligentRouteX. Do not use OSRM Trip/TSP to reorder pickup/dropoff stops.

