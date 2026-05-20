# Repository Cleanup Record

Status: dashboard/UI and Android demo surfaces removed.

Removed dashboard surfaces:
- React/Vite dashboard source under `dashboard/`.
- Live dispatch dashboard/map/control tower pages.
- Playground dashboard pages and dashboard-specific gate scripts.
- Docker dashboard demo pack scripts and generated artifacts.
- Stale dashboard/playground documentation.

Removed Android/mobile surfaces:
- External Android app worktree under Omnara worktrees.
- Claude worktrees containing Android/dashboard experiment copies.
- Pruned stale Git worktree metadata.

Kept intentionally:
- Java backend core under `src/main/java`.
- Worker services under `services/`.
- Backend benchmark API controller classes still used by API gates despite legacy `DashboardController` naming.
- Gradle wrapper and backend build files.

Generated trash cleaned locally:
- `artifacts/`, `build/`, `dist/`, `release/`, `data/`.
- `.gradle*`, `.runtime`, `.pytest_cache`, `.portable-runtime-seeds`, `.claude`.
