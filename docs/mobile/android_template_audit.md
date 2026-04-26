# Android Template Audit

This project will use public food-delivery repositories as references, not as a blind code import. The current repository is the IntelligentRouteX Spring Boot dispatch core, so the Android app should be added as a clean monorepo module and wired to the backend through Firebase Cloud Functions.

## Recommended Reference Set

| Repository | Use | Risk |
| --- | --- | --- |
| `AdityaV025/Munche` | Customer flow, Firebase patterns, cart/order, map ideas | Mixed Java/Kotlin and author notes about code quality mean it should not become the base unchanged |
| `AHMED-SAFA/FoodiGo` | Java/Firebase auth, Realtime Database, Storage, order history | Simpler app, useful for patterns but not enough for driver dispatch UX |
| `androidmaycry/APPetit` | Customer/restaurant/rider feature reference | GPL-3.0 license, so do not copy code into this repository unless the whole product accepts GPL obligations |
| `sergeyCodenameOne/UberEatsClone` | UI/UX inspiration for screens and food-delivery flows | Codename One, not native Android Java XML |

## Decision

Create a clean native Android Java/XML app under `android/routefood-app/`. Import template code only after a file-by-file license and quality review. Prefer rewriting screens and adapters in RouteFood style so the product is maintainable, consistently branded, and compatible with the existing IntelligentRouteX backend.

## Non-Negotiable Cleanup Rules

- Rename all package names to `com.routefood.app`.
- Remove all third-party branding, logos, sample credentials, and template demo assets.
- Keep dispatch, assignment, role, and privileged writes outside the Android client.
- Route all sensitive actions through Firebase Cloud Functions.
- Do not copy GPL code into the app unless project licensing is explicitly changed.
- Treat map provider code as replaceable behind a small app-owned abstraction.
