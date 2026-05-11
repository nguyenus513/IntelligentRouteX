# IntelligentRouteX Valhalla Route Data

This folder runs a self-hosted Valhalla routing server so the Driver app can draw routes from a real road graph instead of relying on public fallback routing.

## Start Valhalla

```powershell
cd routing/valhalla
docker compose up -d
```

The first run downloads Vietnam OSM PBF data and builds Valhalla tiles. This can take a while and needs disk space.

Android emulator URL:

```text
http://10.0.2.2:8002
```

Host machine URL:

```text
http://localhost:8002
```

## Test Route API

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8002/route `
  -ContentType 'application/json' `
  -Body '{"locations":[{"lat":10.776,"lon":106.704,"type":"break"},{"lat":10.7741,"lon":106.7038,"type":"break"}],"costing":"motor_scooter","shape_format":"geojson"}'
```

## Android Build Override

Default app config already points emulator to Valhalla:

```text
VALHALLA_BASE_URL=http://10.0.2.2:8002
```

Override if needed:

```powershell
.\gradlew.bat :app:assembleDebug -PVALHALLA_BASE_URL=http://10.0.2.2:8002
```

## Routing Rule

Valhalla must only route through the fixed `routePlan.sequence` produced by IntelligentRouteX. It must not reorder pickup/dropoff stops.

