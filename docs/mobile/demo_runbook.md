# RouteFood Demo Runbook

## Prerequisites

- Java 21 for the backend.
- Node 20 for Firebase Functions.
- Android SDK or the local `.android-sdk/` created by diagnostics.
- A Firebase project or local emulators.

## Start Firebase Emulators

```powershell
cd functions
npm run serve
```

## Seed HCMC Demo Data

In another terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\seed_hcm_demo.ps1
```

The seed writes deterministic restaurants, menu items, demo drivers, traffic hotspots, and demo weather.

## Run Foundation Diagnostics

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnose_mobile_foundation.ps1
```

## Android App

Open `android/routefood-app/` in Android Studio and run the `app` module. Add a local `app/google-services.json` only when connecting to a real Firebase project. Do not commit it.

## Current Demo Flow

1. Login/register or continue with local demo fallback.
2. Choose User mode.
3. Home reads seeded `restaurants` and renders HCMC restaurant cards.
4. Restaurant Detail and Cart are implemented as MVP screens.
5. Checkout calls `createUserOrder` when Firebase Functions are configured.
6. `dispatchOrder` assigns the nearest available demo driver as fallback.
