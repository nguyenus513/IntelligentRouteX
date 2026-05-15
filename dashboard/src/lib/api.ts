import type { BenchmarkJob, DashboardRun, RunVisualizationDto, ScenarioGenerateRequest } from '../types/dispatch';

const jsonHeaders = { 'Content-Type': 'application/json' };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  runs: () => request<DashboardRun[]>('/api/v1/dashboard/runs'),
  visualization: (runId: string) => request<RunVisualizationDto>(`/api/v1/dashboard/runs/${runId}/visualization`),
  generateScenario: (scenario: ScenarioGenerateRequest) =>
    request<RunVisualizationDto>('/api/v1/dashboard/scenario/generate', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(scenario)
    }),
  runDispatch: (scenario: ScenarioGenerateRequest, base?: RunVisualizationDto) =>
    request<RunVisualizationDto>('/api/v1/dashboard/dispatch/run', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ scenarioId: base?.scenarioId, scenario, orders: base?.orders, drivers: base?.drivers })
    }),
  simulateRescue: (baseRunId: string) =>
    request<RunVisualizationDto>('/api/v1/dashboard/rescue/simulate', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({
        baseRunId,
        events: [
          { type: 'heavy-rain', label: 'Heavy Rain', severity: 'warning' },
          { type: 'driver-cancelled', label: 'Driver cancelled mid-route', severity: 'danger' }
        ]
      })
    }),
  createBenchmarkJob: () =>
    request<BenchmarkJob>('/api/v1/dashboard/benchmarks/jobs', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ datasetId: 'synthetic-food-smoke', solvers: ['single-order', 'distance-batching', 'IntelligentRouteX'] })
    }),
  benchmarkResult: (jobId: string) => request<RunVisualizationDto>(`/api/v1/dashboard/benchmarks/jobs/${jobId}/result`)
};

export const defaultScenario: ScenarioGenerateRequest = {
  orderCount: 60,
  driverCount: 15,
  scenarioType: 'rush_hour',
  weatherProfile: 'CLEAR',
  trafficMode: 'normal',
  riskRate: 0.12
};
