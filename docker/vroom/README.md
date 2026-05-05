# VROOM Deployment Pack

This pack runs VROOM as the industry-standard champion baseline for IntelligentRouteX benchmark comparisons.

## Start

```powershell
docker compose -f docker/vroom/docker-compose.yml up -d
docker/vroom/healthcheck.cmd
```

If Docker Desktop is installed but the daemon is stopped, start Docker Desktop first. If the container is healthy internally but `localhost:3000` does not respond, recreate it so the port mapping is applied:

```powershell
Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
docker compose -f docker/vroom/docker-compose.yml down
docker compose -f docker/vroom/docker-compose.yml up -d --force-recreate
docker port intelligentroutex-vroom 3000
```

## Health Check

Use `/health` for readiness checks:

```powershell
curl -w "%{http_code}" http://localhost:3000/health
```

On Windows, prefer `docker/vroom/healthcheck.cmd` because local PowerShell execution policy may block `healthcheck.ps1`.

`GET /` may return `404`; that is not a VROOM service failure. The benchmark runner posts optimization requests to `http://localhost:3000`.

## Comparator

```powershell
py -3.13 scripts/run_phase58a_vroom_industry_comparator.py `
  --instances lrc202,lrc106 `
  --vroom-url http://localhost:3000 `
  --vroom-timeout-seconds 120 `
  --challenger-time-limit 30s `
  --output-dir artifacts/benchmark/community-phase58b-vroom-smoke-v1
```
