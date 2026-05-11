# Driver Routing V2: IntelligentRouteX + Valhalla

## Goal

IntelligentRouteX owns dispatch intelligence and stop ordering. The routing provider owns road-network navigation for the fixed stop order.

```text
IntelligentRouteX Core
  -> fixed routePlan.sequence: DR -> P/D...
RoutingProvider V2
  -> snap/route/quality for that fixed order
Android MapLibre
  -> render roadRoute.coordinates + DR/P/D markers
```

## Android Provider Chain

The driver demo now uses:

```text
OsrmRoutingProvider(primary local prebuilt OSM graph)
  fallback -> OsrmRoutingProvider(public fixed-order route)
```

Use local OSRM when you want the app to use prebuilt road-route data instead of drawing or measuring routes in-app.

Build with local OSRM:

```powershell
cd android/routefood-app
.\gradlew.bat :app:assembleDebug -POSRM_BASE_URL=http://10.0.2.2:5000
```

Default Valhalla URL for Android emulator:

```text
http://10.0.2.2:8002
```

If Valhalla is not running, the app falls back to OSRM fixed-order routing automatically.

## Why Valhalla

- Better navigation-style turn-by-turn support.
- Supports costing models suitable for delivery routing.
- Can run self-hosted with OSM data.
- Lets IntelligentRouteX keep pickup/dropoff ordering constraints while Valhalla handles road geometry.

## Valhalla Request Shape

The app sends fixed waypoints only:

```json
{
  "locations": [
    {"lat": 10.776, "lon": 106.704, "type": "break"},
    {"lat": 10.7741, "lon": 106.7038, "type": "break"}
  ],
  "costing": "motor_scooter",
  "costing_options": {
    "motor_scooter": {
      "use_highways": 0.05,
      "use_tolls": 0.0,
      "top_speed": 60
    }
  },
  "shape_format": "geojson"
}
```

## Rules

- Do not call TSP/trip optimization from the routing provider.
- Do not let routing reorder pickup/dropoff stops.
- Do not append raw DR/P/D points into the route polyline.
- Render markers separately from route geometry.
- Use connector lines only as a separate visual layer if raw display point differs from snapped navigation point.

## Production Next Step

Run a self-hosted Valhalla service for the target city/region and expose it to the Android app through the backend, not directly from mobile in production.

## Local Route Data Server

Preferred local production-free route data server:

```text
routing/osrm
```

Build the OSRM graph:

```powershell
cd routing/osrm
.\build-osrm-vietnam.ps1
```

Run OSRM:

```powershell
.\run-osrm.ps1
```

The Android app will call `http://10.0.2.2:5000` by default.

## Alternative Local Route Data Server

The repository includes a local Valhalla route-data stack:

```text
routing/valhalla/docker-compose.yml
```

Start it with:

```powershell
cd routing/valhalla
docker compose up -d
```

This downloads/builds a Vietnam OSM routing graph. Once it is running, the Android emulator uses:

```text
http://10.0.2.2:8002
```

The app no longer needs to invent route geometry. It asks Valhalla for road geometry over the fixed IntelligentRouteX stop order.
