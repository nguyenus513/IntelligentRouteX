# Runtime Deployment

`v1.0.1-irx-all-in-one-benchmark-certified` defines two runtime modes:

- Local: `powershell -ExecutionPolicy Bypass -File scripts/irx.ps1 up`
- Docker: `docker compose -f docker-compose.allinone.yml up --build`

The all-in-one runtime must expose `/v1/health` with solver readiness for VROOM, OR-Tools, PyVRP, and Adaptive ML QUALITY_SEEKING.
Compare/benchmark mode requires VROOM, OR-Tools, and PyVRP readiness. Missing required solvers return `SOLVER_UNAVAILABLE` instead of silently degrading compare evidence.
