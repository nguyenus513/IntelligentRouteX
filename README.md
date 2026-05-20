# IntelligentRouteX

Java/Spring Boot dispatch optimization backend.

Current repo cleanup status:
- React dashboard/playground source removed.
- Android/mobile demo worktrees removed locally.
- Generated artifacts, build output, release zips, data dumps, and local caches removed locally.
- Backend API, optimization core, ML worker services, benchmark scripts, and Gradle build remain.

Run backend compile:

```powershell
.\gradlew.bat compileJava --no-daemon --console=plain
```

Run backend API locally:

```powershell
.\gradlew.bat bootRun --args="--server.port=18116"
```

Primary backend docs:
- `docs/API_REFERENCE.md`
- `docs/API_EXAMPLES.md`
- `docs/DYNAMIC_DISPATCH.md`
- `docs/ADAPTIVE_ML_POLICY.md`
- `docs/BENCHMARKS.md`
- `docs/REPO_CLEANUP.md`
