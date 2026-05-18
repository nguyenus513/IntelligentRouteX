import type { ApiEnvelope, ArtifactRecord, BatchResponse, CycleResponse, EventRecord, JobStatus, LiveState, PageResult, RescueResult, RuntimeMetrics, StaticResult } from './playgroundTypes';

const API_BASE = import.meta.env.VITE_IRX_API_BASE_URL ?? 'http://localhost:18116/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Api-Key': 'demo-key',
      ...(init?.headers ?? {})
    }
  });
  const envelope = await response.json() as ApiEnvelope<T>;
  return unwrap(envelope);
}

export function unwrap<T>(response: ApiEnvelope<T>): T {
  if (!response.ok) throw new Error(response.error?.message ?? 'API error');
  return response.data;
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
  const items = Array.from({ length: 120 }, (_, index) => ({ orderId: `BD-${Date.now()}-${index}`, externalOrderId: `EXT-${index}`, lat: 10.7, lng: 106.7 }));
  items.push({ orderId: `BD-BAD-${Date.now()}`, externalOrderId: 'BAD', lat: 0, lng: 0, invalid: true } as (typeof items)[number] & { invalid: boolean });
  return request<BatchResponse>('/bigdata/batches', {
    method: 'POST',
    headers: { 'Idempotency-Key': `playground-bigdata-${Date.now()}` },
    body: JSON.stringify({ batchId: `BATCH-${Date.now()}`, tenantId: 'demo', items, options: { validationMode: 'STRICT', dedupeKey: 'externalOrderId', enqueueDispatch: true } })
  });
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

