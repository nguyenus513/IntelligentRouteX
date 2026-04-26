# RouteFood Mobile Implementation Plan

## Architecture

- `src/` remains the Spring Boot IntelligentRouteX dispatch core.
- `android/routefood-app/` will contain the native Android Java/XML app.
- `functions/` contains Firebase Cloud Functions middleware.
- `firebase/` contains Firestore, Realtime Database, and Storage rules plus index definitions.
- Android talks to Firebase only; Cloud Functions talk to `POST /api/dispatch/v2`.

## MVP Scope

- User can sign in, browse HCMC restaurants, add menu items to cart, checkout, and watch live tracking.
- Driver can sign in, go online, receive an assignment, accept/reject it, navigate simulated pickup/dropoff, and complete delivery.
- Demo data covers HCMC restaurants, drivers, traffic hotspots, weather, ETA, and route progress.
- IntelligentRouteX remains the dispatch brain; Android only displays state and sends user/driver intents.

## Android Package Plan

- Package: `com.routefood.app`.
- Core: auth/session, Firebase repositories, functions client, location tracker, map controller, secure preferences.
- Data: model classes for users, drivers, restaurants, menu items, orders, assignments, route legs, recommendations, traffic, and weather.
- User features: splash/auth/home/search/restaurant/cart/checkout/tracking/orders/profile.
- Driver features: home/assignment/navigation/earnings/profile.
- Demo features: seed scenario controls and simulator state.

## Firebase Middleware Plan

- Callable functions: `createUserOrder`, `setDriverOnline`, `updateDriverLocation`, `driverAcceptAssignment`, `driverRejectAssignment`, `advanceDemoOrder`, `simulateNearbyDrivers`, and `simulateIncomingOrderForDriver`.
- Internal functions: `dispatchOrder`, `callIntelligentRouteX`, `refreshEta`, `generateHcmTrafficProfile`, and `generateWeatherProfile`.
- Every function validates Firebase Auth, role, payload shape, and resource ownership before writing.

## Backend Bridge

- Endpoint: `POST /api/dispatch/v2`.
- Request: existing `DispatchV2Request` contract.
- Response: existing `DispatchV2Result` contract.
- Failure mode: return a schema-valid fallback result so middleware can assign the nearest available demo driver.

## Delivery Order

1. Add backend dispatch endpoint and tests.
2. Add Firebase rules/functions skeleton.
3. Scaffold clean Android Java/XML app.
4. Implement auth and role routing.
5. Implement user order flow.
6. Implement driver assignment flow.
7. Connect functions to dispatch backend.
8. Add HCMC simulator and tracking animation.
9. Polish UI states and notification hooks.
