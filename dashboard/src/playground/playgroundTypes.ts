export type PlaygroundMode = 'STATIC_DISPATCH' | 'LIVE_ROLLING' | 'RESCUE' | 'BIGDATA_LITE';
export type AdaptiveMode = 'QUALITY_SEEKING' | 'TOP_K_ASSISTED';
export type JobStatusValue = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'TIMEOUT' | 'DEAD_LETTER' | string;

export interface ApiMeta { version: string; timestamp: string }
export interface ApiError { code: string; message: string; details?: Array<{ field?: string; reason?: string }> }
export interface ApiEnvelope<T> { ok: boolean; requestId: string; data: T; error?: ApiError; meta: ApiMeta }

export interface JobStatus {
  jobId: string;
  status: JobStatusValue;
  mode?: string;
  progress?: { stage: string; percent: number };
  links?: Record<string, string>;
  idempotency?: { key: string; replayed: boolean; originalResourceId: string };
}

export interface StaticResult {
  mode?: string;
  finalSolver?: string;
  status?: JobStatusValue;
  summary?: { assignedOrders?: number; routeCount?: number; totalKm?: number; lateCount?: number };
  coverage?: { assigned: number; total: number; rate: number };
  metrics?: { distanceKm?: number; lateCount?: number; runtimeMs?: number };
  routes?: unknown[];
  diagnostics?: Record<string, unknown>;
}

export interface EventRecord { eventId: string; type: string; jobId?: string; timestamp: string; data?: Record<string, unknown> }
export interface ArtifactRecord { artifactId: string; type?: string; path?: string; downloadUrl?: string; createdAt?: string }
export interface LiveState { running: boolean; mode: string; bufferedOrders: number; activeDrivers: number; completedCycles: number; lastCycleId: string }
export interface CycleResponse { cycleId: string; status?: string; assigned?: number; lateRegression?: number; capacityViolations?: number }
export interface RescueResult { mode: string; beforeLate: number; afterLate: number; lateNotWorse: boolean; rescuedRouteCount: number; rescueDominanceGuard: { passed: boolean; rollbackApplied: boolean } }
export interface BatchResponse { batchId: string; status: string; accepted?: number; rejected?: number; totalItems?: number; normalizedItems?: number; processedItems?: number; deadLetterItems?: number; queuedItems?: number; jobId?: string }
export interface RuntimeMetrics { jobsCreated?: number; jobsCompleted?: number; jobsFailed?: number; artifactCount?: number; eventCount?: number; latestTelemetryCount?: number }
export interface PageResult<T> { items: T[]; count?: number; total?: number; page?: number; size?: number; nextCursor?: string }

export interface PlaygroundSnapshot {
  scenarioId: string;
  mode: PlaygroundMode;
  adaptiveMode: AdaptiveMode;
  job?: JobStatus;
  staticResult?: StaticResult;
  liveState?: LiveState;
  cycle?: CycleResponse;
  rescue?: RescueResult;
  batch?: BatchResponse;
  batchItems?: PageResult<Record<string, unknown>>;
  events: EventRecord[];
  artifacts: ArtifactRecord[];
  metrics?: RuntimeMetrics;
  raw: { lastRequest?: unknown; lastResponse?: unknown; result?: unknown };
}

