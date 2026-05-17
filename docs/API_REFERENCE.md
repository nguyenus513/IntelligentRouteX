# IRX API Reference v1

Base URL: `http://localhost:18116/api/v1`.

Envelope:
- Success: `{ ok, requestId, data, meta }`
- Error: `{ ok:false, requestId, error:{ code,message,details }, meta }`

Core endpoint groups:
- Jobs: `POST /jobs`, `GET /jobs/{jobId}`, `GET /jobs/{jobId}/result`, `POST /jobs/{jobId}/cancel`, `GET /jobs/{jobId}/events`, `GET /jobs/{jobId}/artifacts`
- Static: `POST /static/dispatch`, `POST /static/dispatch/jobs`, `GET /static/dispatch/jobs/{jobId}`, `GET /static/dispatch/jobs/{jobId}/result`
- Live: `POST /live/start`, `POST /live/stop`, `GET /live/state`, `POST /live/orders`, `POST /live/drivers/location`, `POST /live/cycles/run-now`, `GET /live/cycles/{cycleId}/result`, `GET /live/events`
- Rescue: `POST /rescue/jobs`, `GET /rescue/jobs/{jobId}`, `GET /rescue/jobs/{jobId}/result`
- BigData-lite: `POST /bigdata/batches`, `GET /bigdata/batches/{batchId}`, `GET /bigdata/batches/{batchId}/items`, `GET /bigdata/dead-letter`, `POST /bigdata/dead-letter/{itemId}/requeue`, `GET /bigdata/metrics`
- Artifacts/events/metrics: `GET /artifacts`, `GET /artifacts/{artifactId}`, `GET /artifacts/{artifactId}/download`, `DELETE /artifacts/{artifactId}`, `GET /events`, `GET /metrics`, `GET /runtime/state`
