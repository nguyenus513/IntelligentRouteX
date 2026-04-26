# RouteFood Android App

Native Android Java/XML app for the RouteFood + IntelligentRouteX demo.

## Current Milestone

- Clean Android project scaffold.
- RouteFood design tokens and basic Material theme.
- Splash, login, register placeholder, demo role selection, user home shell, and driver console shell.
- Firebase dependencies are declared, but real Firebase Auth wiring starts in the next milestone.

## Local Setup

1. Open `android/routefood-app/` in Android Studio.
2. Add a real Firebase `google-services.json` to `app/` locally.
3. Do not commit real Firebase config, API keys, or service account files.
4. Build the `app` module.

## Next Milestone

- Connect Firebase Auth.
- Read user role from custom claims when available.
- Keep demo role selection only for local simulator mode.
- Add repositories for restaurants, orders, drivers, and tracking.
