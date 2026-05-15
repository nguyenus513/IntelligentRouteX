export type RunStatus = 'CREATED' | 'GENERATING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
export type UiState = 'empty' | 'loading' | 'success' | 'error' | 'partial' | 'evidence_gap';
export type GeometryMode = 'STRAIGHT_LINE' | 'ROAD_ROUTE' | 'IMPORTED_POLYLINE';
export type BenchmarkVerdict = 'WIN' | 'LOSE' | 'TIE' | 'PASS_WITH_LIMITS' | 'EVIDENCE_GAP' | 'NOT_RUN' | 'FAILED';

export interface OrderDto {
  orderId: string;
  restaurantId: string;
  pickupLat: number;
  pickupLng: number;
  dropoffLat: number;
  dropoffLng: number;
  demand: number;
  priority: number;
  deadlineMinutes: number;
}

export interface DriverDto {
  driverId: string;
  lat: number;
  lng: number;
  capacity: number;
  currentLoad: number;
  status: string;
}

export interface BatchDto {
  batchId: string;
  orderIds: string[];
  driverId: string;
  color: string;
  status: string;
}

export interface AssignmentDto {
  assignmentId: string;
  batchId: string;
  driverId: string;
  orderIds: string[];
  selectionRank: number;
  selectionScore: number;
  robustUtility: number;
  reasons: string[];
  degradeReasons: string[];
}

export interface StopVisualizationDto {
  sequence: number;
  type: 'PICKUP' | 'DROPOFF' | string;
  orderId: string;
  lat: number;
  lng: number;
  etaMinutes: number;
  distanceFromPreviousKm: number;
  travelTimeFromPreviousMinutes: number;
  deadlineSlackMinutes: number;
  riskLevel: string;
  status: string;
}

export interface RouteVisualizationDto {
  routeId: string;
  driverId: string;
  batchId: string;
  geometryMode: GeometryMode;
  oldRouteId?: string | null;
  rescueStatus: string;
  stops: StopVisualizationDto[];
  polyline: { lat: number; lng: number }[];
  totalDistanceKm: number;
  totalEtaMinutes: number;
  lateOrderCount: number;
}

export interface MetricsDto {
  driverCount: number;
  totalDistanceKm: number;
  lateOrderCount: number;
  assignedOrderCount: number;
  slaSuccessRate: number;
  runtimeMs: number;
  batchCount: number;
  rejectedOrderCount: number;
}

export interface EventDto {
  type: string;
  label: string;
  severity: string;
}

export interface ComparisonDto {
  beforeRunId?: string | null;
  afterRunId?: string | null;
  label: string;
  verdict: BenchmarkVerdict;
  reason: string;
}

export interface RunVisualizationDto {
  runId: string;
  scenarioId: string;
  solverName: string;
  solverVersion: string;
  createdAt: string;
  status: RunStatus;
  inputSnapshot: Record<string, unknown>;
  orders: OrderDto[];
  drivers: DriverDto[];
  batches: BatchDto[];
  assignments: AssignmentDto[];
  routes: RouteVisualizationDto[];
  metrics: MetricsDto;
  diagnostics: Record<string, unknown>;
  events: EventDto[];
  comparison?: ComparisonDto | null;
  artifacts: Record<string, unknown>;
}

export interface ScenarioGenerateRequest {
  orderCount: number;
  driverCount: number;
  scenarioType: string;
  weatherProfile: string;
  trafficMode: string;
  riskRate: number;
}

export interface DashboardRun {
  runId: string;
  kind: string;
  createdAt: string;
  status: RunStatus;
  visualization: RunVisualizationDto;
}

export interface BenchmarkJob {
  jobId: string;
  datasetId: string;
  solvers: string[];
  status: RunStatus;
  createdAt: string;
  resultRunId?: string | null;
  error?: string | null;
}
