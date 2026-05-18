import type { ApiEnvelope, ApiHealth, ApiHealthSnapshot, ArtifactRecord, BatchResponse, CycleResponse, EventRecord, JobStatus, LiveState, PageResult, RescueResult, RuntimeMetrics, StaticResult } from './playgroundTypes';

const DEFAULT_API_BASE = '/api/v1';
const DEFAULT_TIMEOUT_MS = 15_000;
const BIGDATA_TIMEOUT_MS = 30_000;

export const API_BASE = resolveApiBase();

export class PlaygroundApiError extends Error {
  constructor(
    public readonly code: 'BACKEND_UNAVAILABLE' | 'API_TIMEOUT' | 'INVALID_JSON_RESPONSE' | 'API_ERROR' | 'CORS_OR_NETWORK_ERROR',
    message: string,
    public readonly status?: number
  ) {
    super(message);
    this.name = 'PlaygroundApiError';
  }
}

function resolveApiBase(): string {
  const configured = import.meta.env.VITE_IRX_API_BASE_URL as string | undefined;
  if (configured?.trim()) return configured.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location.port === '18116') return `${window.location.origin}/api/v1`;
  return DEFAULT_API_BASE;
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Api-Key': 'demo-key',
        'X-Tenant-Id': 'demo',
        ...(init.headers ?? {})
      }
    });
  } catch (cause) {
    const aborted = cause instanceof DOMException && cause.name === 'AbortError';
    throw new PlaygroundApiError(
      aborted ? 'API_TIMEOUT' : 'BACKEND_UNAVAILABLE',
      aborted ? `API timed out after ${Math.round(timeoutMs / 1000)}s at ${API_BASE}.` : `Backend offline or blocked. Expected API: ${API_BASE}. Run: .\\scripts\\irx.ps1 up`,
    );
  } finally {
    window.clearTimeout(timer);
  }

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    const text = await response.text().catch(() => '');
    throw new PlaygroundApiError('INVALID_JSON_RESPONSE', `Invalid API response from ${API_BASE}${path}. Expected JSON, got ${contentType || 'empty'}${text ? `: ${text.slice(0, 120)}` : ''}`, response.status);
  }

  const envelope = await response.json().catch(() => {
    throw new PlaygroundApiError('INVALID_JSON_RESPONSE', `Invalid JSON response from ${API_BASE}${path}.`, response.status);
  }) as ApiEnvelope<T>;

  if (!response.ok || !envelope.ok) {
    const code = envelope.error?.code ?? `HTTP_${response.status}`;
    const message = envelope.error?.message ?? response.statusText ?? 'API error';
    throw new PlaygroundApiError('API_ERROR', `${code}: ${message}`, response.status);
  }
  return envelope.data;
}

export async function checkApiHealth(): Promise<ApiHealthSnapshot> {
  try {
    const health = await request<ApiHealth>('/health', { method: 'GET' }, 5_000);
    return { state: 'online', apiBase: API_BASE, message: `Backend online: ${health.status ?? 'UP'}`, health };
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : `Backend offline. Expected API: ${API_BASE}. Run: .\\scripts\\irx.ps1 up`;
    return { state: 'offline', apiBase: API_BASE, message };
  }
}

export function describeApiError(cause: unknown): string {
  if (cause instanceof PlaygroundApiError) return `${cause.code}: ${cause.message}`;
  if (cause instanceof TypeError) return `CORS_OR_NETWORK_ERROR: Backend offline or CORS blocked. Expected API: ${API_BASE}. Run: .\\scripts\\irx.ps1 up`;
  return cause instanceof Error ? cause.message : 'Playground API flow failed';
}

export async function runStaticScenario(input: { scenarioId: string; adaptiveMode: string }): Promise<JobStatus> {
  return request<JobStatus>('/static/dispatch/jobs', {
    method: 'POST',
    headers: { 'Idempotency-Key': `playground-static-${input.scenarioId}-${input.adaptiveMode}` },
    body: JSON.stringify({
      scenarioId: input.scenarioId,
      orders: [],
      drivers: [],
      policy: { adaptiveMlPolicyMode: input.adaptiveMode, adaptiveTopKMoves: 30, adaptiveExplorationRate: 0.1, coverageMode: 'DRAIN_UNTIL_ACCOUNTED' },
      options: { includeDiagnostics: true, includeArtifacts: true }
    })
  });
}

export async function runLiveDemo(): Promise<CycleResponse> {
  await request<LiveState>('/live/start', { method: 'POST', body: JSON.stringify({}) });
  await request<{ accepted: boolean }>('/live/orders', { method: 'POST', body: JSON.stringify({ orderId: `LIVE-${Date.now()}`, pickup: { lat: 10.77, lng: 106.69 }, dropoff: { lat: 10.8, lng: 106.72 } }) });
  await request<{ accepted: boolean }>('/live/drivers/location', { method: 'POST', body: JSON.stringify({ driverId: 'D-LIVE-1', lat: 10.78, lng: 106.7 }) });
  return request<CycleResponse>('/live/cycles/run-now', { method: 'POST', body: JSON.stringify({}) });
}

export async function runRescueDemo(): Promise<JobStatus> {
  return request<JobStatus>('/rescue/jobs', { method: 'POST', body: JSON.stringify({ reason: 'DRIVER_DELAYED', affectedDriverId: 'D01', affectedOrderIds: ['ORD-001'] }) });
}

export async function runBigDataDemo(): Promise<BatchResponse> {
  const stamp = Date.now();
  const items = Array.from({ length: 120 }, (_, index) => ({ orderId: `BD-${stamp}-${index}`, externalOrderId: `EXT-${index}`, lat: 10.7 + index * 0.0001, lng: 106.7 + index * 0.0001 }));
  items.push({ orderId: `BD-BAD-${stamp}`, externalOrderId: 'BAD', lat: 0, lng: 0, invalid: true } as (typeof items)[number] & { invalid: boolean });
  return request<BatchResponse>('/bigdata/batches', {
    method: 'POST',
    headers: { 'Idempotency-Key': `playground-bigdata-${stamp}` },
    body: JSON.stringify({ batchId: `BATCH-${stamp}`, tenantId: 'demo', items, options: { validationMode: 'STRICT', dedupeKey: 'externalOrderId', enqueueDispatch: true } })
  }, BIGDATA_TIMEOUT_MS);
}

export const getJob = (jobId: string) => request<JobStatus>(`/jobs/${jobId}`);
export const getJobResult = (jobId: string) => request<StaticResult>(`/jobs/${jobId}/result`);
export const getJobEvents = async (jobId: string) => (await request<PageResult<EventRecord>>(`/jobs/${jobId}/events?limit=50`)).items;
export const getJobArtifacts = (jobId: string) => request<ArtifactRecord[]>(`/jobs/${jobId}/artifacts`);
export const getLiveState = () => request<LiveState>('/live/state');
export const getLiveEvents = async () => (await request<PageResult<EventRecord>>('/live/events?limit=50')).items;
export const getRescueResult = (jobId: string) => request<RescueResult>(`/rescue/jobs/${jobId}/result`);
export const getBatch = (batchId: string) => request<BatchResponse>(`/bigdata/batches/${batchId}`);
export const getBatchItems = (batchId: string) => request<PageResult<Record<string, unknown>>>(`/bigdata/batches/${batchId}/items?page=0&size=50`);
export const getRuntimeMetrics = () => request<RuntimeMetrics>('/metrics');
