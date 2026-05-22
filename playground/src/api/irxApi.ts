const API_BASE = (import.meta.env.VITE_IRX_API_BASE ?? '/irx-api').replace(/\/$/, '');
const API_KEY = import.meta.env.VITE_IRX_API_KEY ?? 'demo-key';
const TENANT_ID = import.meta.env.VITE_IRX_TENANT_ID ?? 'demo';
const eventUrl = (path: string) => `${API_BASE}${path}${path.includes('?') ? '&' : '?'}stream=true&apiKey=${encodeURIComponent(API_KEY)}`;

export type IrxResult<T = unknown> = {
  ok: boolean;
  status: number;
  durationMs: number;
  data?: T;
  error?: string;
};

export type DispatchJobRequest = {
  requestId: string;
  tenantId: string;
  datasetId: string;
  profile: string;
  adaptiveMl?: Record<string, unknown>;
  options?: Record<string, unknown>;
  drivers?: unknown[];
  orders?: unknown[];
};

async function irxRequest<T>(path: string, init: RequestInit = {}): Promise<IrxResult<T>> {
  const started = performance.now();
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        'X-Api-Key': API_KEY,
        'X-Tenant-Id': TENANT_ID,
        'Content-Type': 'application/json',
        ...(init.headers ?? {})
      }
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : undefined;
    return { ok: res.ok, status: res.status, durationMs: Math.round(performance.now() - started), data };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      durationMs: Math.round(performance.now() - started),
      error: error instanceof Error ? error.message : 'Unknown IRX API error'
    };
  }
}

function command(path: string, body: unknown, prefix: string) {
  return irxRequest(path, {
    method: 'POST',
    headers: { 'Idempotency-Key': `${prefix}-${crypto.randomUUID()}` },
    body: JSON.stringify(body)
  });
}

export const irxApi = {
  base: API_BASE,
  health: () => irxRequest('/v1/health'),
  version: () => irxRequest('/v1/version'),
  createDispatchJob: (body: DispatchJobRequest) => command('/v1/dispatch/jobs', body, 'static'),
  getDispatchJob: (jobId: string) => irxRequest(`/v1/dispatch/jobs/${encodeURIComponent(jobId)}`),
  getDispatchResult: (jobId: string) => irxRequest(`/v1/dispatch/jobs/${encodeURIComponent(jobId)}/result`),
  createCompareJob: (body: unknown) => command('/v1/compare/jobs', body, 'compare'),
  getCompareResult: (jobId: string) => irxRequest(`/v1/compare/jobs/${encodeURIComponent(jobId)}/result`),
  cancelCompareJob: (jobId: string) => command(`/v1/compare/jobs/${encodeURIComponent(jobId)}/cancel`, {}, 'compare-cancel'),
  createLiveSession: (body: unknown) => command('/v1/live/sessions', body, 'live'),
  createRescueJob: (body: unknown) => command('/v1/rescue/jobs', body, 'rescue'),
  addLiveOrder: (sessionId: string, body: unknown) => command(`/v1/live/sessions/${encodeURIComponent(sessionId)}/orders`, body, 'order'),
  addLiveDriver: (sessionId: string, body: unknown) => command(`/v1/live/sessions/${encodeURIComponent(sessionId)}/drivers`, body, 'driver'),
  runLiveCycle: (sessionId: string, body: unknown) => command(`/v1/live/sessions/${encodeURIComponent(sessionId)}/cycles`, body, 'cycle'),
  getLiveState: (sessionId: string) => irxRequest(`/v1/live/sessions/${encodeURIComponent(sessionId)}/state`),
  getExecutionTimeline: (executionId: string) => irxRequest(`/v1/executions/${encodeURIComponent(executionId)}/timeline`),
  getExecutionEvents: (executionId: string) => irxRequest(`/v1/executions/${encodeURIComponent(executionId)}/events`),
  executionEventStreamUrl: (executionId: string) => eventUrl(`/v1/executions/${encodeURIComponent(executionId)}/events`),
  runDashboardDispatch: (body: unknown) => irxRequest('/api/v1/dashboard/dispatch/run', {
    method: 'POST',
    body: JSON.stringify(body)
  })
};

export function getStringId(data: unknown, keys: string[]): string | undefined {
  if (!data || typeof data !== 'object') return undefined;
  const record = data as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string') return value;
  }
  return undefined;
}
