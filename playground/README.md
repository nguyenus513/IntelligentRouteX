# IRX Control Tower Playground

React/Vite client for the real IRX backend API.

## Start

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\irx.ps1 up
cd playground
npm install
npm run dev
```

Open: `http://localhost:5173`

The dev server proxies `/irx-api/*` to `http://localhost:18116/*`, avoiding browser CORS issues.

## API Used

- `GET /v1/health`
- `GET /v1/version`
- `POST /v1/dispatch/jobs`
- `GET /v1/dispatch/jobs/{jobId}`
- `GET /v1/dispatch/jobs/{jobId}/result`
- `POST /v1/live/sessions`
- `POST /v1/live/sessions/{id}/orders`
- `POST /v1/live/sessions/{id}/cycles`
- `GET /v1/live/sessions/{id}/state`
- `POST /v1/compare/jobs`
- `GET /v1/compare/jobs/{jobId}/result`
- `GET /v1/executions/{executionId}/timeline`
- `GET /v1/executions/{executionId}/events`

## Note

Map projection falls back to synthetic HCM SVG nodes if the backend result has no route geometry.
