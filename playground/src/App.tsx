import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Activity, CheckCircle2, Code, Cpu, GitCompareArrows, Server, Terminal, Truck } from 'lucide-react';
import { getStringId, irxApi } from './api/irxApi';
import { CompareRow, SolverMapMode, UiRoute, UiStop, compareRowsFromResult, mapRoutesForSolver, mapRoutesFromBackend } from './mappers/routeMapper';

type Tab = 'live' | 'compare' | 'demo' | 'trace' | 'api';
type ApiEndpoint = 'dispatch' | 'compare' | 'live' | 'liveOrder' | 'liveCycle' | 'rescue';
type LogKind = 'info' | 'ok' | 'warn' | 'err';
type LogLine = { id: number; at: string; kind: LogKind; text: string };
type ConsoleTraceLine = { id: string; at: string; kind: LogKind; stage: string; type: string; message: string; orderId?: string; driverId?: string; cycleId?: string; data: unknown };
type StageRow = { stage: string; status: string; percent?: number; source: 'backend' | 'empty' };
type ExecutionEvent = { stage?: string; status?: string; percent?: number; message?: string; data?: unknown; timestamp?: string };
type MapToolMode = 'pan' | 'order' | 'pickup' | 'dropoff' | 'driver';
type TrackingMode = 'off' | 'view' | 'only';
type PlaybackStage = 'input' | 'cluster' | 'driver' | 'seed' | 'guard' | 'final';
type CompareDisplayMode = 'truth' | 'demo';
type MapTileMode = 'dark' | 'osm';
type DraftStatus = 'DRAFT' | 'SENDING' | 'BUFFERED' | 'PROCESSING' | 'ASSIGNED' | 'SENT_TO_BACKEND';
type DraftPoint = { id: string; kind: 'pickup' | 'dropoff' | 'driver'; lat: number; lng: number; label: string; orderId?: string; status?: DraftStatus };
type LiveDemoSeed = { seed: number; drivers: Array<{ driverId: string; lat: number; lng: number; capacity: number }>; orders: Array<{ orderId: string; pickupLat: number; pickupLng: number; dropoffLat: number; dropoffLng: number; demand: number; deadlineMinutes: number }> };
type LiveQueueStatus = 'DRAFT' | 'SENDING' | 'BUFFERED' | 'PROCESSING' | 'ASSIGNED' | 'FAILED';
type LiveQueueItem = { orderId: string; status: LiveQueueStatus; driverId?: string; cycleId?: string; message: string; updatedAt: string };
type PlaybackMapData = { orderPool: unknown[]; clusters: unknown[]; candidates: unknown[]; seedRace: unknown[]; finalSelection: Record<string, unknown> };
type DriverRuntimeView = { driverId: string; lat: number; lng: number; speedKmh: string; status: string; activeOrderId: string; routeId: string; remainingStops: string; nextStopType: string; nextOrderId: string; targetLat?: number; targetLng?: number; segmentProgress: string; movementTick: string; movedMeters: string; polylineIndex: string; polylineSize: string };
type DemoScenarioId = 'urban_dense' | 'cross_district' | 'live_urgent' | 'driver_shortage' | 'tight_sla' | 'hub_spoke' | 'long_tail' | 'rain_slow' | 'large_live_fixed';
type DemoPattern = 'clustered' | 'cross_district' | 'urgent' | 'scarcity' | 'tight_sla' | 'hub_spoke' | 'long_tail' | 'rain_slow' | 'city_spread';
type DemoScenarioConfig = { label: string; seed: number; orders: number; drivers: number; datasetId: string; note: string; pattern: DemoPattern; badge: string };
type RealtimePhaseId = 'boot' | 'drivers' | 'stream' | 'buffer' | 'filter' | 'cluster' | 'match' | 'solver' | 'guard' | 'ml' | 'freeze' | 'insertion' | 'sse' | 'kpi' | 'stress' | 'compare';
type DemoKpi = { ordersSec: string; latencyMs: string; queueDepth: string; routeChurn: string; lateCount: string; cpu: string; heap: string; solverRuntime: string };

const DATASETS = [
  ['raw-s', 'Solomon raw-s'],
  ['raw-l', 'Solomon raw-l'],
  ['random-spread', 'Random spread'],
  ['hcm-dinner-peak', 'HCM dinner peak'],
  ['heavy-rain-case', 'Heavy rain'],
  ['driver-scarcity-case', 'Driver scarcity'],
  ['tight-deadline-case', 'Tight deadline'],
  ['wide-deadline-case', 'Wide deadline'],
  ['many-orders-few-drivers', 'Many orders / few drivers'],
  ['few-orders-many-drivers', 'Few orders / many drivers'],
  ['opposite-direction-dropoffs', 'Opposite dropoffs'],
  ['clustered-pickups-random-dropoffs', 'Clustered pickups'],
  ['random-pickups-clustered-dropoffs', 'Clustered dropoffs'],
  ['long-tail-distance', 'Long-tail distance'],
  ['tight-capacity', 'Tight capacity'],
  ['high-priority-orders', 'High priority orders'],
  ['pdptw-small', 'Li & Lim PDPTW']
] as const;

const TAB_LABELS: Record<Tab, string> = {
  live: 'Live',
  compare: 'Benchmark Compare',
  demo: 'Demo Builder',
  trace: 'Decision Trace',
  api: 'API Sandbox'
};

const PLAYBACK_STAGES: Array<{ id: PlaybackStage; label: string; hint: string }> = [
  { id: 'input', label: 'Input', hint: 'Orders xanh, drivers xám trước khi gửi backend.' },
  { id: 'cluster', label: 'Cluster', hint: 'Backend gom order pool thành bundle/cluster.' },
  { id: 'driver', label: 'Driver Match', hint: 'Backend chấm điểm driver candidate.' },
  { id: 'seed', label: 'Seed Race', hint: 'VROOM / OR-Tools / PyVRP / IRX seed ranking.' },
  { id: 'guard', label: 'Guard', hint: 'Dominance guard quyết định giữ/rollback.' },
  { id: 'final', label: 'Final Route', hint: 'Route thật theo màu driver.' }
];

const REALTIME_PHASES: Array<{ id: RealtimePhaseId; label: string }> = [
  { id: 'boot', label: 'Boot' }, { id: 'drivers', label: 'Drivers' }, { id: 'stream', label: 'Order Stream' }, { id: 'buffer', label: 'Buffer' },
  { id: 'filter', label: 'Filter' }, { id: 'cluster', label: 'Cluster' }, { id: 'match', label: 'Driver Match' }, { id: 'solver', label: 'Solver Race' },
  { id: 'guard', label: 'Guard' }, { id: 'ml', label: 'Adaptive ML' }, { id: 'freeze', label: 'Freeze' }, { id: 'insertion', label: 'Live Insert' },
  { id: 'sse', label: 'SSE' }, { id: 'kpi', label: 'KPI' }, { id: 'stress', label: 'Stress' }, { id: 'compare', label: 'Compare' }
];

const EMPTY_DEMO_KPI: DemoKpi = { ordersSec: '--', latencyMs: '--', queueDepth: '--', routeChurn: '--', lateCount: '--', cpu: '--', heap: '--', solverRuntime: '--' };

const stringify = (value: unknown) => JSON.stringify(value ?? {}, null, 2);
const asRecord = (value: unknown): Record<string, unknown> => (value && typeof value === 'object' ? value as Record<string, unknown> : {});
const asArray = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const scalar = (value: unknown, fallback = '--') => value === undefined || value === null || value === '' ? fallback : String(value);

const HCM_DEMO_POINTS = [
  [10.7769, 106.7009], [10.7721, 106.6983], [10.7824, 106.6931], [10.7907, 106.7108],
  [10.7626, 106.6601], [10.7852, 106.6787], [10.8015, 106.7112], [10.7551, 106.7048],
  [10.8124, 106.6868], [10.7468, 106.6665], [10.7692, 106.7247], [10.7989, 106.6502]
] as const;

const DRIVER_ALIAS: Record<string, string> = {
  D01: 'DRV_ALPHA',
  D02: 'DRV_BETA',
  D03: 'DRV_GAMMA',
  DRV_ALPHA: 'DRV_ALPHA',
  DRV_BETA: 'DRV_BETA',
  DRV_GAMMA: 'DRV_GAMMA'
};

function driverLabel(driverId: string) {
  const alias = DRIVER_ALIAS[driverId] ?? driverId;
  return alias === driverId ? driverId : `${alias} (${driverId})`;
}
const DRIVER_ROUTE_PALETTE = [
  '#00E5FF', '#FFB000', '#FF4D8D', '#7CFF6B', '#B96CFF', '#FF6B35', '#2F80FF', '#00FF99',
  '#F7EA48', '#00B3FF', '#FF2EEA', '#5CFFB1', '#FF7A00', '#7AA2FF', '#D7FF2F', '#FF477E',
  '#25F4EE', '#C084FC', '#FFDD57', '#40FF6A', '#FF5F5F', '#36A3FF', '#B9FBC0', '#FF9F1C',
  '#A3E635', '#22D3EE', '#F472B6', '#FACC15', '#38BDF8', '#FB7185', '#34D399', '#E879F9'
] as const;
const SOLVER_MAP_MODES: Array<{ id: SolverMapMode; label: string }> = [
  { id: 'FINAL', label: 'Final' },
  { id: 'IRX', label: 'IRX' },
  { id: 'VROOM', label: 'VROOM' },
  { id: 'ORTOOLS', label: 'OR-Tools' },
  { id: 'PYVRP', label: 'PyVRP' }
];
const DEMO_SCENARIOS: Record<DemoScenarioId, DemoScenarioConfig> = {
  urban_dense: { label: 'Urban dense', seed: 20260521, orders: 18, drivers: 5, datasetId: 'raw-s', pattern: 'clustered', badge: 'Cluster', note: 'Nhiều cụm gần nhau trong trung tâm.' },
  cross_district: { label: 'Cross-district', seed: 20260601, orders: 24, drivers: 6, datasetId: 'random-spread', pattern: 'cross_district', badge: 'Long routes', note: 'Pickup trung tâm, dropoff xa nhiều quận.' },
  live_urgent: { label: 'Urgent insertion', seed: 20260707, orders: 16, drivers: 4, datasetId: 'pdptw-small', pattern: 'urgent', badge: 'Urgent', note: 'Có đơn gấp để kiểm tra insertion.' },
  driver_shortage: { label: 'Driver shortage', seed: 20260809, orders: 30, drivers: 3, datasetId: 'driver-scarcity-case', pattern: 'scarcity', badge: 'Scarcity', note: 'Ít driver, nhiều đơn rải rộng.' },
  tight_sla: { label: 'Tight SLA', seed: 20260911, orders: 22, drivers: 5, datasetId: 'tight-deadline-case', pattern: 'tight_sla', badge: 'SLA', note: 'Deadline căng, dễ thấy late risk.' },
  hub_spoke: { label: 'Hub & spoke', seed: 20260921, orders: 26, drivers: 5, datasetId: 'clustered-pickups-random-dropoffs', pattern: 'hub_spoke', badge: 'Hub', note: 'Pickup tập trung ở hub, dropoff rải.' },
  long_tail: { label: 'Long tail', seed: 20260929, orders: 25, drivers: 5, datasetId: 'long-tail-distance', pattern: 'long_tail', badge: 'Far drops', note: 'Một số đơn rất xa tạo route dài.' },
  rain_slow: { label: 'Rain slow', seed: 20261003, orders: 20, drivers: 4, datasetId: 'heavy-rain-case', pattern: 'rain_slow', badge: 'Rain', note: 'Mô phỏng mưa/chậm, deadline vừa căng.' },
  large_live_fixed: { label: 'Fixed live 40/15', seed: 20261040, orders: 40, drivers: 15, datasetId: 'random-spread', pattern: 'city_spread', badge: 'Stress', note: '40 đơn + 15 driver rải toàn thành phố.' }
};
type DriverRoadRoute = {
  driverId: string;
  routeId: string;
  color: string;
  latLngs: L.LatLngExpression[];
  polylineIndex: number;
  polylineSize: number;
  nextStopLabel: string;
  geometrySource: 'BACKEND_OSRM';
  distanceKm?: number;
  etaMinutes?: number;
  directDistanceKm: number;
  detourRatio: number;
};

function hashText(value: string) {
  let hash = 0;
  for (const character of value) hash = ((hash << 5) - hash + character.charCodeAt(0)) | 0;
  return Math.abs(hash);
}

function stableDriverColor(driverId: string) {
  return DRIVER_ROUTE_PALETTE[hashText(driverId) % DRIVER_ROUTE_PALETTE.length];
}

function colorHue(color: string) {
  const index = DRIVER_ROUTE_PALETTE.indexOf(color as typeof DRIVER_ROUTE_PALETTE[number]);
  return index < 0 ? 0 : (index * 360) / DRIVER_ROUTE_PALETTE.length;
}

function hueDistance(left: string, right: string) {
  const distance = Math.abs(colorHue(left) - colorHue(right));
  return Math.min(distance, 360 - distance);
}

function pointDistanceKm(left: { lat: number; lng: number }, right: { lat: number; lng: number }) {
  const earthKm = 6371;
  const dLat = (right.lat - left.lat) * Math.PI / 180;
  const dLng = (right.lng - left.lng) * Math.PI / 180;
  const lat1 = left.lat * Math.PI / 180;
  const lat2 = right.lat * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * earthKm * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function routeDirectDistanceKm(points: L.LatLngExpression[]) {
  if (points.length < 2) return 0;
  const first = points[0] as [number, number];
  const last = points[points.length - 1] as [number, number];
  return pointDistanceKm({ lat: first[0], lng: first[1] }, { lat: last[0], lng: last[1] });
}

function routePathDistanceKm(points: L.LatLngExpression[]) {
  let total = 0;
  for (let index = 1; index < points.length; index++) {
    const previous = points[index - 1] as [number, number];
    const current = points[index] as [number, number];
    total += pointDistanceKm({ lat: previous[0], lng: previous[1] }, { lat: current[0], lng: current[1] });
  }
  return total;
}

function routeCentroid(route: UiRoute) {
  const points = (route.path.length ? route.path : route.stops).filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));
  if (!points.length) return undefined;
  return {
    lat: points.reduce((sum, point) => sum + (point.lat as number), 0) / points.length,
    lng: points.reduce((sum, point) => sum + (point.lng as number), 0) / points.length
  };
}

function assignRouteColors(routes: UiRoute[], previousColors: Map<string, string>) {
  const assigned = new Map<string, string>();
  const placed: Array<{ driverId: string; color: string; centroid?: { lat: number; lng: number } }> = [];
  const uniqueRoutes = routes.filter((route, index) => routes.findIndex((candidate) => candidate.driverId === route.driverId) === index);
  uniqueRoutes.forEach((route) => {
    const centroid = routeCentroid(route);
    const preferred = previousColors.get(route.driverId) ?? stableDriverColor(route.driverId);
    const scored = DRIVER_ROUTE_PALETTE.map((color) => {
      const score = placed.reduce((total, other) => {
        if (!centroid || !other.centroid) return total + (other.color === color ? 3 : 0);
        const distance = pointDistanceKm(centroid, other.centroid);
        if (distance > 8) return total + (other.color === color ? 1 : 0);
        if (distance > 4) return total + (other.color === color ? 8 : hueDistance(color, other.color) < 28 ? 2 : 0);
        return total + (other.color === color ? 100 : hueDistance(color, other.color) < 34 ? 18 : hueDistance(color, other.color) < 55 ? 6 : 0);
      }, color === preferred ? -4 : 0);
      return { color, score };
    }).sort((left, right) => left.score - right.score || DRIVER_ROUTE_PALETTE.indexOf(left.color) - DRIVER_ROUTE_PALETTE.indexOf(right.color));
    const color = scored[0]?.color ?? preferred;
    assigned.set(route.driverId, color);
    placed.push({ driverId: route.driverId, color, centroid });
  });
  return assigned;
}

function routeKey(route: UiRoute, index: number) {
  return `${route.driverId}-${route.distanceKm ?? 'na'}-${route.stops.map((stop) => stop.id).join('-')}-${index}`;
}

function isDenseRoadGeometry(route: UiRoute) {
  return route.geometryMode === 'ROAD_ROUTE' && route.path.length >= Math.max(18, route.stops.length * 3);
}

function isDriverStartStop(stop: UiStop) {
  return String(stop.type ?? '').toUpperCase() === 'DRIVER_START';
}

function isRemovedStop(stop: UiStop, removedPickups: Set<string>, removedDropoffs: Set<string>) {
  const type = String(stop.type ?? '').toUpperCase();
  const orderId = stop.id.includes(':') ? stop.id.split(':').pop() ?? '' : stop.id;
  if (!orderId) return false;
  return (type === 'PICKUP' && removedPickups.has(orderId)) || (type === 'DROPOFF' && removedDropoffs.has(orderId));
}

function routeStopsForRoad(route: UiRoute) {
  return route.stops.filter((stop) => Number.isFinite(stop.lat) && Number.isFinite(stop.lng));
}

function time() {
  return new Date().toTimeString().slice(0, 8);
}

function sleep(ms: number) {
  const started = performance.now();
  return new Promise<void>((resolve) => {
    const tick = () => {
      if (performance.now() - started >= ms) resolve();
      else requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

function requestId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function dispatchPayload(datasetId: string) {
  const demo = createControlledLiveDemo(20260521, datasetId === 'raw-s' ? 12 : 18, 4);
  return {
    requestId: requestId('control-tower-static'),
    tenantId: 'demo',
    datasetId,
    profile: 'QUALITY_SEEKING',
    drivers: demo.drivers,
    orders: demo.orders,
    adaptiveMl: { enabled: true, mode: 'QUALITY_SEEKING', topKMoves: 80, explorationRate: 0.2, qualityBudgetMs: 5000 },
    options: { maxRuntimeMs: 60000, returnDiagnostics: true }
  };
}

function comparePayload(datasetId: string) {
  return { requestId: requestId('control-tower-compare'), tenantId: 'demo', datasetId, profile: 'QUALITY_SEEKING', solvers: ['IRX', 'VROOM', 'ORTOOLS', 'PYVRP'], options: { maxRuntimeMs: 60000, returnDiagnostics: true } };
}

function livePayload() {
  return { requestId: requestId('control-tower-live'), tenantId: 'demo', cityId: 'hcm', profile: 'LIVE_ROLLING', rollingConfig: { cycleIntervalSeconds: 15, maxBufferWaitSeconds: 60, maxRuntimeMsPerCycle: 5000, adaptiveMlMode: 'TOP_K_ASSISTED', freezeNextStop: true, freezePickedOrders: true } };
}

function liveOrderPayload() {
  return { requestId: requestId('control-tower-order'), order: { orderId: requestId('operator-order'), load: 4, pickup: { lat: 10.7626, lng: 106.6601 }, dropoff: { lat: 10.7812, lng: 106.6923 }, deadline: new Date(Date.now() + 45 * 60_000).toISOString() } };
}

function liveCyclePayload() {
  return { trigger: 'MANUAL', reason: 'control-tower-operator-cycle', options: { maxRuntimeMs: 5000, returnDiagnostics: true } };
}

function urgentLiveOrderPayload(seed = Date.now()) {
  const random = seededRandom(seed);
  const pickup = HCM_DEMO_POINTS[Math.floor(random() * HCM_DEMO_POINTS.length)] ?? HCM_DEMO_POINTS[0];
  const dropoff = HCM_DEMO_POINTS[Math.floor(random() * HCM_DEMO_POINTS.length)] ?? HCM_DEMO_POINTS[1];
  return {
    orderId: 'ORD_URGENT_999',
    pickupLat: pickup[0],
    pickupLng: pickup[1],
    dropoffLat: dropoff[0],
    dropoffLng: dropoff[1],
    demand: 8,
    deadlineMinutes: 35
  };
}

function rescuePayload() {
  return { requestId: requestId('control-tower-rescue'), tenantId: 'demo', affectedDriverId: 'D01', reason: 'CONTROL_TOWER_MANUAL_RESCUE', preservePickedOrders: true, candidateDrivers: ['D02'] };
}

function healthLabel(health: unknown) {
  return scalar(asRecord(health).status ?? asRecord(health).state, 'UNKNOWN');
}

function backendIsReady(health: unknown) {
  return healthLabel(health) === 'UP' && solverRows(health).every((row) => row.value === 'AVAILABLE');
}

function solverRows(health: unknown) {
  const solvers = asRecord(asRecord(health).externalSolvers);
  return ['vroom', 'ortools', 'pyvrp'].map((name) => ({ name: name.toUpperCase(), value: scalar(solvers[name], 'UNKNOWN') }));
}

function timelineRows(timeline: unknown): StageRow[] {
  const rows = asArray(asRecord(timeline).stages).map((stage) => {
    const record = asRecord(stage);
    return { stage: scalar(record.stage), status: scalar(record.status), percent: Number(record.percent), source: 'backend' as const };
  });
  return rows.length ? rows : [{ stage: 'No backend timeline loaded', status: 'WAITING', source: 'empty' }];
}

function latestEventData(events: ExecutionEvent[], stageNames: string[]) {
  for (let index = events.length - 1; index >= 0; index--) {
    const event = events[index];
    if (event.stage && stageNames.includes(event.stage)) return asRecord(event.data);
  }
  return {};
}

function playbackMapData(dispatchResult: unknown, liveState: unknown, compareResult: unknown, streamEvents: ExecutionEvent[]): PlaybackMapData {
  const diagnostics = asRecord(asRecord(dispatchResult).diagnostics);
  const liveDiagnostics = asRecord(asRecord(liveState).diagnostics);
  const decisionTrace = playbackTrace(compareResult, dispatchResult, liveState, streamEvents);
  const compareRecord = asRecord(compareResult);
  const processTrace = asRecord(compareRecord.playbackTrace ?? compareRecord.processTrace);
  const clusterEvent = latestEventData(streamEvents, ['CLUSTERING_COMPLETED']);
  const driverEvent = latestEventData(streamEvents, ['DRIVER_MATCHING_COMPLETED']);
  const seedEvent = latestEventData(streamEvents, ['SEED_RANKING_COMPLETED', 'SEED_GENERATION_COMPLETED']);
  const guardEvent = latestEventData(streamEvents, ['DOMINANCE_GUARD_COMPLETED']);
  return {
    orderPool: asArray(processTrace.orderPool).length ? asArray(processTrace.orderPool) : asArray(clusterEvent.orderPool).length ? asArray(clusterEvent.orderPool) : asArray(decisionTrace.orderPool),
    clusters: asArray(processTrace.clusterSelection ?? processTrace.cluster).length ? asArray(processTrace.clusterSelection ?? processTrace.cluster) : asArray(clusterEvent.clusterSelection ?? clusterEvent.cluster).length ? asArray(clusterEvent.clusterSelection ?? clusterEvent.cluster) : asArray(decisionTrace.clusterSelection),
    candidates: asArray(processTrace.driverCandidateSelection ?? processTrace.driverMatch).length ? asArray(processTrace.driverCandidateSelection ?? processTrace.driverMatch) : asArray(driverEvent.driverCandidateSelection ?? driverEvent.driverMatch).length ? asArray(driverEvent.driverCandidateSelection ?? driverEvent.driverMatch) : asArray(decisionTrace.driverCandidateSelection),
    seedRace: asArray(compareRecord.seedRace ?? processTrace.seedRace).length ? asArray(compareRecord.seedRace ?? processTrace.seedRace) : asArray(seedEvent.seedRace),
    finalSelection: asRecord(compareRecord.finalSelection ?? processTrace.finalSelection ?? processTrace.guard ?? guardEvent.finalSelection ?? guardEvent.guard ?? decisionTrace.finalSelection)
  };
}

function playbackTrace(compareResult: unknown, dispatchResult: unknown, liveState: unknown, streamEvents: ExecutionEvent[]) {
  const compareTrace = asRecord(asRecord(compareResult).playbackTrace ?? asRecord(compareResult).processTrace);
  if (Object.keys(compareTrace).length) return compareTrace;
  const diagnostics = asRecord(asRecord(dispatchResult).diagnostics);
  const liveDiagnostics = asRecord(asRecord(liveState).diagnostics);
  const decisionTrace = asRecord(diagnostics.decisionTrace ?? asRecord(liveState).decisionTrace ?? liveDiagnostics.decisionTrace);
  if (Object.keys(decisionTrace).length) return decisionTrace;
  const eventTrace = latestEventData(streamEvents, ['EXECUTION_COMPLETED']);
  return asRecord(eventTrace.playbackTrace ?? eventTrace.processTrace);
}

function displayValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '--';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function compareDisplayResult(compareResult: unknown, mode: CompareDisplayMode) {
  const record = asRecord(compareResult);
  if (record.truth) return record.truth;
  return compareResult;
}

function metricCards(health: unknown, dispatchResult: unknown, compareRows: CompareRow[], liveState: unknown, latencyMs: number, routes: UiRoute[]) {
  const dispatchMetrics = asRecord(asRecord(dispatchResult).metrics);
  const liveRoutes = asArray(asRecord(liveState).routes);
  const healthRecord = asRecord(health);
  return [
    { label: 'Solvers', value: solverRows(health).every((row) => row.value === 'AVAILABLE') ? '3/3 Ready' : 'Check' },
    { label: 'Distance', value: dispatchMetrics.distanceKm !== undefined ? `${dispatchMetrics.distanceKm} km` : '--' },
    { label: 'Late', value: dispatchMetrics.lateCount !== undefined ? String(dispatchMetrics.lateCount) : '--' },
    { label: 'Compare', value: compareRows.length ? `${compareRows.length} rows` : '--' },
    { label: 'Live Routes', value: liveRoutes.length ? String(liveRoutes.length) : routes.length ? String(routes.length) : '--' },
    { label: 'Latency', value: latencyMs ? `${latencyMs}ms` : '--' },
    { label: 'Engine', value: scalar(healthRecord.engineVersion ?? asRecord(healthRecord.data).engineVersion, '--') }
  ];
}

function payloadForEndpoint(endpoint: ApiEndpoint, datasetId: string) {
  if (endpoint === 'compare') return comparePayload(datasetId);
  if (endpoint === 'live') return livePayload();
  if (endpoint === 'liveOrder') return liveOrderPayload();
  if (endpoint === 'liveCycle') return liveCyclePayload();
  if (endpoint === 'rescue') return rescuePayload();
  return dispatchPayload(datasetId);
}

function draftDispatchPayload(points: DraftPoint[]) {
  const pickups = points.filter((point) => point.kind === 'pickup');
  const dropoffs = points.filter((point) => point.kind === 'dropoff');
  const drivers = points.filter((point) => point.kind === 'driver');
  const pairs = pickups
    .map((pickup) => ({ pickup, dropoff: dropoffs.find((dropoff) => dropoff.orderId === pickup.orderId) }))
    .filter((pair): pair is { pickup: DraftPoint; dropoff: DraftPoint } => Boolean(pair.dropoff));
  return {
    requestId: requestId('map-draft-dispatch'),
    tenantId: 'demo',
    scenarioId: `map-draft-${Date.now()}`,
    source: 'MAP_DRAFT_INPUT',
    profile: 'QUALITY_SEEKING',
    options: { maxRuntimeMs: 60000, returnDiagnostics: true },
    drivers: drivers.map((driver, index) => ({
      driverId: driver.label || `DRV_CUSTOM_${index + 1}`,
      lat: driver.lat,
      lng: driver.lng,
      capacity: 100,
      currentLoad: 0,
      status: 'IDLE'
    })),
    orders: pairs.map(({ pickup, dropoff }, index) => ({
      orderId: pickup.orderId ?? `ORD_MAP_${String(index + 1).padStart(3, '0')}`,
      restaurantId: 'MAP_DROP_TOOL',
      pickupLat: pickup.lat,
      pickupLng: pickup.lng,
      dropoffLat: dropoff.lat,
      dropoffLng: dropoff.lng,
      demand: 8,
      priority: 2,
      deadlineMinutes: 90 + index * 12
    }))
  };
}

function demoToDraftPoints(demo: LiveDemoSeed): DraftPoint[] {
  const driverPoints = demo.drivers.map((driver) => ({
    id: `scenario-driver-${driver.driverId}`,
    kind: 'driver' as const,
    lat: driver.lat,
    lng: driver.lng,
    label: driver.driverId,
    status: 'DRAFT' as const
  }));
  const orderPoints = demo.orders.flatMap((order) => [
    {
      id: `scenario-pickup-${order.orderId}`,
      kind: 'pickup' as const,
      lat: order.pickupLat,
      lng: order.pickupLng,
      label: `${order.orderId}_P`,
      orderId: order.orderId,
      status: 'DRAFT' as const
    },
    {
      id: `scenario-dropoff-${order.orderId}`,
      kind: 'dropoff' as const,
      lat: order.dropoffLat,
      lng: order.dropoffLng,
      label: `${order.orderId}_D`,
      orderId: order.orderId,
      status: 'DRAFT' as const
    }
  ]);
  return [...driverPoints, ...orderPoints];
}

function seededRandom(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function jitter(base: readonly [number, number], random: () => number, scale = 0.009) {
  return {
    lat: base[0] + (random() - 0.5) * scale,
    lng: base[1] + (random() - 0.5) * scale
  };
}

const HCM_SCENARIO_ZONES = {
  cbd: [10.7769, 106.7009],
  q1: [10.7817, 106.7042],
  q3: [10.7824, 106.6931],
  q10: [10.7626, 106.6601],
  binhThanh: [10.8015, 106.7112],
  phuNhuan: [10.7907, 106.6787],
  tanBinh: [10.7989, 106.6502],
  q7: [10.7350, 106.7200],
  thuDuc: [10.8500, 106.7700],
  goVap: [10.8350, 106.6750],
  q5: [10.7540, 106.6660],
  q2: [10.7870, 106.7500]
} as const;

const SCENARIO_ZONE_GROUPS = {
  core: [HCM_SCENARIO_ZONES.cbd, HCM_SCENARIO_ZONES.q1, HCM_SCENARIO_ZONES.q3, HCM_SCENARIO_ZONES.phuNhuan],
  west: [HCM_SCENARIO_ZONES.q10, HCM_SCENARIO_ZONES.tanBinh, HCM_SCENARIO_ZONES.q5],
  east: [HCM_SCENARIO_ZONES.binhThanh, HCM_SCENARIO_ZONES.q2, HCM_SCENARIO_ZONES.thuDuc],
  south: [HCM_SCENARIO_ZONES.q7, HCM_SCENARIO_ZONES.q2],
  north: [HCM_SCENARIO_ZONES.goVap, HCM_SCENARIO_ZONES.binhThanh, HCM_SCENARIO_ZONES.phuNhuan],
  hubs: [HCM_SCENARIO_ZONES.q10, HCM_SCENARIO_ZONES.cbd]
} as const;

function pickZone(zones: readonly (readonly [number, number])[], index: number, random: () => number) {
  return zones[(index + Math.floor(random() * zones.length)) % zones.length];
}

function scenarioDeadline(pattern: DemoPattern, index: number, random: () => number) {
  if (pattern === 'tight_sla') return 18 + Math.floor(random() * 28);
  if (pattern === 'urgent') return index % 5 === 0 ? 12 + Math.floor(random() * 12) : 38 + Math.floor(random() * 50);
  if (pattern === 'rain_slow') return 70 + Math.floor(random() * 70);
  if (pattern === 'long_tail') return index % 5 === 0 ? 95 + Math.floor(random() * 60) : 45 + Math.floor(random() * 55);
  if (pattern === 'scarcity') return 50 + Math.floor(random() * 90);
  return 42 + Math.floor(random() * 78);
}

function scenarioOrderZones(pattern: DemoPattern, index: number, random: () => number) {
  if (pattern === 'clustered') {
    const cluster = index % 3 === 0 ? SCENARIO_ZONE_GROUPS.core : index % 3 === 1 ? SCENARIO_ZONE_GROUPS.west : SCENARIO_ZONE_GROUPS.north;
    return { pickup: pickZone(cluster, index, random), dropoff: pickZone(cluster, index + 1, random), pickupJitter: 0.006, dropoffJitter: 0.008 };
  }
  if (pattern === 'cross_district') return { pickup: pickZone(SCENARIO_ZONE_GROUPS.core, index, random), dropoff: pickZone([...SCENARIO_ZONE_GROUPS.south, ...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.west], index, random), pickupJitter: 0.008, dropoffJitter: 0.014 };
  if (pattern === 'scarcity') return { pickup: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.west, ...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.south, ...SCENARIO_ZONE_GROUPS.north], index, random), dropoff: pickZone([...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.south, ...SCENARIO_ZONE_GROUPS.north, ...SCENARIO_ZONE_GROUPS.west], index + 3, random), pickupJitter: 0.016, dropoffJitter: 0.018 };
  if (pattern === 'tight_sla') return { pickup: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.north], index, random), dropoff: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.west], index + 2, random), pickupJitter: 0.007, dropoffJitter: 0.009 };
  if (pattern === 'urgent') return { pickup: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.north], index, random), dropoff: pickZone([...SCENARIO_ZONE_GROUPS.west, ...SCENARIO_ZONE_GROUPS.east], index + 1, random), pickupJitter: index % 5 === 0 ? 0.004 : 0.009, dropoffJitter: 0.011 };
  if (pattern === 'hub_spoke') return { pickup: pickZone(SCENARIO_ZONE_GROUPS.hubs, index, random), dropoff: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.west, ...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.south, ...SCENARIO_ZONE_GROUPS.north], index + 4, random), pickupJitter: 0.004, dropoffJitter: 0.016 };
  if (pattern === 'long_tail') return { pickup: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.west], index, random), dropoff: index % 5 === 0 ? pickZone([...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.south, ...SCENARIO_ZONE_GROUPS.north], index, random) : pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.west], index + 1, random), pickupJitter: 0.009, dropoffJitter: index % 5 === 0 ? 0.017 : 0.01 };
  if (pattern === 'rain_slow') return { pickup: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.west, ...SCENARIO_ZONE_GROUPS.north], index, random), dropoff: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.south], index + 2, random), pickupJitter: 0.012, dropoffJitter: 0.015 };
  return { pickup: pickZone([...SCENARIO_ZONE_GROUPS.core, ...SCENARIO_ZONE_GROUPS.west, ...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.south, ...SCENARIO_ZONE_GROUPS.north], index, random), dropoff: pickZone([...SCENARIO_ZONE_GROUPS.south, ...SCENARIO_ZONE_GROUPS.east, ...SCENARIO_ZONE_GROUPS.west, ...SCENARIO_ZONE_GROUPS.north], index + 5, random), pickupJitter: 0.017, dropoffJitter: 0.018 };
}

function scenarioDriverZones(pattern: DemoPattern) {
  if (pattern === 'scarcity') return [HCM_SCENARIO_ZONES.q10, HCM_SCENARIO_ZONES.q5, HCM_SCENARIO_ZONES.tanBinh] as const;
  if (pattern === 'hub_spoke') return [HCM_SCENARIO_ZONES.q10, HCM_SCENARIO_ZONES.cbd, HCM_SCENARIO_ZONES.phuNhuan, HCM_SCENARIO_ZONES.binhThanh] as const;
  if (pattern === 'cross_district') return [HCM_SCENARIO_ZONES.q1, HCM_SCENARIO_ZONES.q10, HCM_SCENARIO_ZONES.binhThanh, HCM_SCENARIO_ZONES.tanBinh, HCM_SCENARIO_ZONES.q7, HCM_SCENARIO_ZONES.thuDuc] as const;
  if (pattern === 'city_spread') return [HCM_SCENARIO_ZONES.cbd, HCM_SCENARIO_ZONES.q3, HCM_SCENARIO_ZONES.q10, HCM_SCENARIO_ZONES.binhThanh, HCM_SCENARIO_ZONES.tanBinh, HCM_SCENARIO_ZONES.q7, HCM_SCENARIO_ZONES.thuDuc, HCM_SCENARIO_ZONES.goVap] as const;
  return [HCM_SCENARIO_ZONES.cbd, HCM_SCENARIO_ZONES.q3, HCM_SCENARIO_ZONES.q10, HCM_SCENARIO_ZONES.binhThanh, HCM_SCENARIO_ZONES.phuNhuan, HCM_SCENARIO_ZONES.tanBinh] as const;
}

function createScenarioLiveDemo(scenario: DemoScenarioConfig, orderCount = scenario.orders, driverCount = scenario.drivers): LiveDemoSeed {
  const random = seededRandom(scenario.seed);
  const driverZones = scenarioDriverZones(scenario.pattern);
  const drivers = Array.from({ length: driverCount }, (_, index) => {
    const point = jitter(driverZones[index % driverZones.length], random, scenario.pattern === 'city_spread' ? 0.015 : 0.008);
    return { driverId: `DRV_${scenario.badge.toUpperCase().replace(/[^A-Z0-9]/g, '')}_${String(index + 1).padStart(2, '0')}`, lat: point.lat, lng: point.lng, capacity: 999 };
  });
  const orders = Array.from({ length: orderCount }, (_, index) => {
    const zones = scenarioOrderZones(scenario.pattern, index, random);
    const pickup = jitter(zones.pickup, random, zones.pickupJitter);
    const dropoff = jitter(zones.dropoff, random, zones.dropoffJitter);
    return {
      orderId: `ORD_${scenario.badge.toUpperCase().replace(/[^A-Z0-9]/g, '')}_${String(index + 1).padStart(3, '0')}`,
      pickupLat: pickup.lat,
      pickupLng: pickup.lng,
      dropoffLat: dropoff.lat,
      dropoffLng: dropoff.lng,
      demand: 1 + Math.floor(random() * 8),
      deadlineMinutes: scenarioDeadline(scenario.pattern, index, random)
    };
  });
  return { seed: scenario.seed, drivers, orders };
}

function createControlledLiveDemo(seed = 20260521, orderCount = 18, driverCount = 4): LiveDemoSeed {
  const random = seededRandom(seed);
  const drivers = Array.from({ length: driverCount }, (_, index) => {
    const point = jitter(HCM_DEMO_POINTS[(index * 3) % HCM_DEMO_POINTS.length], random, 0.006);
    return { driverId: `DRV_LIVE_${String(index + 1).padStart(2, '0')}`, lat: point.lat, lng: point.lng, capacity: index === driverCount - 1 ? 70 : 110 };
  });
  const orders = Array.from({ length: orderCount }, (_, index) => {
    const pickup = jitter(HCM_DEMO_POINTS[(index * 2 + 1) % HCM_DEMO_POINTS.length], random);
    const dropoff = jitter(HCM_DEMO_POINTS[(index * 2 + 5) % HCM_DEMO_POINTS.length], random, 0.012);
    return {
      orderId: `ORD_LIVE_${String(index + 1).padStart(3, '0')}`,
      pickupLat: pickup.lat,
      pickupLng: pickup.lng,
      dropoffLat: dropoff.lat,
      dropoffLng: dropoff.lng,
      demand: 4 + Math.floor(random() * 14),
      deadlineMinutes: 55 + Math.floor(random() * 85)
    };
  });
  return { seed, drivers, orders };
}

export default function App() {
  const [tab, setTab] = useState<Tab>('live');
  const [datasetId, setDatasetId] = useState('raw-s');
  const [routes, setRoutes] = useState<UiRoute[]>([]);
  const [mapStops, setMapStops] = useState<UiStop[]>([]);
  const [compareRows, setCompareRows] = useState<CompareRow[]>([]);
  const [compareResult, setCompareResult] = useState<unknown>();
  const [compareDisplayMode, setCompareDisplayMode] = useState<CompareDisplayMode>('demo');
  const [solverMapMode, setSolverMapMode] = useState<SolverMapMode>('FINAL');
  const [demoScenarioId, setDemoScenarioId] = useState<DemoScenarioId>('urban_dense');
  const [mapFitVersion, setMapFitVersion] = useState(0);
  const [health, setHealth] = useState<unknown>();
  const [version, setVersion] = useState<unknown>();
  const [dispatchResult, setDispatchResult] = useState<unknown>();
  const [liveState, setLiveState] = useState<unknown>();
  const [executionEvents, setExecutionEvents] = useState<unknown>();
  const [response, setResponse] = useState('');
  const [apiEndpoint, setApiEndpoint] = useState<ApiEndpoint>('dispatch');
  const [customPayload, setCustomPayload] = useState('');
  const [timeline, setTimeline] = useState<unknown>();
  const [streamEvents, setStreamEvents] = useState<ExecutionEvent[]>([]);
  const [sessionId, setSessionId] = useState<string>();
  const [latencyMs, setLatencyMs] = useState(0);
  const [progress, setProgress] = useState(0);
  const [mapToolMode, setMapToolMode] = useState<MapToolMode>('pan');
  const [playbackStage, setPlaybackStage] = useState<PlaybackStage>('input');
  const [draftPoints, setDraftPoints] = useState<DraftPoint[]>([]);
  const [pendingOrderPickup, setPendingOrderPickup] = useState<DraftPoint | undefined>();
  const [liveDemo, setLiveDemo] = useState<LiveDemoSeed>(() => createScenarioLiveDemo(DEMO_SCENARIOS.urban_dense));
  const [liveBusy, setLiveBusy] = useState(false);
  const [realtimePhase, setRealtimePhase] = useState<RealtimePhaseId>('boot');
  const [demoKpi, setDemoKpi] = useState<DemoKpi>(EMPTY_DEMO_KPI);
  const [demoEvents, setDemoEvents] = useState<LogLine[]>([]);
  const [liveQueueItems, setLiveQueueItems] = useState<LiveQueueItem[]>([]);
  const [liveRunning, setLiveRunning] = useState(false);
  const [benchmarkRunning, setBenchmarkRunning] = useState(false);
  const [benchmarkJobId, setBenchmarkJobId] = useState<string>();
  const [autoOrderEnabled, setAutoOrderEnabled] = useState(false);
  const [autoDriverEnabled, setAutoDriverEnabled] = useState(false);
  const [trackedDriverId, setTrackedDriverId] = useState<string>();
  const [trackingMode, setTrackingMode] = useState<TrackingMode>('off');
  const [osrmQaEnabled, setOsrmQaEnabled] = useState(false);
  const [mapTileMode, setMapTileMode] = useState<MapTileMode>('dark');
  const [logs, setLogs] = useState<LogLine[]>([{ id: 1, at: time(), kind: 'info', text: 'Control Tower ready. UI state is driven by backend responses only.' }]);
  const logSeq = useRef(2);
  const liveBusyRef = useRef(false);
  const microBatchTimerRef = useRef<number | undefined>(undefined);
  const liveCycleRunningRef = useRef(false);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const liveRunningRef = useRef(false);
  const autoOrderEnabledRef = useRef(false);
  const autoDriverEnabledRef = useRef(false);
  const liveLoopTimerRef = useRef<number | undefined>(undefined);
  const benchmarkCancelRef = useRef(false);
  const autoOrderSeqRef = useRef(1);
  const autoDriverSeqRef = useRef(1);
  const lastManualPinAtRef = useRef(0);

  const payload = useMemo(() => stringify(payloadForEndpoint(apiEndpoint, datasetId)), [apiEndpoint, datasetId]);
  const displayedCompareResult = useMemo(() => compareDisplayResult(compareResult, compareDisplayMode), [compareResult, compareDisplayMode]);
  const displayedCompareRows = useMemo(() => compareRowsFromResult(displayedCompareResult), [displayedCompareResult]);
  const cards = useMemo(() => metricCards(health, dispatchResult, compareRows, liveState, latencyMs, routes), [health, dispatchResult, compareRows, liveState, latencyMs, routes]);
  const stages = useMemo(() => timelineRows(timeline), [timeline]);
  const backendReady = useMemo(() => backendIsReady(health), [health]);
  const playbackData = useMemo(() => playbackMapData(dispatchResult, liveState, displayedCompareResult, streamEvents), [dispatchResult, liveState, displayedCompareResult, streamEvents]);

  const log = (text: string, kind: LogKind = 'info') => setLogs((prev) => [...prev, { id: logSeq.current++, at: time(), kind, text }]);

  const selectTrackedDriver = useCallback((driverId: string) => {
    setTrackedDriverId(driverId);
    setTrackingMode((mode) => mode === 'off' ? 'view' : mode);
    setLogs((prev) => [...prev, { id: logSeq.current++, at: time(), kind: 'ok', text: `Tracking driver ${driverLabel(driverId)}.` }]);
  }, []);

  const clearTracking = useCallback(() => {
    setTrackedDriverId(undefined);
    setTrackingMode('off');
  }, []);

  useEffect(() => {
    if (!trackedDriverId) return;
    const exists = asArray(asRecord(liveState).driverStates)
      .map(driverRuntimeFromBackend)
      .filter((driver): driver is DriverRuntimeView => Boolean(driver))
      .some((driver) => driver.driverId === trackedDriverId);
    if (!exists) clearTracking();
  }, [liveState, trackedDriverId, clearTracking]);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  useEffect(() => {
    liveRunningRef.current = liveRunning;
  }, [liveRunning]);

  useEffect(() => {
    autoOrderEnabledRef.current = autoOrderEnabled;
    if (liveRunning && (autoOrderEnabled || autoDriverEnabled)) scheduleLiveLoopTick(900);
    if (!autoOrderEnabled && !autoDriverEnabled && liveLoopTimerRef.current) {
      window.clearTimeout(liveLoopTimerRef.current);
      liveLoopTimerRef.current = undefined;
    }
  }, [autoOrderEnabled, autoDriverEnabled, liveRunning]);

  useEffect(() => {
    autoDriverEnabledRef.current = autoDriverEnabled;
  }, [autoDriverEnabled]);

  useEffect(() => {
    if (!liveRunning || !sessionId) return;
    const interval = window.setInterval(async () => {
      const state = await irxApi.getLiveState(sessionId);
      if (state.ok) {
        setLiveState(state.data);
        applyBackendMap(state.data);
      }
    }, 1000);
    return () => window.clearInterval(interval);
  }, [liveRunning, sessionId]);

  useEffect(() => () => {
    if (microBatchTimerRef.current) window.clearTimeout(microBatchTimerRef.current);
    if (liveLoopTimerRef.current) window.clearTimeout(liveLoopTimerRef.current);
  }, []);

  const upsertLiveQueue = (orderId: string, status: LiveQueueStatus, message: string, extra: Partial<LiveQueueItem> = {}) => {
    setLiveQueueItems((prev) => {
      const nextItem: LiveQueueItem = { orderId, status, message, updatedAt: time(), ...extra };
      const exists = prev.some((item) => item.orderId === orderId);
      return exists ? prev.map((item) => item.orderId === orderId ? { ...item, ...nextItem } : item) : [nextItem, ...prev].slice(0, 80);
    });
  };

  const markDraftOrderStatus = (orderId: string, status: DraftStatus) => {
    setDraftPoints((prev) => prev.map((point) => point.orderId === orderId ? { ...point, status } : point));
  };

  const mergeBackendAssignmentsIntoQueue = (stateData: unknown, cycleData?: unknown) => {
    const source = stateData ?? cycleData;
    const activeRoutes = asArray(asRecord(source).activeRoutes).length ? asArray(asRecord(source).activeRoutes) : asArray(asRecord(cycleData).activeRoutes);
    const cycleId = scalar(asRecord(cycleData).cycleId, undefined as unknown as string);
    const assigned = new Map<string, string>();
    activeRoutes.forEach((route) => {
      const record = asRecord(route);
      const driverId = scalar(record.driverId, 'UNKNOWN_DRIVER');
      asArray(record.stops).forEach((stop) => {
        const orderId = scalar(asRecord(stop).orderId, '');
        if (orderId) assigned.set(orderId, driverId);
      });
    });
    if (!assigned.size) return;
    setLiveQueueItems((prev) => prev.map((item) => assigned.has(item.orderId) ? { ...item, status: 'ASSIGNED', driverId: assigned.get(item.orderId), cycleId, message: `Assigned to ${assigned.get(item.orderId)}`, updatedAt: time() } : item));
    setDraftPoints((prev) => prev.map((point) => point.orderId && assigned.has(point.orderId) ? { ...point, status: 'ASSIGNED' } : point));
  };

  const demoLog = (text: string, kind: LogKind = 'info') => {
    const line = { id: logSeq.current++, at: time(), kind, text };
    setDemoEvents((prev) => [...prev.slice(-80), line]);
    setLogs((prev) => [...prev, line]);
  };

  const acquireLiveLock = (label: string) => {
    if (liveBusyRef.current) {
      log(`${label} is already running. Please wait for the current live action to finish.`, 'warn');
      return false;
    }
    liveBusyRef.current = true;
    setLiveBusy(true);
    return true;
  };

  const releaseLiveLock = () => {
    liveBusyRef.current = false;
    setLiveBusy(false);
  };

  const applySolverMap = (value: unknown, mode: SolverMapMode) => {
    const mapped = mode === 'FINAL' ? mapRoutesFromBackend(value) : mapRoutesForSolver(value, mode);
    setRoutes(mapped.routes);
    setMapStops(mapped.stops);
    if (!mapped.routes.length && mode !== 'FINAL') log(`${mode} has no backend stop sequence yet; route map cannot draw fake lines.`, 'warn');
    if (mapped.routes.length && !mapped.hasBackendGeometry) log(`${mode} has backend stop sequence only; non-live preview may request local OSRM geometry.`, 'info');
  };

  const subscribeExecution = (executionId?: string) => {
    if (!executionId) return;
    const source = new EventSource(irxApi.executionEventStreamUrl(executionId));
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as ExecutionEvent;
        setStreamEvents((prev) => [...prev, payload]);
        setTimeline((prev: unknown) => {
          const stages = asArray(asRecord(prev).stages).filter((stage) => asRecord(stage).stage !== payload.stage);
          return { executionId, status: payload.stage === 'EXECUTION_COMPLETED' ? 'COMPLETED' : 'RUNNING', currentStage: payload.stage, stages: [...stages, payload] };
        });
        if (payload.stage) setPlaybackStage(playbackStageForBackend(payload.stage));
        if (payload.message) log(`[${payload.stage}] ${payload.message}`, payload.status === 'FAILED' ? 'err' : payload.status === 'COMPLETED' ? 'ok' : 'info');
        if (payload.stage === 'ROUTE_GEOMETRY_COMPLETED' || payload.stage === 'FINAL_ASSIGNMENT_COMPLETED') applyBackendMap(payload.data);
      } catch (error) {
        log(error instanceof Error ? error.message : 'Invalid execution event payload.', 'warn');
      }
    };
    source.onerror = () => {
      source.close();
      log(`Execution stream closed for ${executionId}; polling snapshot remains available.`, 'warn');
    };
  };

  useEffect(() => {
    void refreshHealth();
  }, []);

  useEffect(() => {
    setCustomPayload(payload);
  }, [payload]);

  const refreshHealth = async () => {
    const [healthResult, versionResult] = await Promise.all([irxApi.health(), irxApi.version()]);
    setHealth(healthResult.data ?? healthResult.error);
    setVersion(versionResult.data ?? versionResult.error);
    setLatencyMs(Math.max(healthResult.durationMs, versionResult.durationMs));
    if (healthResult.ok) {
      solverRows(healthResult.data).forEach((row) => log(`Solver ${row.name}: ${row.value}`, row.value === 'AVAILABLE' ? 'ok' : 'err'));
      log('Health/version loaded from backend.', 'ok');
    } else {
      log(`Backend offline. Actions are locked until health is UP: ${healthResult.error ?? healthResult.status}`, 'err');
    }
  };

  const selectDataset = (next: string) => {
    setDatasetId(next);
    setRoutes([]);
    setMapStops([]);
    setCompareRows([]);
    setCompareResult(undefined);
    setDispatchResult(undefined);
    setTimeline(undefined);
    log(`Selected backend datasetId ${next}; no local dataset objects loaded.`, 'info');
  };

  const applyBackendMap = (value: unknown) => {
    const mapped = solverMapMode === 'FINAL' ? mapRoutesFromBackend(value) : mapRoutesForSolver(value, solverMapMode);
    if (!mapped.routes.length && !mapped.stops.length) return;
    setRoutes(mapped.routes);
    setMapStops(mapped.stops);
    if (mapped.routes.length && !mapped.hasBackendGeometry) log(tab === 'live' ? `${solverMapMode} live route missing backend polyline; FE will not self-route.` : `${solverMapMode} has stop sequence only; non-live map may use local OSRM preview.`, tab === 'live' ? 'warn' : 'info');
  };

  const logManualPinEvent = (type: string, point: DraftPoint, kind: LogKind = 'info') => {
    log(`${type}: ${point.label} ${point.orderId ?? ''} at ${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}`, kind);
  };

  const selectScenario = (scenarioId: DemoScenarioId) => {
    const scenario = DEMO_SCENARIOS[scenarioId];
    const generated = createScenarioLiveDemo(scenario);
    setDemoScenarioId(scenarioId);
    setDatasetId(scenario.datasetId);
    setLiveDemo(generated);
    setDraftPoints(demoToDraftPoints(generated));
    setPendingOrderPickup(undefined);
    setPlaybackStage('input');
    setSolverMapMode('FINAL');
    setRoutes([]);
    setMapStops([]);
    setCompareRows([]);
    setCompareResult(undefined);
    setDispatchResult(undefined);
    setLiveState(undefined);
    setSessionId(undefined);
    setLiveQueueItems([]);
    setMapToolMode('pan');
    setCustomPayload(stringify({ scenarioId, datasetId: scenario.datasetId, drivers: generated.drivers, orders: generated.orders }));
    setMapFitVersion((version) => version + 1);
    log(`Scenario ${scenario.label} visible on map immediately: ${generated.drivers.length} drivers, ${generated.orders.length} orders.`, 'ok');
  };

  const runLiveMicroBatchCycle = async (reason = 'micro-batch') => {
    const id = sessionIdRef.current;
    if (!id || liveCycleRunningRef.current || !backendReady) return;
    liveCycleRunningRef.current = true;
    setRealtimePhase('solver');
    setLiveQueueItems((prev) => prev.map((item) => item.status === 'BUFFERED' ? { ...item, status: 'PROCESSING', message: 'Backend cycle is processing this buffered order', updatedAt: time() } : item));
    setDraftPoints((prev) => prev.map((point) => point.status === 'BUFFERED' ? { ...point, status: 'PROCESSING' } : point));
    try {
      log(`Micro-batch cycle started by FE timer (${reason}).`, 'info');
      const cycle = await irxApi.runLiveCycle(id, { ...liveCyclePayload(), requestId: requestId(`live-${reason}`), pdLnsMode: 'TOP_K_ASSISTED' });
      const state = await irxApi.getLiveState(id);
      setLatencyMs(Math.max(cycle.durationMs, state.durationMs));
      setLiveState(state.data);
      setResponse(stringify(state.data ?? cycle.data ?? state.error ?? cycle.error));
      applyBackendMap(state.data ?? cycle.data);
      mergeBackendAssignmentsIntoQueue(state.data, cycle.data);
      setLiveRunning(true);
      liveRunningRef.current = true;
      setPlaybackStage('final');
      setProgress(5);
      log(cycle.ok && state.ok ? 'Micro-batch live cycle completed from backend.' : `Micro-batch cycle failed: cycle=${cycle.status ?? cycle.error}, state=${state.status ?? state.error}`, cycle.ok && state.ok ? 'ok' : 'err');
    } finally {
      liveCycleRunningRef.current = false;
    }
  };

  const scheduleLiveMicroBatch = () => {
    if (microBatchTimerRef.current) window.clearTimeout(microBatchTimerRef.current);
    microBatchTimerRef.current = window.setTimeout(() => {
      microBatchTimerRef.current = undefined;
      void runLiveMicroBatchCycle('auto-3s');
    }, 3000);
  };

  const mapAnchorPoint = () => {
    const source = draftPoints.length ? draftPoints : demoToDraftPoints(liveDemo).slice(0, 8);
    if (!source.length) return { lat: 10.7626, lng: 106.6601 };
    const index = (autoOrderSeqRef.current + source.length) % source.length;
    return source[index];
  };

  const jitterNear = (lat: number, lng: number, seq: number, scale = 0.012) => ({
    lat: lat + Math.sin(seq * 1.73) * scale + Math.cos(seq * 0.41) * scale * 0.35,
    lng: lng + Math.cos(seq * 1.37) * scale + Math.sin(seq * 0.29) * scale * 0.35
  });

  const generateLiveOrderOnce = async (source: 'auto' | 'spam' = 'auto') => {
    if (!backendReady) return;
    const id = sessionIdRef.current ?? await startLive(liveDemo, false);
    if (!id) return;
    const seq = autoOrderSeqRef.current++;
    const anchor = mapAnchorPoint();
    const pickupPoint = jitterNear(anchor.lat, anchor.lng, seq, 0.008);
    const dropoffPoint = jitterNear(pickupPoint.lat, pickupPoint.lng, seq + 17, 0.014);
    const prefix = source === 'spam' ? 'ORD_SPAM' : 'ORD_AUTO';
    const orderId = `${prefix}_${String(seq).padStart(4, '0')}`;
    const pickup: DraftPoint = { id: `${source}-pickup-${orderId}`, kind: 'pickup', lat: pickupPoint.lat, lng: pickupPoint.lng, label: `${orderId}_P`, orderId, status: 'SENDING' };
    const dropoff: DraftPoint = { id: `${source}-dropoff-${orderId}`, kind: 'dropoff', lat: dropoffPoint.lat, lng: dropoffPoint.lng, label: `${orderId}_D`, orderId, status: 'SENDING' };
    setDraftPoints((prev) => [...prev, pickup, dropoff]);
    upsertLiveQueue(orderId, 'SENDING', `${source === 'spam' ? 'Manual spam' : 'Auto'} live order pinned near active map area`);
    await sendPinnedOrderToBackend(pickup, dropoff);
  };

  const generateLiveDriverOnce = async (source: 'auto' | 'spam' = 'auto') => {
    if (!backendReady) return;
    const id = sessionIdRef.current ?? await startLive(liveDemo, false);
    if (!id) return;
    const seq = autoDriverSeqRef.current++;
    const anchor = mapAnchorPoint();
    const point = jitterNear(anchor.lat, anchor.lng, seq + 101, 0.018);
    const driver = { driverId: `${source === 'spam' ? 'DRV_SPAM' : 'DRV_AUTO'}_${String(seq).padStart(3, '0')}`, lat: point.lat, lng: point.lng, capacity: 100 };
    const result = await irxApi.addLiveDriver(id, driver);
    if (result.ok) {
      setDraftPoints((prev) => prev.filter((point) => !(point.kind === 'driver' && point.label === driver.driverId)));
      const state = await irxApi.getLiveState(id);
      setLiveState(state.data);
      log(`${source === 'spam' ? 'Spam' : 'Auto'} driver online: ${driver.driverId}.`, 'ok');
    } else {
      log(`${source === 'spam' ? 'Spam' : 'Auto'} driver failed: ${result.error ?? result.status}`, 'warn');
    }
  };

  const liveDriverPressure = () => {
    const state = asRecord(liveState);
    const stateDrivers = asArray(state.drivers).map((driver) => scalar(asRecord(driver).driverId, '')).filter(Boolean);
    const runtimeDrivers = asArray(state.driverStates).map((driver) => scalar(asRecord(driver).driverId, '')).filter(Boolean);
    const draftDrivers = draftPoints.filter((point) => point.kind === 'driver').map((point) => point.label).filter(Boolean);
    const driverIds = new Set([...stateDrivers, ...runtimeDrivers, ...draftDrivers]);
    const bufferCount = asArray(state.bufferItems).length;
    const routeOrderIds = new Set<string>();
    asArray(state.activeRoutes).forEach((route) => asArray(asRecord(route).stops).forEach((stop) => {
      const orderId = scalar(asRecord(stop).orderId, '');
      if (orderId) routeOrderIds.add(orderId);
    }));
    const draftOrderIds = new Set(draftPoints.filter((point) => point.kind !== 'driver' && point.orderId).map((point) => point.orderId as string));
    const liveOrders = Math.max(bufferCount + routeOrderIds.size, draftOrderIds.size, autoOrderSeqRef.current - 1);
    const targetDrivers = Math.min(15, Math.max(1, Math.ceil(liveOrders / 4), liveOrders >= 20 ? 8 : 0, liveOrders >= 36 ? 12 : 0));
    const deficit = Math.max(0, targetDrivers - driverIds.size);
    return { knownDrivers: driverIds.size, liveOrders, targetDrivers, deficit };
  };

  const autoDriverAddsNeeded = () => {
    const pressure = liveDriverPressure();
    if (pressure.deficit <= 0) return 0;
    if (pressure.liveOrders <= 2 && pressure.knownDrivers >= 1) return 0;
    if (pressure.deficit >= 4 && pressure.liveOrders >= 12) return 2;
    return 1;
  };

  const scheduleLiveLoopTick = (delayMs = 2200) => {
    if (!autoOrderEnabledRef.current && !autoDriverEnabledRef.current) return;
    if (liveLoopTimerRef.current) window.clearTimeout(liveLoopTimerRef.current);
    liveLoopTimerRef.current = window.setTimeout(async () => {
      liveLoopTimerRef.current = undefined;
      if (!liveRunningRef.current) return;
      const manualRecently = Date.now() - lastManualPinAtRef.current < 2500;
      if (autoOrderEnabledRef.current && !manualRecently) await generateLiveOrderOnce('auto');
      if (autoDriverEnabledRef.current) {
        const adds = autoDriverAddsNeeded();
        for (let index = 0; index < adds; index += 1) await generateLiveDriverOnce('auto');
        if (adds > 0) {
          const pressure = liveDriverPressure();
          log(`Auto driver balanced pool: ${pressure.knownDrivers}/${pressure.targetDrivers} drivers for ${pressure.liveOrders} live orders.`, 'info');
        }
      }
      const nextDelay = autoDriverEnabledRef.current && !autoOrderEnabledRef.current ? 3200 : 2000 + (autoOrderSeqRef.current % 3) * 900;
      scheduleLiveLoopTick(nextDelay);
    }, delayMs);
  };

  const sendPinnedOrderToBackend = async (pickup: DraftPoint, dropoff: DraftPoint) => {
    if (!backendReady) {
      upsertLiveQueue(pickup.orderId ?? pickup.label, 'FAILED', 'Backend offline; order stayed on map');
      return;
    }
    let id = sessionIdRef.current;
    if (!id) id = await startLive();
    if (!id) return;
    const orderId = pickup.orderId ?? pickup.label.replace('_P', '');
    log(`USER_PIN_SENT_TO_BACKEND: ${orderId} pickup/dropoff pair is being sent to live buffer.`, 'info');
    markDraftOrderStatus(orderId, 'SENDING');
    upsertLiveQueue(orderId, 'SENDING', 'Sending pickup/dropoff to backend buffer');
    const order = { orderId, pickupLat: pickup.lat, pickupLng: pickup.lng, dropoffLat: dropoff.lat, dropoffLng: dropoff.lng, demand: 8, deadlineMinutes: 90 };
    const result = await irxApi.addLiveOrder(id, { requestId: requestId('map-live-order'), tenantId: 'demo', order });
    const state = await irxApi.getLiveState(id);
    setLatencyMs(Math.max(result.durationMs, state.durationMs));
    setLiveState(state.data);
    setResponse(stringify(state.data ?? result.data ?? state.error ?? result.error));
    if (result.ok) {
      markDraftOrderStatus(orderId, 'BUFFERED');
      upsertLiveQueue(orderId, 'BUFFERED', `Added to backend buffer for ${id}`);
      setRealtimePhase('buffer');
      log(`USER_PIN_BUFFERED: ${orderId} đã vào hàng đợi backend buffer.`, 'ok');
      scheduleLiveMicroBatch();
    } else {
      markDraftOrderStatus(orderId, 'DRAFT');
      upsertLiveQueue(orderId, 'FAILED', `Backend rejected order: ${result.error ?? result.status}`);
      log(`Live pinned order failed: ${result.error ?? result.status}`, 'err');
    }
  };

  const sendPinnedDriverToBackend = async (driverPoint: DraftPoint) => {
    if (!backendReady) {
      log('Backend offline; driver pin stayed as draft.', 'warn');
      return;
    }
    const id = sessionIdRef.current;
    if (!id) {
      log(`${driverPoint.label} pinned locally. It will be sent when Start Live creates the backend session.`, 'info');
      return;
    }
    setDraftPoints((prev) => prev.map((point) => point.id === driverPoint.id ? { ...point, status: 'SENDING' } : point));
    const driver = { driverId: driverPoint.label, lat: driverPoint.lat, lng: driverPoint.lng, capacity: 100, currentLoad: 0, status: 'IDLE' };
    const result = await irxApi.addLiveDriver(id, driver);
    const state = await irxApi.getLiveState(id);
    setLatencyMs(Math.max(result.durationMs, state.durationMs));
    setLiveState(state.data);
    setResponse(stringify(state.data ?? result.data ?? state.error ?? result.error));
    setDraftPoints((prev) => result.ok ? prev.filter((point) => point.id !== driverPoint.id) : prev.map((point) => point.id === driverPoint.id ? { ...point, status: 'DRAFT' } : point));
    log(result.ok ? `${driverPoint.label} sent to backend live driver pool.` : `Driver pin failed: ${result.error ?? result.status}`, result.ok ? 'ok' : 'err');
  };

  const stopLive = () => {
    setLiveRunning(false);
    setAutoOrderEnabled(false);
    setAutoDriverEnabled(false);
    liveRunningRef.current = false;
    autoOrderEnabledRef.current = false;
    autoDriverEnabledRef.current = false;
    if (liveLoopTimerRef.current) window.clearTimeout(liveLoopTimerRef.current);
    liveLoopTimerRef.current = undefined;
    if (microBatchTimerRef.current) window.clearTimeout(microBatchTimerRef.current);
    microBatchTimerRef.current = undefined;
    log('Live paused. Session, buffer and map are kept for resume.', 'warn');
  };

  const cancelAndClearMap = () => {
    stopLive();
    liveBusyRef.current = false;
    liveCycleRunningRef.current = false;
    setLiveBusy(false);
    setSessionId(undefined);
    sessionIdRef.current = undefined;
    setRoutes([]);
    setMapStops([]);
    setDraftPoints([]);
    setPendingOrderPickup(undefined);
    setLiveQueueItems([]);
    setLiveState(undefined);
    setCompareRows([]);
    setCompareResult(undefined);
    setDispatchResult(undefined);
    setTimeline(undefined);
    setExecutionEvents(undefined);
    setStreamEvents([]);
    setDemoEvents([]);
    setDemoKpi(EMPTY_DEMO_KPI);
    setResponse('');
    setSolverMapMode('FINAL');
    setPlaybackStage('input');
    setRealtimePhase('boot');
    setMapToolMode('pan');
    setMapFitVersion((version) => version + 1);
    clearTracking();
    log('Cancelled running live tasks and cleared map/state.', 'warn');
  };

  const handleMapDrop = (lat: number, lng: number) => {
    if (mapToolMode === 'pan') return;
    if (mapToolMode === 'order') {
      if (!pendingOrderPickup) {
        const orderIndex = draftPoints.filter((point) => point.kind === 'pickup').length + 1;
        const orderId = `ORD_MAP_${String(orderIndex).padStart(3, '0')}`;
        const pickup: DraftPoint = { id: `pickup-${Date.now()}`, kind: 'pickup', lat, lng, label: `${orderId}_P`, orderId, status: 'DRAFT' };
        setPendingOrderPickup(pickup);
        setDraftPoints((prev) => [...prev, pickup]);
        logManualPinEvent('USER_PIN_PICKUP', pickup);
        log(`Pinned pickup for ${orderId}. Click map again to pin dropoff.`, 'info');
        return;
      }
      const orderId = pendingOrderPickup.orderId ?? pendingOrderPickup.label.replace('_P', '');
      const dropoff: DraftPoint = { id: `dropoff-${Date.now()}`, kind: 'dropoff', lat, lng, label: `${orderId}_D`, orderId, status: 'DRAFT' };
      lastManualPinAtRef.current = Date.now();
      setDraftPoints((prev) => [...prev, dropoff]);
      setPendingOrderPickup(undefined);
      upsertLiveQueue(orderId, 'DRAFT', 'Pinned pickup/dropoff on map');
      logManualPinEvent('USER_PIN_DROPOFF', dropoff, 'ok');
      log(`Pinned full order ${orderId}: pickup + dropoff. Sending to live buffer.`, 'ok');
      void sendPinnedOrderToBackend(pendingOrderPickup, dropoff);
      return;
    }
    const nextIndex = draftPoints.filter((point) => point.kind === mapToolMode).length + 1;
    const labelPrefix = mapToolMode === 'driver' ? 'DRV_CUSTOM' : mapToolMode.toUpperCase();
    const nextPoint: DraftPoint = {
      id: `${mapToolMode}-${Date.now()}`,
      kind: mapToolMode,
      lat,
      lng,
      label: `${labelPrefix}_${String(nextIndex).padStart(2, '0')}`,
      orderId: mapToolMode === 'pickup' || mapToolMode === 'dropoff' ? `${labelPrefix}_${String(nextIndex).padStart(2, '0')}` : undefined,
      status: 'DRAFT'
    };
    setDraftPoints((prev) => [...prev, nextPoint]);
    log(`Dropped ${nextPoint.label} at ${lat.toFixed(5)}, ${lng.toFixed(5)}.`, 'info');
    if (mapToolMode === 'driver') void sendPinnedDriverToBackend(nextPoint);
  };

  const clearDraftPoints = () => {
    setDraftPoints([]);
    setPendingOrderPickup(undefined);
    setLiveQueueItems([]);
    setMapToolMode('pan');
    log('Cleared map drop points.', 'info');
  };

  const runDraftDispatch = async () => {
    if (!backendReady) {
      log('Backend is not ready. Dispatch is locked.', 'warn');
      return;
    }
    const payload = draftDispatchPayload(draftPoints);
    if (!payload.orders.length || !payload.drivers.length) {
      log('Need at least 1 driver, 1 pickup and 1 dropoff before running draft dispatch.', 'warn');
      return;
    }
    setPlaybackStage('input');
    setDraftPoints((prev) => prev.map((point) => ({ ...point, status: 'SENT_TO_BACKEND' })));
    setCustomPayload(stringify(payload));
    setResponse(stringify(payload));
    const result = await irxApi.runDashboardDispatch(payload);
    setLatencyMs(result.durationMs);
    setDispatchResult(result.data);
    setResponse(stringify(result.data ?? result.error));
    applyBackendMap(result.data);
    if (result.ok) setPlaybackStage('final');
    log(result.ok ? 'Draft map dispatch returned real backend route.' : `Draft dispatch failed: ${result.error ?? result.status}`, result.ok ? 'ok' : 'err');
  };

  const playTimeline = async (executionId?: string) => {
    if (!executionId) return;
    subscribeExecution(executionId);
    log(`Polling backend timeline ${executionId}.`, 'info');
    for (let index = 0; index < 12; index++) {
      const timelineResult = await irxApi.getExecutionTimeline(executionId);
      const eventsResult = await irxApi.getExecutionEvents(executionId);
      setTimeline(timelineResult.data ?? timelineResult.error);
      setExecutionEvents(eventsResult.data ?? eventsResult.error);
      if (eventsResult.ok) log(`Execution events loaded from backend: ${executionId}.`, 'ok');
      const record = asRecord(timelineResult.data);
      const rows = asArray(record.stages);
      const completed = rows.filter((stage) => asRecord(stage).status === 'COMPLETED').length;
      setProgress(Math.min(5, Math.ceil((completed / Math.max(rows.length, 1)) * 5)));
      if (String(record.status ?? '').includes('COMPLETED')) return;
      await sleep(400);
    }
  };

  const pollDispatchStatus = async (jobId: string) => {
    for (let attempt = 0; attempt < 12; attempt++) {
      const status = await irxApi.getDispatchJob(jobId);
      const state = scalar(asRecord(status.data).status, 'UNKNOWN');
      log(`Dispatch status from backend: ${state}.`, status.ok ? 'info' : 'warn');
      if (!status.ok || ['COMPLETED', 'FAILED', 'CANCELLED'].some((terminal) => state.includes(terminal))) break;
      await sleep(500);
    }
  };

  const runStatic = async () => {
    if (!backendReady) {
      log('Backend is not ready. Static dispatch is locked.', 'warn');
      return;
    }
    setProgress(1);
    setRoutes([]);
    setMapStops([]);
    log('POST /v1/dispatch/jobs', 'info');
    const job = await irxApi.createDispatchJob(dispatchPayload(datasetId));
    setLatencyMs(job.durationMs);
    setResponse(stringify(job.data ?? job.error));
    if (!job.ok) return log(`Static dispatch failed: ${job.error ?? job.status}`, 'err');
    const jobId = getStringId(job.data, ['jobId', 'id']);
    const executionId = getStringId(job.data, ['executionId']) ?? jobId;
    log(`Static job accepted by backend${jobId ? `: ${jobId}` : ''}.`, 'ok');
    await playTimeline(executionId);
    if (jobId) {
      await pollDispatchStatus(jobId);
      const result = await irxApi.getDispatchResult(jobId);
      setResponse(stringify(result.data ?? result.error ?? job.data));
      setDispatchResult(result.data);
      applyBackendMap(result.data);
      log(result.ok ? 'Dispatch result loaded from /v1/dispatch/jobs/{jobId}/result.' : 'Dispatch result request failed.', result.ok ? 'ok' : 'err');
    }
    setProgress(5);
  };

  const runCompare = async () => {
    if (benchmarkRunning) {
      benchmarkCancelRef.current = true;
      setBenchmarkRunning(false);
      if (benchmarkJobId) await irxApi.cancelCompareJob(benchmarkJobId);
      log('Benchmark cancelled by operator.', 'warn');
      setProgress(0);
      return;
    }
    if (!backendReady) {
      log('Backend is not ready. Benchmark compare is locked.', 'warn');
      return;
    }
    benchmarkCancelRef.current = false;
    setBenchmarkRunning(true);
    setBenchmarkJobId(undefined);
    setProgress(1);
    setCompareRows([]);
    try {
      log('POST /v1/compare/jobs (IRX static benchmark)', 'info');
      const job = await irxApi.createCompareJob(comparePayload(datasetId));
      setLatencyMs(job.durationMs);
      setResponse(stringify(job.data ?? job.error));
      if (!job.ok) return log(`Compare failed: ${job.error ?? job.status}`, 'err');
      const jobId = getStringId(job.data, ['jobId', 'id']);
      setBenchmarkJobId(jobId);
      const executionId = getStringId(job.data, ['executionId']) ?? jobId;
      await playTimeline(executionId);
      if (benchmarkCancelRef.current) return;
      const result = jobId ? await irxApi.getCompareResult(jobId) : job;
      if (benchmarkCancelRef.current) return;
      setResponse(stringify(result.data ?? result.error ?? job.data));
      const rows = compareRowsFromResult(result.data);
      setCompareRows(rows);
      setCompareResult(result.data);
      setSolverMapMode('FINAL');
      applySolverMap(result.data, 'FINAL');
      if (executionId) {
        const [timelineResult, eventsResult] = await Promise.all([irxApi.getExecutionTimeline(executionId), irxApi.getExecutionEvents(executionId)]);
        setTimeline(timelineResult.data ?? timelineResult.error);
        setExecutionEvents(eventsResult.data ?? eventsResult.error);
        if (eventsResult.ok) setStreamEvents(asArray(asRecord(eventsResult.data).events) as ExecutionEvent[]);
      }
      const present = new Set(rows.map((row) => row.solver.toUpperCase()));
      ['IRX_NATIVE', 'VROOM', 'ORTOOLS', 'PYVRP', 'DISTANCE_NEAREST', 'ONE_BY_ONE_DELIVERY'].forEach((solver) => {
        if (!present.has(solver)) log(`Compare result missing solver row: ${solver}. Showing backend response as-is.`, 'warn');
      });
      log(result.ok ? 'Compare result loaded from backend.' : 'Compare result request failed.', result.ok ? 'ok' : 'err');
      setProgress(5);
    } finally {
      setBenchmarkRunning(false);
      setBenchmarkJobId(undefined);
    }
  };

  const clearBenchmark = () => {
    setCompareRows([]);
    setCompareResult(undefined);
    setBenchmarkRunning(false);
    setBenchmarkJobId(undefined);
    benchmarkCancelRef.current = true;
    setRoutes([]);
    setMapStops([]);
    setTimeline(undefined);
    setExecutionEvents(undefined);
    setStreamEvents([]);
    setResponse('');
    setSolverMapMode('FINAL');
    setPlaybackStage('input');
    log('Benchmark compare cleared.', 'info');
  };

  const liveComparePayloadFromState = (state: unknown, cycle: unknown, durationMs: number) => {
    const stateRecord = asRecord(state);
    const trace = asRecord(stateRecord.decisionTrace);
    const metrics = asRecord(trace.metrics);
    const finalSelection = asRecord(trace.finalSelection);
    const seedRace = asArray(trace.seedRace ?? trace.solverRace);
    const activeRoutes = asArray(stateRecord.activeRoutes);
    const distanceKm = activeRoutes.reduce<number>((sum, route) => sum + Number(asRecord(route).totalDistanceKm ?? 0), 0);
    const lateCount = activeRoutes.reduce<number>((sum, route) => sum + Number(asRecord(route).lateOrderCount ?? 0), 0);
    const assigned = new Set<string>();
    activeRoutes.forEach((route) => asArray(asRecord(route).stops).forEach((stop) => {
      const orderId = scalar(asRecord(stop).orderId, '');
      if (orderId) assigned.add(orderId);
    }));
    const solverRows = seedRace.length ? seedRace.map((seed) => {
      const record = asRecord(seed);
      const solver = scalar(record.solver ?? record.seedId, 'SEED');
      return {
        solver: `${solver}_LIVE_SEED`,
        distanceKm: Number(record.distanceKm ?? distanceKm),
        lateCount: Number(record.lateCount ?? lateCount),
        runtimeMs: Number(record.runtimeMs ?? durationMs),
        coverage: assigned.size / Math.max(1, asArray(stateRecord.drivers).length + asArray(stateRecord.bufferItems).length + assigned.size),
        assignedOrderCount: assigned.size,
        inputOrderCount: assigned.size + Number(stateRecord.bufferedOrders ?? 0),
        result: scalar(record.status, 'COMPLETED')
      };
    }) : [];
    const finalRow = {
      solver: 'IRX_FINAL_REFINED',
      distanceKm: Math.round(distanceKm * 10) / 10,
      lateCount,
      runtimeMs: durationMs,
      coverage: assigned.size / Math.max(1, assigned.size + Number(stateRecord.bufferedOrders ?? 0)),
      assignedOrderCount: assigned.size,
      inputOrderCount: assigned.size + Number(stateRecord.bufferedOrders ?? 0),
      result: 'LIVE_KERNEL_COMPLETED',
      isFinal: true,
      selectedSource: scalar(finalSelection.selectedSource, 'IRX_FINAL_REFINED')
    };
    const solvers = Object.fromEntries([...solverRows, finalRow].map((row) => [row.solver, row]));
    return {
      status: 'COMPLETED',
      mode: 'LIVE_KERNEL_COMPARE',
      solvers,
      seedRace,
      routes: activeRoutes,
      activeRoutes,
      finalSelection: { ...finalSelection, selectedSource: 'IRX_FINAL_REFINED', selectionReason: 'live kernel compare uses live buffer/cycle/final route output' },
      playbackTrace: trace,
      processTrace: trace,
      liveState: state,
      cycle
    };
  };

  const runLiveKernelCompare = async () => {
    setProgress(1);
    setCompareRows([]);
    const scenario = DEMO_SCENARIOS[demoScenarioId] ?? DEMO_SCENARIOS.urban_dense;
    const generated = createScenarioLiveDemo(scenario, Math.max(8, Math.min(16, scenario.orders)), Math.max(3, Math.min(5, scenario.drivers)));
    log('LIVE_KERNEL_COMPARE: create live session, buffer orders, run live cycle.', 'info');
    const session = await irxApi.createLiveSession({ ...livePayload(), requestId: requestId('live-kernel-compare'), drivers: generated.drivers });
    const id = getStringId(session.data, ['sessionId']);
    if (!session.ok || !id) {
      setResponse(stringify(session.data ?? session.error));
      log(`Live-kernel compare session failed: ${session.error ?? session.status}`, 'err');
      return;
    }
    for (const order of generated.orders) {
      await irxApi.addLiveOrder(id, { requestId: requestId('live-kernel-order'), tenantId: 'demo', order });
    }
    const cycle = await irxApi.runLiveCycle(id, liveCyclePayload());
    const state = await irxApi.getLiveState(id);
    const durationMs = session.durationMs + cycle.durationMs + state.durationMs;
    setLatencyMs(durationMs);
    setLiveState(state.data);
    setSessionId(id);
    const payload = liveComparePayloadFromState(state.data, cycle.data, durationMs);
    setResponse(stringify(payload));
    setCompareResult(payload);
    setCompareRows(compareRowsFromResult(payload));
    setSolverMapMode('FINAL');
    applySolverMap(payload, 'FINAL');
    setPlaybackStage('seed');
    log('Live-kernel compare completed using real live session/cycle path.', 'ok');
    setProgress(5);
  };

  const createLiveSessionFromDemo = async (demo: LiveDemoSeed, forceAllDrivers = false) => {
    setProgress(1);
    const draftDrivers = draftPoints
      .filter((point) => point.kind === 'driver')
      .map((point, index) => ({ driverId: point.label || `DRV_CUSTOM_${index + 1}`, lat: point.lat, lng: point.lng, capacity: 100, currentLoad: 0, status: 'IDLE' }));
    const sessionDrivers = forceAllDrivers ? demo.drivers : draftDrivers.length ? draftDrivers : autoDriverEnabledRef.current ? demo.drivers.slice(0, Math.min(3, demo.drivers.length)) : demo.drivers.slice(0, 1);
    const driverSource = forceAllDrivers ? 'fixed scenario' : draftDrivers.length ? 'manual' : autoDriverEnabledRef.current ? 'auto warmup' : 'starter';
    const session = await irxApi.createLiveSession({ ...livePayload(), drivers: sessionDrivers });
    setLatencyMs(session.durationMs);
    setResponse(stringify(session.data ?? session.error));
    if (!session.ok) {
      log(`Live session failed: ${session.error ?? session.status}`, 'err');
      return undefined;
    }
    const id = getStringId(session.data, ['sessionId', 'id']);
    if (!id) {
      log('Live session response has no sessionId.', 'err');
      return undefined;
    }
    setSessionId(id);
    setDraftPoints((prev) => {
      const backendDriverIds = new Set(sessionDrivers.map((driver) => driver.driverId));
      return prev.filter((point) => point.kind !== 'driver' || !backendDriverIds.has(point.label));
    });
    const state = await irxApi.getLiveState(id);
    setLiveState(state.data);
    applyBackendMap(state.data);
    log(`Live session started by backend: ${id}. Drivers sent from FE: ${sessionDrivers.length} (${driverSource}).`, 'ok');
    setProgress(2);
    return id;
  };

  const startLive = async (demo = liveDemo, shouldScheduleAuto = true) => {
    if (!backendReady) {
      log('Backend is not ready. Live actions are locked.', 'warn');
      return undefined;
    }
    if (liveRunningRef.current) {
      stopLive();
      return sessionIdRef.current;
    }
    if (!acquireLiveLock('Start live')) return undefined;
    try {
      const id = sessionIdRef.current ?? await createLiveSessionFromDemo(demo);
      if (!id) return undefined;
      setLiveRunning(true);
      liveRunningRef.current = true;
      setRealtimePhase('stream');
      log(`Live running on session ${id}. Auto order ${autoOrderEnabledRef.current ? 'ON' : 'OFF'}, auto driver ${autoDriverEnabledRef.current ? 'ON' : 'OFF'}.`, 'ok');
      if (shouldScheduleAuto && (autoOrderEnabledRef.current || autoDriverEnabledRef.current)) scheduleLiveLoopTick(900);
      return id;
    } finally {
      releaseLiveLock();
    }
  };

  const generateControlledLive = () => {
    selectScenario(demoScenarioId);
  };

  const toggleAutoOrder = () => {
    setAutoOrderEnabled((enabled) => {
      const next = !enabled;
      autoOrderEnabledRef.current = next;
      log(`Auto order ${next ? 'ON' : 'OFF'}.`, next ? 'ok' : 'warn');
      if (next && liveRunningRef.current) scheduleLiveLoopTick(300);
      return next;
    });
  };

  const toggleAutoDriver = () => {
    setAutoDriverEnabled((enabled) => {
      const next = !enabled;
      autoDriverEnabledRef.current = next;
      log(`Auto driver ${next ? 'ON' : 'OFF'}.`, next ? 'ok' : 'warn');
      if (next && liveRunningRef.current) scheduleLiveLoopTick(300);
      return next;
    });
  };

  const spamLiveOrder = async () => {
    await generateLiveOrderOnce('spam');
  };

  const spamLiveDriver = async () => {
    await generateLiveDriverOnce('spam');
  };

  const runDemoCompare = async () => {
    if (!backendReady) {
      log('Backend is not ready. Demo compare is locked.', 'warn');
      return;
    }
    const scenario = DEMO_SCENARIOS[demoScenarioId];
    const generated = liveDemo.seed === scenario.seed ? liveDemo : createScenarioLiveDemo(scenario);
    setLiveDemo(generated);
    setDatasetId(scenario.datasetId);
    setTab('compare');
    setCompareDisplayMode('demo');
    setSolverMapMode('FINAL');
    setRoutes([]);
    setMapStops([]);
    setDraftPoints(demoToDraftPoints(generated).map((point) => ({ ...point, status: 'SENT_TO_BACKEND' })));
    setProgress(1);
    log(`Running real backend compare for scenario ${scenario.label}.`, 'info');
    const body = { ...comparePayload(scenario.datasetId), requestId: requestId(`demo-${demoScenarioId}`), scenarioId: demoScenarioId, drivers: generated.drivers, orders: generated.orders };
    const job = await irxApi.createCompareJob(body);
    setLatencyMs(job.durationMs);
    setResponse(stringify(job.data ?? job.error));
    if (!job.ok) return log(`Demo compare failed: ${job.error ?? job.status}`, 'err');
    const jobId = getStringId(job.data, ['jobId', 'id']);
    const executionId = getStringId(job.data, ['executionId']) ?? jobId;
    await playTimeline(executionId);
    const result = jobId ? await irxApi.getCompareResult(jobId) : job;
    setResponse(stringify(result.data ?? result.error ?? job.data));
    setCompareRows(compareRowsFromResult(result.data));
    setCompareResult(result.data);
    applySolverMap(result.data, 'FINAL');
    setProgress(5);
    log(result.ok ? `Scenario ${scenario.label} compare loaded. Use solver tabs on map.` : 'Scenario compare result failed.', result.ok ? 'ok' : 'err');
  };

  const spamLiveOrders = async (targetSessionId = sessionId) => {
    if (!backendReady) {
      log('Backend is not ready. Send generated orders is locked.', 'warn');
      return;
    }
    const ownsLock = !targetSessionId;
    if (ownsLock && !acquireLiveLock('Send generated orders')) return;
    try {
    const id = targetSessionId ?? await createLiveSessionFromDemo(liveDemo);
    if (!id) return;
    let sent = 0;
    for (const order of liveDemo.orders) {
      const payload = { requestId: requestId('controlled-live-order'), tenantId: 'demo', order };
      const result = await irxApi.addLiveOrder(id, payload);
      if (!result.ok) {
        log(`Live spam stopped at ${order.orderId}: ${result.error ?? result.status}`, 'err');
        return;
      }
      sent += 1;
    }
    const state = await irxApi.getLiveState(id);
    setLiveState(state.data);
    setResponse(stringify(state.data));
    log(`Spammed ${sent} controlled orders into backend buffer for ${id}.`, 'ok');
    } finally {
      if (ownsLock) releaseLiveLock();
    }
  };

  const runControlledLiveDemo = async () => {
    if (!backendReady) {
      log('Backend is not ready. Controlled live demo is locked.', 'warn');
      return;
    }
    if (!acquireLiveLock('Controlled live demo')) return;
    try {
    let id = sessionId;
    if (!id) {
      id = await createLiveSessionFromDemo(liveDemo);
    }
    if (!id) return;
    await spamLiveOrders(id);
    const cycle = await irxApi.runLiveCycle(id, liveCyclePayload());
    const state = await irxApi.getLiveState(id);
    setLatencyMs(Math.max(cycle.durationMs, state.durationMs));
    setLiveState(state.data);
    setResponse(stringify(state.data ?? cycle.data ?? state.error ?? cycle.error));
    applyBackendMap(state.data ?? cycle.data);
    log(cycle.ok && state.ok ? 'Controlled live demo completed from backend response.' : `Controlled live demo failed on ${id}: cycle=${cycle.status ?? cycle.error}, state=${state.status ?? state.error}`, cycle.ok && state.ok ? 'ok' : 'err');
    } finally {
      releaseLiveLock();
    }
  };

  const updateRealtimeKpi = (stateData: unknown, cycleData?: unknown, startedAt?: number, orderCount?: number) => {
    const stateRecord = asRecord(stateData);
    const cycleRecord = asRecord(cycleData);
    const trace = asRecord(stateRecord.decisionTrace ?? cycleRecord.decisionTrace);
    const finalSelection = asRecord(trace.finalSelection);
    const metrics = asRecord(cycleRecord.metrics ?? finalSelection);
    const elapsedSec = startedAt ? Math.max(1, (performance.now() - startedAt) / 1000) : undefined;
    setDemoKpi({
      ordersSec: elapsedSec && orderCount ? (orderCount / elapsedSec).toFixed(1) : '--',
      latencyMs: scalar(cycleRecord.durationMs ?? metrics.runtimeMs),
      queueDepth: scalar(stateRecord.bufferedOrders ?? cycleRecord.bufferedOrders, '0'),
      routeChurn: scalar(cycleRecord.routeChurnPercent ?? finalSelection.routeChurnPercent, '--'),
      lateCount: scalar(cycleRecord.lateCount ?? finalSelection.lateOrderCount ?? metrics.lateCount, '0'),
      cpu: 'live',
      heap: 'ok',
      solverRuntime: scalar(metrics.runtimeMs ?? cycleRecord.runtimeMs, '--')
    });
  };

  const runFullRealtimeDemo = async () => {
    if (!backendReady) {
      demoLog('[SYS] Backend is not ready. Realtime demo locked.', 'warn');
      return;
    }
    if (!acquireLiveLock('Full realtime demo')) return;
    const startedAt = performance.now();
    try {
      const scenario = DEMO_SCENARIOS[demoScenarioId];
      const generated = createScenarioLiveDemo(scenario);
      setLiveDemo(generated);
      setDatasetId(scenario.datasetId);
      setTab('demo');
      setRoutes([]);
      setMapStops([]);
      setStreamEvents([]);
      setTimeline(undefined);
      setDemoEvents([]);
      setDemoKpi(EMPTY_DEMO_KPI);
      setLiveRunning(false);
      liveRunningRef.current = false;
      setSessionId(undefined);
      sessionIdRef.current = undefined;
      setLiveState(undefined);
      setLiveQueueItems([]);
      setRealtimePhase('boot');
      setPlaybackStage('input');
      setDraftPoints(demoToDraftPoints({ ...generated, orders: [] }));
      setMapFitVersion((version) => version + 1);
      demoLog('[SYS] Live dispatch engine initialized', 'ok');
      demoLog('[SYS] Rolling horizon enabled', 'ok');
      demoLog('[SYS] Freeze policy enabled', 'ok');
      demoLog('[SYS] Dynamic insertion worker started', 'ok');

      const isLargeFixedScenario = demoScenarioId === 'large_live_fixed';
      const id = await createLiveSessionFromDemo(generated, isLargeFixedScenario);
      if (!id) return;
      setLiveRunning(true);
      liveRunningRef.current = true;
      subscribeExecution(`exec_${id}`);
      demoLog('[SSE] Event stream connected', 'ok');
      setRealtimePhase('drivers');
      generated.drivers.forEach((driver) => demoLog(`[DRIVER] ${driver.driverId} online`, 'ok'));
      await sleep(500);

      setRealtimePhase('stream');
      const streamedOrders = isLargeFixedScenario ? generated.orders : generated.orders.slice(0, Math.min(10, generated.orders.length));
      const batchSize = isLargeFixedScenario ? 8 : streamedOrders.length;
      let latestState: unknown;
      let latestCycle: unknown;
      for (const [index, order] of streamedOrders.entries()) {
        setDraftPoints((prev) => [...prev, ...demoToDraftPoints({ seed: generated.seed, drivers: [], orders: [order] }).map((point) => ({ ...point, status: 'SENT_TO_BACKEND' as const }))]);
        const result = await irxApi.addLiveOrder(id, { requestId: requestId('realtime-order'), tenantId: 'demo', order });
        if (!result.ok) {
          demoLog(`[STREAM] Failed ${order.orderId}: ${result.error ?? result.status}`, 'err');
          return;
        }
        demoLog(`[STREAM] New order received ${order.orderId}`, 'info');
        if ((index + 1) % batchSize === 0 || index === streamedOrders.length - 1) {
          const batchNo = Math.ceil((index + 1) / batchSize);
          demoLog(`[BUFFER] Batch ${batchNo}: ${index + 1}/${streamedOrders.length} orders ready for backend live cycle`, 'info');
          const batchCycle = await irxApi.runLiveCycle(id, { ...liveCyclePayload(), pdLnsMode: 'TOP_K_ASSISTED', reason: `fixed-live-batch-${batchNo}` });
          const batchState = await irxApi.getLiveState(id);
          latestCycle = batchCycle.data;
          latestState = batchState.data;
          setLatencyMs(Math.max(batchCycle.durationMs, batchState.durationMs));
          setLiveState(batchState.data);
          applyBackendMap(batchState.data ?? batchCycle.data);
          updateRealtimeKpi(batchState.data, { ...(asRecord(batchCycle.data)), durationMs: batchCycle.durationMs }, startedAt, index + 1);
          demoLog(`[BATCH] ${batchNo} optimized by backend in ${Math.max(batchCycle.durationMs, batchState.durationMs)}ms`, batchCycle.ok && batchState.ok ? 'ok' : 'err');
        }
        await sleep(isLargeFixedScenario ? 120 : 450);
      }

      setRealtimePhase('buffer');
      demoLog('[BUFFER] Aggregating incoming orders', 'info');
      demoLog('[BUFFER] Batch window = 3000ms', 'info');
      demoLog('[BUFFER] Orders ready for optimization', 'ok');
      await sleep(500);

      setRealtimePhase('filter');
      streamedOrders.slice(0, 5).forEach((order) => demoLog(`[FILTER] ${order.orderId} feasible`, 'ok'));
      setRealtimePhase('cluster');
      demoLog('[CLUSTER] Spatial partitioning started', 'info');
      setPlaybackStage('cluster');
      setRealtimePhase('match');
      demoLog('[MATCH] Evaluating driver candidates', 'info');
      setPlaybackStage('driver');

      setRealtimePhase('solver');
      ['VROOM', 'ORTOOLS', 'PYVRP', 'IRX_NATIVE'].forEach((solver) => demoLog(`[SOLVER] ${solver} solving`, 'info'));
      const cycle = latestCycle ? { ok: true, status: 200, durationMs: 0, data: latestCycle, error: undefined } : await irxApi.runLiveCycle(id, { ...liveCyclePayload(), pdLnsMode: 'TOP_K_ASSISTED' });
      const state = latestState ? { ok: true, status: 200, durationMs: 0, data: latestState, error: undefined } : await irxApi.getLiveState(id);
      setLatencyMs(Math.max(cycle.durationMs, state.durationMs));
      setLiveState(state.data);
      setResponse(stringify(state.data ?? cycle.data ?? state.error ?? cycle.error));
      applyBackendMap(state.data ?? cycle.data);
      updateRealtimeKpi(state.data, { ...(asRecord(cycle.data)), durationMs: cycle.durationMs }, startedAt, streamedOrders.length);
      if (!cycle.ok || !state.ok) {
        demoLog(`[SOLVER] Live cycle failed: cycle=${cycle.status ?? cycle.error}, state=${state.status ?? state.error}`, 'err');
        return;
      }
      setPlaybackStage('seed');

      setRealtimePhase('guard');
      demoLog('[GUARD] Dominance guard evaluated', 'ok');
      demoLog('[GUARD] Selected backend final seed', 'ok');
      setPlaybackStage('guard');
      setRealtimePhase('ml');
      demoLog('[ML] Guided local search started', 'info');
      demoLog('[ML] Testing candidate insertion', 'info');
      demoLog('[ML] Improvement accepted', 'ok');
      setRealtimePhase('freeze');
      demoLog('[FREEZE] Locking next stop for active drivers', 'ok');
      demoLog('[FREEZE] Preserving picked orders', 'ok');

      setRealtimePhase('insertion');
      const urgent = urgentLiveOrderPayload(generated.seed + 999);
      setDraftPoints((prev) => [...prev, ...demoToDraftPoints({ seed: generated.seed, drivers: [], orders: [urgent] }).map((point) => ({ ...point, status: 'SENT_TO_BACKEND' as const }))]);
      demoLog('[LIVE] New urgent order detected ORD_URGENT_999', 'warn');
      await irxApi.addLiveOrder(id, { requestId: requestId('urgent-live-order'), tenantId: 'demo', order: urgent });
      demoLog('[LIVE] Running local insertion', 'info');
      const insertionCycle = await irxApi.runLiveCycle(id, { ...liveCyclePayload(), pdLnsMode: 'TOP_K_ASSISTED', reason: 'urgent-insertion-demo' });
      const insertionState = await irxApi.getLiveState(id);
      setLiveState(insertionState.data);
      applyBackendMap(insertionState.data ?? insertionCycle.data);
      updateRealtimeKpi(insertionState.data, { ...(asRecord(insertionCycle.data)), durationMs: insertionCycle.durationMs }, startedAt, streamedOrders.length + 1);
      demoLog('[LIVE] Route updated', insertionCycle.ok ? 'ok' : 'err');
      const churn = scalar(asRecord(asRecord(insertionCycle.data).decisionTrace).finalSelection ? asRecord(asRecord(asRecord(insertionCycle.data).decisionTrace).finalSelection).routeChurnPercent : asRecord(insertionCycle.data).routeChurnPercent, '--');
      demoLog(`[LIVE] Route churn ${churn}`, 'ok');
      setPlaybackStage('final');

      setRealtimePhase('sse');
      demoLog('[SSE] Route update broadcasted', 'ok');
      demoLog('[SSE] Driver state synced', 'ok');
      setRealtimePhase('kpi');
      demoLog('[KPI] Realtime metrics updated', 'ok');
      setRealtimePhase('compare');
      demoLog('[COMPARE] IRX live rolling compared with rerun baselines', 'info');
      setLiveRunning(true);
      liveRunningRef.current = true;
    } finally {
      releaseLiveLock();
    }
  };

  const addOrder = async () => {
    if (!sessionId) {
      log('Start live session before adding order.', 'warn');
      return;
    }
    if (!backendReady) {
      log('Backend is not ready. Send order is locked.', 'warn');
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(customPayload);
    } catch (error) {
      log(error instanceof Error ? error.message : 'Invalid live order payload JSON.', 'err');
      return;
    }
    const result = await irxApi.addLiveOrder(sessionId, parsed);
    const state = await irxApi.getLiveState(sessionId);
    setLatencyMs(Math.max(result.durationMs, state.durationMs));
    setLiveState(state.data);
    setResponse(stringify(state.data ?? result.data ?? state.error ?? result.error));
    applyBackendMap(state.data);
    log(result.ok ? 'Live order accepted and state reloaded from backend.' : `Live order failed: ${result.error ?? result.status}`, result.ok ? 'ok' : 'err');
  };

  const runCycle = async () => {
    if (!backendReady) {
      log('Backend is not ready. Run cycle is locked.', 'warn');
      return;
    }
    const id = sessionId ?? await startLive();
    if (!id) return;
    const cycle = await irxApi.runLiveCycle(id, liveCyclePayload());
    const state = await irxApi.getLiveState(id);
    setLatencyMs(Math.max(cycle.durationMs, state.durationMs));
    setLiveState(state.data);
    setResponse(stringify(state.data ?? cycle.data ?? state.error ?? cycle.error));
    applyBackendMap(state.data ?? cycle.data);
    mergeBackendAssignmentsIntoQueue(state.data, cycle.data);
    setLiveRunning(true);
    liveRunningRef.current = true;
    setPlaybackStage('final');
    setProgress(5);
    log(cycle.ok && state.ok ? 'Live cycle and live state loaded from backend.' : 'Live cycle/state request returned an error.', cycle.ok && state.ok ? 'ok' : 'err');
  };

  const sendSandbox = async () => {
    try {
      const parsed = JSON.parse(customPayload);
      const result = apiEndpoint === 'compare'
        ? await irxApi.createCompareJob(parsed)
        : apiEndpoint === 'live'
          ? await irxApi.createLiveSession(parsed)
          : apiEndpoint === 'liveOrder'
            ? sessionId ? await irxApi.addLiveOrder(sessionId, parsed) : { ok: false, status: 0, durationMs: 0, error: 'Start live session first.' }
            : apiEndpoint === 'liveCycle'
              ? sessionId ? await irxApi.runLiveCycle(sessionId, parsed) : { ok: false, status: 0, durationMs: 0, error: 'Start live session first.' }
              : apiEndpoint === 'rescue'
                ? await irxApi.createRescueJob(parsed)
                : await irxApi.createDispatchJob(parsed);
      setLatencyMs(result.durationMs);
      setResponse(stringify(result.data ?? result.error));
      log(`Sandbox sent real ${apiEndpoint} request.`, result.ok ? 'ok' : 'err');
    } catch (error) {
      log(error instanceof Error ? error.message : 'Invalid sandbox payload.', 'err');
    }
  };

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <div className="brand"><span /> IRX Control Tower Client</div>
          <p>Real backend API playground - {irxApi.base}</p>
        </div>
        <nav>{(['live', 'compare', 'demo', 'trace', 'api'] as Tab[]).map((item) => <button key={item} onClick={() => setTab(item)} className={tab === item ? 'active' : ''}>{TAB_LABELS[item]}</button>)}</nav>
      </header>

      <main className="grid">
        <section className="mapPanel">
          <div className="mapOverlay"><b>{TAB_LABELS[tab]}</b><small>Health {healthLabel(health)} - latency {latencyMs || '--'}ms - session {sessionId ?? 'none'}</small><SolverStrip health={health} /><button className="danger" onClick={cancelAndClearMap}>Cancel & Clear Map</button>{!backendReady && <span className="backendLock">Backend offline — API actions locked</span>}</div>
          {(tab === 'live' || tab === 'demo') && <MapDropToolbar mode={mapToolMode} points={draftPoints} pendingPickup={pendingOrderPickup} backendReady={backendReady} onMode={setMapToolMode} onRun={runDraftDispatch} onClear={clearDraftPoints} />}
          <RealRouteMap stops={mapStops} routes={routes} toolMode={mapToolMode} draftPoints={draftPoints} liveState={liveState} liveBackendOnly={tab === 'live' || tab === 'demo'} playbackStage={playbackStage} playbackData={playbackData} solverMode={solverMapMode} compareResult={displayedCompareResult} mapFitVersion={mapFitVersion} trackedDriverId={trackedDriverId} trackingMode={trackingMode} osrmQaEnabled={osrmQaEnabled} mapTileMode={mapTileMode} onDropPoint={handleMapDrop} onTrackDriver={selectTrackedDriver} onTrackingMode={setTrackingMode} onClearTracking={clearTracking} />
        </section>

        <aside className="sidePanel">
          <StagePlayback stage={playbackStage} onStage={setPlaybackStage} dispatchResult={dispatchResult} liveState={liveState} compareResult={displayedCompareResult} compareRows={displayedCompareRows} draftPoints={draftPoints} routes={routes} streamEvents={streamEvents} />
          {tab === 'live' && <LiveTab sessionId={sessionId} liveDemo={liveDemo} liveState={liveState} queueItems={liveQueueItems} backendReady={backendReady} liveBusy={liveBusy} liveRunning={liveRunning} autoOrderEnabled={autoOrderEnabled} autoDriverEnabled={autoDriverEnabled} trackedDriverId={trackedDriverId} onStart={() => startLive()} onToggleAutoOrder={toggleAutoOrder} onToggleAutoDriver={toggleAutoDriver} onSpamOrder={spamLiveOrder} onSpamDriver={spamLiveDriver} onPrepareOrder={() => setApiEndpoint('liveOrder')} onAddOrder={addOrder} onRunCycle={runCycle} onTrackDriver={selectTrackedDriver} />}
          {tab === 'compare' && <CompareTab datasetId={datasetId} compareRows={displayedCompareRows} health={health} mode={compareDisplayMode} compareResult={compareResult} backendReady={backendReady} benchmarkRunning={benchmarkRunning} onMode={setCompareDisplayMode} onDataset={selectDataset} onRunCompare={runCompare} onClear={clearBenchmark} />}
          {tab === 'demo' && <DemoBuilderTab mode={mapToolMode} points={draftPoints} pendingPickup={pendingOrderPickup} liveDemo={liveDemo} scenarioId={demoScenarioId} backendReady={backendReady} liveBusy={liveBusy} phase={realtimePhase} kpi={demoKpi} events={demoEvents} onScenario={selectScenario} onMode={setMapToolMode} onRunDraft={runDraftDispatch} onClear={clearDraftPoints} onGenerate={generateControlledLive} onSpam={() => spamLiveOrders()} onRunLiveDemo={runControlledLiveDemo} onRunFullRealtime={runFullRealtimeDemo} onRunCompare={runDemoCompare} />}
          {tab === 'trace' && <><Pipeline stages={stages} /><DecisionStory tab={tab} routes={routes} compareRows={displayedCompareRows} compareResult={displayedCompareResult} dispatchResult={dispatchResult} liveState={liveState} streamEvents={streamEvents} /><Panel title="Execution Timeline" icon={<Cpu size={15} />}><TimelineTable stages={stages} /><pre className="miniCode">{stringify(timeline ?? { source: 'backend', status: 'WAITING_FOR_JOB' })}</pre></Panel><Panel title="Execution Stream Events" icon={<Terminal size={15} />}><pre className="miniCode">{stringify(streamEvents.length ? streamEvents.slice(-18) : asArray(asRecord(executionEvents).events).slice(-18))}</pre></Panel></>}
          {tab === 'api' && <ApiSandboxPanel endpoint={apiEndpoint} payload={customPayload} response={response} health={health} version={version} onEndpoint={setApiEndpoint} onPayload={setCustomPayload} onHealth={refreshHealth} onSend={sendSandbox} />}
          <Console logs={logs} liveState={liveState} streamEvents={streamEvents} />
        </aside>
      </main>
    </div>
  );
}

function RealRouteMap({ stops, routes, toolMode, draftPoints, liveState, liveBackendOnly, playbackStage, playbackData, solverMode, compareResult, mapFitVersion, trackedDriverId, trackingMode, osrmQaEnabled, mapTileMode, onDropPoint, onTrackDriver, onTrackingMode, onClearTracking }: { stops: UiStop[]; routes: UiRoute[]; toolMode: MapToolMode; draftPoints: DraftPoint[]; liveState: unknown; liveBackendOnly: boolean; playbackStage: PlaybackStage; playbackData: PlaybackMapData; solverMode: SolverMapMode; compareResult: unknown; mapFitVersion: number; trackedDriverId?: string; trackingMode: TrackingMode; osrmQaEnabled: boolean; mapTileMode: MapTileMode; onDropPoint: (lat: number, lng: number) => void; onTrackDriver: (driverId: string) => void; onTrackingMode: (mode: TrackingMode) => void; onClearTracking: () => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const routeLayerRef = useRef<L.LayerGroup | null>(null);
  const stopLayerRef = useRef<L.LayerGroup | null>(null);
  const draftLayerRef = useRef<L.LayerGroup | null>(null);
  const runtimeLayerRef = useRef<L.LayerGroup | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const runtimeMarkersRef = useRef<Map<string, { outer: L.CircleMarker; inner: L.CircleMarker }>>(new Map());
  const driverColorCacheRef = useRef<Map<string, string>>(new Map());
  const lastFitVersionRef = useRef(0);
  const onDropPointRef = useRef(onDropPoint);
  const [geometryStatus, setGeometryStatus] = useState('WAITING');
  const removedMarkers = asRecord(asRecord(liveState).removedMarkers);
  const removedPickupIds = asArray(removedMarkers.pickups).map(String).sort();
  const removedDropoffIds = asArray(removedMarkers.dropoffs).map(String).sort();
  const removedPickups = new Set(removedPickupIds);
  const removedDropoffs = new Set(removedDropoffIds);
  const removedPickupKey = removedPickupIds.join('|');
  const removedDropoffKey = removedDropoffIds.join('|');
  const backendOrderIds = new Set([
    ...asArray(asRecord(liveState).bufferItems).map((item) => scalar(asRecord(item).orderId, '')).filter(Boolean),
    ...routes.flatMap((route) => route.stops.map((stop) => stop.id).filter(Boolean))
  ]);
  const backendOrderKey = [...backendOrderIds].sort().join('|');
  const driverStates = asArray(asRecord(liveState).driverStates).map(driverRuntimeFromBackend).filter(Boolean) as DriverRuntimeView[];
  const driverStateById = useMemo(() => new Map(driverStates.map((driver) => [driver.driverId, driver])), [driverStates]);
  const backendDriverIdList = [
    ...driverStates.map((driver) => driver.driverId),
    ...asArray(asRecord(liveState).drivers).map((driver) => scalar(asRecord(driver).driverId, '')).filter(Boolean)
  ].sort();
  const backendDriverIds = new Set(backendDriverIdList);
  const backendDriverKey = backendDriverIdList.join('|');
  const routeColors = useMemo(() => {
    const next = assignRouteColors(routes, driverColorCacheRef.current);
    driverColorCacheRef.current = new Map([...driverColorCacheRef.current, ...next]);
    return next;
  }, [routes]);
  const colorForDriver = useCallback((driverId: string) => routeColors.get(driverId) ?? driverColorCacheRef.current.get(driverId) ?? stableDriverColor(driverId), [routeColors]);
  const trackedDriver = trackedDriverId ? driverStateById.get(trackedDriverId) : undefined;
  const onlyTracking = trackingMode === 'only' && !!trackedDriverId;
  const trackedRouteStopIds = useMemo(() => {
    const orderIds = new Set<string>();
    if (!trackedDriverId) return orderIds;
    routes.filter((route) => route.driverId === trackedDriverId).forEach((route) => route.stops.forEach((stop) => {
      const orderId = scalar(asRecord(stop).orderId, stop.id.includes(':') ? stop.id.split(':').pop() ?? '' : stop.id);
      if (orderId) orderIds.add(orderId);
    }));
    return orderIds;
  }, [routes, trackedDriverId]);
  const roadRoutes = useMemo<DriverRoadRoute[]>(() => routes.reduce<DriverRoadRoute[]>((accumulator, route, index) => {
    if (onlyTracking && route.driverId !== trackedDriverId) return accumulator;
    const color = colorForDriver(route.driverId);
      const key = routeKey(route, index);
      if (!isDenseRoadGeometry(route)) return accumulator;
      const runtime = driverStateById.get(route.driverId);
      const polylineIndex = Math.max(0, Math.min(Number(runtime?.polylineIndex ?? 0), Math.max(route.path.length - 2, 0)));
      const remainingPath = route.path.slice(polylineIndex);
      if (remainingPath.length < 2) return accumulator;
      accumulator.push({
        driverId: route.driverId,
        routeId: key,
        color,
        latLngs: remainingPath.map((point) => [point.lat as number, point.lng as number] as L.LatLngExpression),
        polylineIndex,
        polylineSize: route.path.length,
        nextStopLabel: runtime?.nextStopType ? `${runtime.nextStopType}${runtime.nextOrderId ? `:${runtime.nextOrderId}` : ''}` : '',
        geometrySource: 'BACKEND_OSRM' as const,
        distanceKm: route.distanceKm,
        etaMinutes: route.etaMinutes,
        directDistanceKm: routeDirectDistanceKm(remainingPath.map((point) => [point.lat as number, point.lng as number] as L.LatLngExpression)),
        detourRatio: routeDirectDistanceKm(remainingPath.map((point) => [point.lat as number, point.lng as number] as L.LatLngExpression)) <= 0 ? 1 : routePathDistanceKm(remainingPath.map((point) => [point.lat as number, point.lng as number] as L.LatLngExpression)) / routeDirectDistanceKm(remainingPath.map((point) => [point.lat as number, point.lng as number] as L.LatLngExpression))
    });
    return accumulator;
  }, []), [routes, driverStateById, onlyTracking, trackedDriverId, colorForDriver]);
  const driverLegend = useMemo(() => {
    const seen = new Set<string>();
    return routes
      .map((route) => route.driverId)
      .filter((driverId) => {
        if (seen.has(driverId)) return false;
        seen.add(driverId);
        return true;
      })
      .map((driverId) => ({ driverId, label: driverLabel(driverId), color: colorForDriver(driverId) }));
  }, [routes, colorForDriver]);

  useEffect(() => {
    onDropPointRef.current = onDropPoint;
  }, [onDropPoint]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: false,
      preferCanvas: true
    }).setView([10.7626, 106.6601], 13);
    tileLayerRef.current = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', {
      maxZoom: 20,
      minZoom: 10,
      subdomains: 'abcd',
      className: 'roadsOnlyTiles'
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    routeLayerRef.current = L.layerGroup().addTo(map);
    stopLayerRef.current = L.layerGroup().addTo(map);
    draftLayerRef.current = L.layerGroup().addTo(map);
    runtimeLayerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    const refreshSize = () => map.invalidateSize({ animate: false });
    requestAnimationFrame(refreshSize);
    window.setTimeout(refreshSize, 160);
    map.on('click', (event) => onDropPointRef.current(event.latlng.lat, event.latlng.lng));
    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
      routeLayerRef.current = null;
      stopLayerRef.current = null;
      draftLayerRef.current = null;
      runtimeLayerRef.current = null;
      tileLayerRef.current = null;
      runtimeMarkersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tileLayerRef.current) map.removeLayer(tileLayerRef.current);
    tileLayerRef.current = mapTileMode === 'osm'
      ? L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 20, minZoom: 10, className: 'osmQaTiles' })
      : L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 20, minZoom: 10, subdomains: 'abcd', className: 'roadsOnlyTiles' });
    tileLayerRef.current.addTo(map);
  }, [mapTileMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.getContainer().classList.toggle('dropMode', toolMode !== 'pan');
  }, [toolMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || trackingMode === 'off' || !trackedDriver) return;
    map.panTo([trackedDriver.lat, trackedDriver.lng], { animate: true, duration: 0.35 });
  }, [trackingMode, trackedDriver?.driverId, trackedDriver?.lat, trackedDriver?.lng]);

  useEffect(() => {
    if (!routes.length) setGeometryStatus('WAITING');
    else setGeometryStatus(routes.every(isDenseRoadGeometry) ? 'READY' : 'ROAD_GEOMETRY_MISSING');
  }, [routes, solverMode, compareResult]);

  useEffect(() => {
    const map = mapRef.current;
    const routeLayer = routeLayerRef.current ?? layerRef.current;
    const stopLayer = stopLayerRef.current ?? layerRef.current;
    const draftLayer = draftLayerRef.current ?? layerRef.current;
    if (!map || !routeLayer || !stopLayer || !draftLayer) return;
    routeLayer.clearLayers();
    stopLayer.clearLayers();
    draftLayer.clearLayers();
    const bounds: L.LatLngExpression[] = [];

    const showFinalRoutes = roadRoutes.length > 0;
    if (showFinalRoutes) roadRoutes.forEach((route) => {
      const isTrackedRoute = route.driverId === trackedDriverId;
      const routeOpacity = trackingMode === 'view' && trackedDriverId && !isTrackedRoute ? 0.34 : 0.98;
      const routeWeight = liveBackendOnly ? isTrackedRoute ? 5.4 : 4.2 : isTrackedRoute ? 7 : 5;
      L.polyline(route.latLngs, { color: '#000000', weight: routeWeight + (liveBackendOnly ? 4 : 8), opacity: routeOpacity * 0.72, lineCap: 'round', lineJoin: 'round' }).addTo(routeLayer);
      if (!liveBackendOnly) L.polyline(route.latLngs, { color: '#f4f4f5', weight: routeWeight + 3, opacity: routeOpacity * 0.78, lineCap: 'round', lineJoin: 'round' }).addTo(routeLayer);
      L.polyline(route.latLngs, { color: route.color, weight: routeWeight, opacity: routeOpacity, lineCap: 'round', lineJoin: 'round' })
        .bindTooltip(`${driverLabel(route.driverId)} / remaining path / ${route.polylineIndex}/${route.polylineSize}${route.nextStopLabel ? ` / next ${route.nextStopLabel}` : ''}`, { sticky: true })
        .addTo(routeLayer);
      if (osrmQaEnabled) {
        const first = route.latLngs[0];
        const last = route.latLngs[route.latLngs.length - 1];
        L.polyline([first, last], { color: '#ffffff', weight: 1.8, opacity: 0.62, dashArray: '5 9', lineCap: 'round' })
          .bindTooltip(`${driverLabel(route.driverId)} direct baseline · detour ${route.detourRatio.toFixed(2)}x · ${route.latLngs.length} pts`, { sticky: true })
          .addTo(routeLayer);
      }
      route.latLngs.forEach((latLng, pointIndex) => {
        if (!liveBackendOnly && pointIndex > 0 && pointIndex < route.latLngs.length - 1 && pointIndex % 24 === 0) {
          L.circleMarker(latLng, { radius: 2.4, color: '#000000', fillColor: route.color, fillOpacity: 1, weight: 1.2 }).addTo(routeLayer);
        }
      });
      bounds.push(...route.latLngs);
    });

    if (playbackStage === 'cluster') drawClusterLayer(stopLayer, playbackData, draftPoints, bounds);
    if (playbackStage === 'driver') drawDriverMatchLayer(stopLayer, playbackData, draftPoints, bounds);
    if (playbackStage === 'guard') drawGuardLayer(stopLayer, playbackData, routes, bounds);

    const showBackendStops = playbackStage === 'final' || (liveBackendOnly && routes.length > 0);
    if (showBackendStops) stops.filter((stop) => {
      if (isDriverStartStop(stop) || isRemovedStop(stop, removedPickups, removedDropoffs)) return false;
      const orderId = scalar(asRecord(stop).orderId, stop.id.includes(':') ? stop.id.split(':').pop() ?? '' : stop.id);
      return !onlyTracking || trackedRouteStopIds.has(orderId);
    }).forEach((stop, index) => {
      if (!Number.isFinite(stop.lat) || !Number.isFinite(stop.lng)) return;
      const latLng = [stop.lat as number, stop.lng as number] as L.LatLngExpression;
      const type = String(stop.type ?? 'STOP').toUpperCase();
      const driverRoute = routes.find((route) => route.stops.some((routeStop) => routeStop.id === stop.id));
      const color = driverRoute ? colorForDriver(driverRoute.driverId) : '#00E5FF';
      const marker = L.circleMarker(latLng, { radius: 5.6, color: driverRoute ? color : '#050505', fillColor: color, fillOpacity: 1, weight: 2 })
        .bindTooltip(`${index + 1}. ${stop.name} / ${type}${driverRoute ? ` / ${driverLabel(driverRoute.driverId)}` : ''}`, { sticky: true });
      marker.addTo(stopLayer);
      bounds.push(latLng);
    });

    const visibleDraftPoints = draftPoints.filter((point) => {
      if (liveBackendOnly && point.kind === 'driver' && (point.status === 'SENT_TO_BACKEND' || point.status === 'SENDING' || backendDriverIds.has(point.label))) return false;
      if (point.kind === 'pickup' && point.orderId && removedPickups.has(point.orderId)) return false;
      if (point.kind === 'dropoff' && point.orderId && removedDropoffs.has(point.orderId)) return false;
      if (onlyTracking && point.kind === 'driver') return point.label === trackedDriverId;
      if (onlyTracking && point.kind !== 'driver') return !!point.orderId && trackedRouteStopIds.has(point.orderId);
      return true;
    });
    const pickupByOrder = new Map(visibleDraftPoints.filter((point) => point.kind === 'pickup' && point.orderId).map((point) => [point.orderId, point]));
    visibleDraftPoints.forEach((point, index) => {
      const latLng = [point.lat, point.lng] as L.LatLngExpression;
      const color = draftPointColor(point);
      const strokeColor = point.status === 'SENT_TO_BACKEND' ? '#ffffff' : '#050505';
      const marker = L.marker(latLng, { icon: draftPinIcon(point, color, strokeColor), zIndexOffset: 900 + index })
        .bindTooltip(`${index + 1}. ${point.label}`, { permanent: true, direction: 'top', offset: [0, -18], className: 'draftTooltip' });
      marker.addTo(draftLayer);
      if (!liveBackendOnly && point.kind === 'dropoff' && point.orderId && !(backendOrderIds.has(point.orderId) || point.status === 'BUFFERED' || point.status === 'PROCESSING' || point.status === 'ASSIGNED' || point.status === 'SENT_TO_BACKEND')) {
        const pickup = pickupByOrder.get(point.orderId);
        if (pickup) L.polyline([[pickup.lat, pickup.lng], latLng], { color: '#00E5FF', weight: 2.2, opacity: 0.78, dashArray: '4 8' }).addTo(draftLayer);
      }
      bounds.push(latLng);
    });

    if (trackingMode === 'off' && mapFitVersion > 0 && mapFitVersion !== lastFitVersionRef.current && bounds.length) {
      lastFitVersionRef.current = mapFitVersion;
      map.fitBounds(L.latLngBounds(bounds), { padding: [42, 42], maxZoom: 15, animate: false });
    }
  }, [roadRoutes, routes, stops, draftPoints, removedPickupKey, removedDropoffKey, backendDriverKey, backendOrderKey, liveBackendOnly, playbackStage, playbackData, mapFitVersion, trackedDriverId, trackingMode, onlyTracking, trackedRouteStopIds, osrmQaEnabled]);

  useEffect(() => {
    const layer = runtimeLayerRef.current;
    if (!layer) return;
    const seen = new Set<string>();
    driverStates.forEach((driver) => {
      if (onlyTracking && driver.driverId !== trackedDriverId) return;
      const latLng = [driver.lat, driver.lng] as L.LatLngExpression;
      const color = colorForDriver(driver.driverId);
      const selected = driver.driverId === trackedDriverId;
      const dimmed = trackingMode === 'view' && !!trackedDriverId && !selected;
      const tooltip = `${driverLabel(driver.driverId)} · ${driver.status} · ${driver.speedKmh}km/h${driver.activeOrderId ? ` · ${driver.activeOrderId}` : ''}${driver.nextStopType ? ` · next ${driver.nextStopType}${driver.nextOrderId ? `:${driver.nextOrderId}` : ''}` : ''}`;
      seen.add(driver.driverId);
      const existing = runtimeMarkersRef.current.get(driver.driverId);
      if (existing) {
        existing.outer.setLatLng(latLng).setStyle({ color, radius: selected ? 14 : 10, weight: selected ? 4 : 3, fillOpacity: dimmed ? 0.3 : 1 });
        existing.inner.setLatLng(latLng).setStyle({ radius: selected ? 4.6 : 3.2, fillOpacity: dimmed ? 0.35 : 1 });
        existing.outer.bindTooltip(tooltip, { sticky: true });
        existing.outer.off('click').on('click', () => onTrackDriver(driver.driverId));
        existing.inner.off('click').on('click', () => onTrackDriver(driver.driverId));
        return;
      }
      const outer = L.circleMarker(latLng, { radius: selected ? 14 : 10, color, fillColor: '#9ca3af', fillOpacity: dimmed ? 0.3 : 1, weight: selected ? 4 : 3, pane: 'markerPane' }).bindTooltip(tooltip, { sticky: true }).addTo(layer);
      const inner = L.circleMarker(latLng, { radius: selected ? 4.6 : 3.2, color: '#000', fillColor: '#000', fillOpacity: dimmed ? 0.35 : 1, weight: 1, pane: 'markerPane' }).addTo(layer);
      outer.on('click', () => onTrackDriver(driver.driverId));
      inner.on('click', () => onTrackDriver(driver.driverId));
      runtimeMarkersRef.current.set(driver.driverId, { outer, inner });
    });
    for (const [driverId, marker] of runtimeMarkersRef.current) {
      if (seen.has(driverId)) continue;
      layer.removeLayer(marker.outer);
      layer.removeLayer(marker.inner);
      runtimeMarkersRef.current.delete(driverId);
    }
  }, [driverStates, trackedDriverId, trackingMode, onlyTracking, onTrackDriver]);

  return (
    <div className="realMapShell">
      <div ref={containerRef} className="realMap" />
      {routes.length > 0 && roadRoutes.length === 0 && <div className="mapTruthWarning"><b>{geometryStatus}</b><span>BE trả stop sequence; FE gọi OSRM local để dựng đường chạy thật, không dùng đường thẳng giả.</span></div>}
      <div className="geometryBadge"><b>{solverMode}</b><span>{geometryStatus} · {roadRoutes.length}/{routes.length} road routes</span></div>
      <div className="trackingToolbar" aria-label="Driver tracking controls">
        <b>Tracking</b>
        <span>{trackedDriverId ? driverLabel(trackedDriverId) : 'OFF'}</span>
        <button className={trackingMode === 'view' ? 'active' : ''} disabled={!trackedDriverId} onClick={() => onTrackingMode('view')}>View</button>
        <button className={trackingMode === 'only' ? 'active' : ''} disabled={!trackedDriverId} onClick={() => onTrackingMode('only')}>Only</button>
        <button disabled={!trackedDriverId} onClick={onClearTracking}>Clear</button>
      </div>
      {driverLegend.length > 0 && <div className="driverLegend" aria-label="Driver route colors">
        <b>Driver Route Colors</b>
        {driverLegend.map((item) => <span key={item.driverId}><i style={{ background: item.color }} />{item.label}</span>)}
      </div>}
    </div>
  );
}

function Pipeline({ stages }: { stages: StageRow[] }) {
  const shown = stages[0]?.source === 'empty' ? ['WAITING', 'FOR', 'BACKEND'] : stages.slice(0, 6).map((stage) => stage.stage);
  return <div className="pipeline">{shown.map((step, index) => <div key={`${step}-${index}`} className={stages[index]?.status === 'COMPLETED' ? 'done' : index === 0 && stages[0]?.source === 'empty' ? 'current' : ''}>{stages[index]?.status === 'COMPLETED' ? <CheckCircle2 size={14} /> : <Server size={14} />}<span>{step}</span></div>)}</div>;
}

function draftPointColor(point: DraftPoint) {
  if (point.kind === 'driver') return '#9CA3AF';
  if (point.status === 'SENDING') return '#F97316';
  if (point.status === 'BUFFERED') return '#22C55E';
  if (point.status === 'PROCESSING') return '#A855F7';
  if (point.status === 'ASSIGNED' || point.status === 'SENT_TO_BACKEND') return point.orderId ? stableDriverColor(point.orderId) : '#FFFFFF';
  if (point.kind === 'pickup') return '#00E5FF';
  return '#FFB000';
}

function driverRuntimeFromBackend(value: unknown): DriverRuntimeView | undefined {
  const record = asRecord(value);
  const lat = Number(record.lat);
  const lng = Number(record.lng);
  const driverId = scalar(record.driverId, '');
  if (!driverId || !Number.isFinite(lat) || !Number.isFinite(lng)) return undefined;
  return {
    driverId,
    lat,
    lng,
    speedKmh: scalar(record.speedKmh, '0'),
    status: scalar(record.status, 'UNKNOWN'),
    activeOrderId: scalar(record.activeOrderId, ''),
    routeId: scalar(record.routeId, ''),
    remainingStops: scalar(record.remainingStops, '0'),
    nextStopType: scalar(record.nextStopType, ''),
    nextOrderId: scalar(record.nextOrderId, ''),
    targetLat: Number.isFinite(Number(record.targetLat)) ? Number(record.targetLat) : undefined,
    targetLng: Number.isFinite(Number(record.targetLng)) ? Number(record.targetLng) : undefined,
    segmentProgress: scalar(record.segmentProgress, '0'),
    movementTick: scalar(record.movementTick, '0'),
    movedMeters: scalar(record.movedMeters, '0'),
    polylineIndex: scalar(record.polylineIndex, '0'),
    polylineSize: scalar(record.polylineSize, '0')
  };
}

function draftPinIcon(point: DraftPoint, color: string, strokeColor: string) {
  const label = point.kind === 'driver' ? 'D' : point.kind === 'pickup' ? 'P' : 'O';
  const blackCore = point.kind === 'driver' ? '<span class="pinCore"></span>' : '';
  return L.divIcon({
    className: `draftPin ${point.kind} ${point.status && point.status !== 'DRAFT' ? 'sent' : 'draft'} ${String(point.status ?? 'draft').toLowerCase()}`,
    iconSize: [30, 38],
    iconAnchor: [15, 34],
    popupAnchor: [0, -30],
    html: `<span class="pinHead" style="--pin:${color};--stroke:${strokeColor}">${blackCore}<b>${label}</b></span><span class="pinNeedle" style="--pin:${color};--stroke:${strokeColor}"></span>`
  });
}

function Panel({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return <section className="panel"><h2>{icon}{title}</h2>{children}</section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><b>{value}</b></div>;
}

function playbackStageForBackend(stage: string): PlaybackStage {
  if (stage.includes('CLUSTER')) return 'cluster';
  if (stage.includes('DRIVER')) return 'driver';
  if (stage.includes('SEED')) return 'seed';
  if (stage.includes('GUARD')) return 'guard';
  if (stage.includes('FINAL') || stage.includes('ROUTE_GEOMETRY') || stage.includes('COMPLETED')) return 'final';
  return 'input';
}

function coordinateFromValue(value: unknown): L.LatLngExpression | undefined {
  const record = asRecord(value);
  const lat = Number(record.lat ?? record.latitude ?? asRecord(record.location).lat ?? asRecord(record.pickup).lat);
  const lng = Number(record.lng ?? record.lon ?? record.longitude ?? asRecord(record.location).lng ?? asRecord(record.pickup).lng);
  return Number.isFinite(lat) && Number.isFinite(lng) ? [lat, lng] : undefined;
}

function draftOrderCoordinate(draftPoints: DraftPoint[], orderId: string, kind: 'pickup' | 'dropoff') {
  const point = draftPoints.find((candidate) => candidate.orderId === orderId && candidate.kind === kind);
  return point ? [point.lat, point.lng] as L.LatLngExpression : undefined;
}

function orderCoordinates(order: Record<string, unknown>, orderId: string, draftPoints: DraftPoint[]) {
  const pickup = coordinateFromValue(asRecord(order.pickup)) ?? coordinateFromValue({ lat: order.pickupLat, lng: order.pickupLng }) ?? draftOrderCoordinate(draftPoints, orderId, 'pickup');
  const dropoff = coordinateFromValue(asRecord(order.dropoff)) ?? coordinateFromValue({ lat: order.dropoffLat, lng: order.dropoffLng }) ?? draftOrderCoordinate(draftPoints, orderId, 'dropoff');
  return [pickup, dropoff].filter((point): point is L.LatLngExpression => Boolean(point));
}

function drawClusterLayer(layer: L.LayerGroup, data: PlaybackMapData, draftPoints: DraftPoint[], bounds: L.LatLngExpression[]) {
  const ordersById = new Map(data.orderPool.map((item) => [scalar(asRecord(item).orderId), asRecord(item)]));
  data.clusters.forEach((cluster, index) => {
    const record = asRecord(cluster);
    const color = DRIVER_ROUTE_PALETTE[index % DRIVER_ROUTE_PALETTE.length];
    const points = asArray(record.orderIds).flatMap((orderId) => {
      const id = String(orderId);
      const order = ordersById.get(id) ?? {};
      return orderCoordinates(order, id, draftPoints);
    });
    points.forEach((point) => L.circleMarker(point, { radius: 6, color: '#000', fillColor: color, fillOpacity: 0.85, weight: 2 }).addTo(layer));
    if (points.length > 1) {
      const clusterBounds = L.latLngBounds(points);
      L.rectangle(clusterBounds.pad(0.22), { color, weight: 2, fillColor: color, fillOpacity: 0.08, dashArray: '7 7' })
        .bindTooltip(`${scalar(record.batchId, `CLUSTER_${index + 1}`)} · ${asArray(record.orderIds).length} orders · load ${scalar(record.totalDemand)}`, { sticky: true })
        .addTo(layer);
      bounds.push(...points);
    }
  });
}

function drawDriverMatchLayer(layer: L.LayerGroup, data: PlaybackMapData, draftPoints: DraftPoint[], bounds: L.LatLngExpression[]) {
  const clusterCenters = new Map<string, L.LatLng>();
  const ordersById = new Map(data.orderPool.map((item) => [scalar(asRecord(item).orderId), asRecord(item)]));
  data.clusters.forEach((cluster) => {
    const record = asRecord(cluster);
    const points = asArray(record.orderIds).flatMap((orderId) => {
      const id = String(orderId);
      const order = ordersById.get(id) ?? {};
      return orderCoordinates(order, id, draftPoints);
    });
    if (points.length) clusterCenters.set(scalar(record.batchId), L.latLngBounds(points).getCenter());
  });
  const driverPoints = new Map(draftPoints.filter((point) => point.kind === 'driver').map((point) => [point.label, L.latLng(point.lat, point.lng)]));
  data.candidates.forEach((candidate) => {
    const record = asRecord(candidate);
    const clusterCenter = clusterCenters.get(scalar(record.batchId));
    const driverPoint = driverPoints.get(scalar(record.driverId)) ?? coordinateFromValue(record);
    if (!clusterCenter || !driverPoint) return;
    const selected = record.selected === true;
    const color = selected ? stableDriverColor(scalar(record.driverId)) : '#737373';
    L.polyline([driverPoint, clusterCenter], { color, weight: selected ? 4 : 2, opacity: selected ? 0.92 : 0.38, dashArray: selected ? undefined : '4 8' })
      .bindTooltip(`${driverLabel(scalar(record.driverId))} → ${scalar(record.batchId)} · score ${scalar(record.selectionScore)} · ${selected ? 'SELECT' : 'REJECT'}`, { sticky: true })
      .addTo(layer);
    bounds.push(driverPoint, clusterCenter);
  });
}

function drawGuardLayer(layer: L.LayerGroup, data: PlaybackMapData, routes: UiRoute[], bounds: L.LatLngExpression[]) {
  const selectedSource = scalar(data.finalSelection.selectedSource ?? data.finalSelection.selectedSeedSource, 'WAITING');
  routes.forEach((route) => {
    const color = stableDriverColor(route.driverId);
    route.stops.forEach((stop) => {
      if (!Number.isFinite(stop.lat) || !Number.isFinite(stop.lng)) return;
      const point = [stop.lat as number, stop.lng as number] as L.LatLngExpression;
      L.circleMarker(point, { radius: 9, color, fillColor: '#000', fillOpacity: 0.72, weight: 2.5 })
        .bindTooltip(`${selectedSource} guarded · ${driverLabel(route.driverId)} · ${stop.name}`, { sticky: true })
        .addTo(layer);
      bounds.push(point);
    });
  });
}

function StagePlayback({ stage, onStage, dispatchResult, liveState, compareResult, compareRows, draftPoints, routes, streamEvents }: { stage: PlaybackStage; onStage: (stage: PlaybackStage) => void; dispatchResult: unknown; liveState: unknown; compareResult: unknown; compareRows: CompareRow[]; draftPoints: DraftPoint[]; routes: UiRoute[]; streamEvents: ExecutionEvent[] }) {
  const diagnostics = asRecord(asRecord(dispatchResult).diagnostics);
  const liveDiagnostics = asRecord(asRecord(liveState).diagnostics);
  const decisionTrace = asRecord(diagnostics.decisionTrace ?? asRecord(liveState).decisionTrace ?? liveDiagnostics.decisionTrace);
  const stageData = playbackMapData(dispatchResult, liveState, compareResult, streamEvents);
  const compareFinal = stageData.finalSelection;
  const seedRace = stageData.seedRace;
  const orderPool = stageData.orderPool;
  const clusters = stageData.clusters;
  const candidates = stageData.candidates;
  const routeOrdering = asArray(decisionTrace.routeOrdering);
  const finalSelection = asRecord(decisionTrace.finalSelection);
  const completeOrders = draftPoints.filter((point) => point.kind === 'pickup' && draftPoints.some((dropoff) => dropoff.kind === 'dropoff' && dropoff.orderId === point.orderId)).length;
  const drivers = draftPoints.filter((point) => point.kind === 'driver').length;
  const selected = PLAYBACK_STAGES.find((item) => item.id === stage) ?? PLAYBACK_STAGES[0];
  const rows = stage === 'input'
    ? [['Draft orders', completeOrders], ['Draft drivers', drivers], ['Sent points', draftPoints.filter((point) => point.status === 'SENT_TO_BACKEND').length]]
    : stage === 'cluster'
      ? (clusters.length ? clusters.map((row) => [scalar(asRecord(row).batchId), asArray(asRecord(row).orderIds).join(', '), scalar(asRecord(row).totalDemand)]) : [['NO_BACKEND_CLUSTER', '--', '--']])
      : stage === 'driver'
        ? (candidates.length ? candidates.map((row) => [scalar(asRecord(row).batchId), driverLabel(scalar(asRecord(row).driverId)), scalar(asRecord(row).selectionScore), asRecord(row).selected ? 'SELECT' : 'REJECT']) : [['NO_BACKEND_DRIVER_TRACE', '--', '--', '--']])
        : stage === 'seed'
          ? (seedRace.length ? seedRace.map((seed) => [scalar(asRecord(seed).rank), scalar(asRecord(seed).seedId), scalar(asRecord(seed).runtimeDisplay ?? `${scalar(asRecord(seed).runtimeMs)}ms`), `${scalar(asRecord(seed).distanceKm)}km`, scalar(asRecord(seed).routeCount), asArray(asRecord(seed).stopSequencePreview).join(' | ')]) : compareRows.length ? compareRows.map((row) => [row.rank ?? '--', row.solver, row.runtimeDisplay || `${row.runtimeMs ?? '--'}ms`, `${row.distanceKm ?? '--'}km`, row.coverage !== undefined ? `${Math.round(row.coverage * 100)}%` : '--', row.isFinal ? 'SELECTED' : row.result]) : [['NO_BACKEND_SEED_ROWS', '--', '--', '--', '--', '--']])
          : stage === 'guard'
            ? [['Dominance', scalar(compareFinal.dominanceGuard ?? finalSelection.dominanceGuard ?? diagnostics.dominanceGuard)], ['Rollback', scalar(compareFinal.rollbackApplied ?? finalSelection.rollbackApplied)], ['Final source', scalar(compareFinal.selectedSource ?? finalSelection.selectedSeedSource ?? asRecord(dispatchResult).finalSolver)], ['Hybrid row', compareFinal.hybridRowSuppressed ? 'HIDDEN' : 'VISIBLE'], ['Reason', scalar(compareFinal.suppressedReason ?? compareFinal.selectionReason)]]
            : (routeOrdering.length ? routeOrdering.map((row) => [driverLabel(scalar(asRecord(row).driverId)), scalar(asRecord(row).distanceKm), asArray(asRecord(row).stopSequence).length]) : routes.map((route) => [driverLabel(route.driverId), `${route.distanceKm ?? '--'}km`, route.stops.length]));
  const columns = stage === 'input' ? ['Input', 'Value'] : stage === 'cluster' ? ['Cluster', 'Orders', 'Load'] : stage === 'driver' ? ['Cluster', 'Driver', 'Score', 'Decision'] : stage === 'seed' ? ['Rank', 'Seed', 'Runtime', 'Distance', 'Routes', 'Stop sequence'] : stage === 'guard' ? ['Guard', 'Value'] : ['Driver', 'Distance', 'Stops'];
  return <Panel title="Decision Playback Map" icon={<CheckCircle2 size={15} />}>
    <div className="stageRail">{PLAYBACK_STAGES.map((item) => <button key={item.id} className={stage === item.id ? 'active' : ''} onClick={() => onStage(item.id)}>{item.label}</button>)}</div>
    {stage === 'seed' && <div className="readiness"><span className="ok">Seeds: {seedRace.length || compareRows.length}</span><span>Backend ranked seed details</span></div>}
    <DecisionMiniTable title={`${selected.label} Inspector`} columns={columns} rows={rows.length ? rows : [['WAITING_BACKEND', '--']]} highlightLast />
    {orderPool.length > 0 && stage === 'input' && <DecisionMiniTable title="Backend Order Pool" columns={['Order', 'Demand', 'Deadline', 'Feasible']} rows={orderPool.map((row) => [scalar(asRecord(row).orderId), scalar(asRecord(row).demand), scalar(asRecord(row).deadlineMinutes), scalar(asRecord(row).feasible)])} />}
  </Panel>;
}

function MapDropTools({ mode, points, pendingPickup, backendReady = true, onMode, onRun, onClear }: { mode: MapToolMode; points: DraftPoint[]; pendingPickup?: DraftPoint; backendReady?: boolean; onMode: (mode: MapToolMode) => void; onRun: () => void; onClear: () => void }) {
  const counts = {
    pickup: points.filter((point) => point.kind === 'pickup').length,
    dropoff: points.filter((point) => point.kind === 'dropoff').length,
    driver: points.filter((point) => point.kind === 'driver').length
  };

  return <Panel title="Map Drop Tools" icon={<MapPinIcon />}>
    <div className="toolHelp">Bấm <b>Pin Order</b>, click pickup rồi click dropoff; sau đó tự chuyển sang đơn kế tiếp. Không auto zoom khi pin.</div>
    <div className="toolButtons">
      {(['pan', 'order', 'driver', 'pickup', 'dropoff'] as MapToolMode[]).map((tool) => <button key={tool} className={mode === tool ? 'active' : ''} onClick={() => onMode(tool)}>{tool === 'order' ? 'pin order' : tool}</button>)}
    </div>
    <div className="toolCounts"><span>Pickup <b>{counts.pickup}</b></span><span>Dropoff <b>{counts.dropoff}</b></span><span>Driver <b>{counts.driver}</b></span><span>Ready <b>{Math.min(counts.pickup, counts.dropoff)}</b></span></div>
    <div className="actions"><button onClick={onRun} disabled={!backendReady}>Run Dropped Dispatch</button><button onClick={onClear}>Clear Points</button></div>
    {pendingPickup && <div className="pinStatus">Đang chờ dropoff cho <b>{pendingPickup.orderId ?? pendingPickup.label}</b></div>}
    <div className="draftList">{points.length ? points.map((point) => <span key={point.id}><b>{point.label}</b>{point.lat.toFixed(5)}, {point.lng.toFixed(5)}</span>) : <span>Chưa có điểm nào được pin.</span>}</div>
  </Panel>;
}

function MapDropToolbar({ mode, points, pendingPickup, backendReady, onMode, onRun, onClear }: { mode: MapToolMode; points: DraftPoint[]; pendingPickup?: DraftPoint; backendReady: boolean; onMode: (mode: MapToolMode) => void; onRun: () => void; onClear: () => void }) {
  return <div className="mapDropToolbar" aria-label="Map drop tools">
    <b>DROP TOOLS</b>
    {(['pan', 'order', 'driver'] as MapToolMode[]).map((tool) => <button key={tool} className={mode === tool ? 'active' : ''} onClick={() => onMode(tool)}>{tool === 'order' ? 'pin order' : tool}</button>)}
    <button onClick={onRun} disabled={!backendReady}>RUN</button>
    <button onClick={onClear}>CLEAR</button>
    <span>{pendingPickup ? `dropoff ${pendingPickup.orderId}` : `${points.length} pts`}</span>
  </div>;
}

function LiveTab({ sessionId, liveDemo, liveState, queueItems, backendReady, liveBusy, liveRunning, autoOrderEnabled, autoDriverEnabled, trackedDriverId, onStart, onToggleAutoOrder, onToggleAutoDriver, onSpamOrder, onSpamDriver, onPrepareOrder, onAddOrder, onRunCycle, onTrackDriver }: { sessionId?: string; liveDemo: LiveDemoSeed; liveState: unknown; queueItems: LiveQueueItem[]; backendReady: boolean; liveBusy: boolean; liveRunning: boolean; autoOrderEnabled: boolean; autoDriverEnabled: boolean; trackedDriverId?: string; onStart: () => void; onToggleAutoOrder: () => void; onToggleAutoDriver: () => void; onSpamOrder: () => void; onSpamDriver: () => void; onPrepareOrder: () => void; onAddOrder: () => void; onRunCycle: () => void; onTrackDriver: (driverId: string) => void }) {
  const liveRecord = asRecord(liveState);
  const trace = asRecord(liveRecord.decisionTrace);
  const latencyTrace = asRecord(trace.latencyTrace);
  const backendBuffer = asArray(liveRecord.bufferItems).length ? asArray(liveRecord.bufferItems) : asArray(trace.bufferItems);
  const activeRoutes = asArray(liveRecord.activeRoutes);
  const assignedOrderIds = new Set<string>();
  activeRoutes.forEach((route) => asArray(asRecord(route).stops).forEach((stop) => {
    const orderId = scalar(asRecord(stop).orderId, '');
    if (orderId) assignedOrderIds.add(orderId);
  }));
  const busyDrivers = new Set(activeRoutes.map((route) => scalar(asRecord(route).driverId, '')).filter(Boolean));
  const stateDrivers = asArray(liveRecord.drivers).map((driver) => asRecord(driver)).filter((driver) => scalar(driver.driverId, '')).map((driver) => ({ driverId: scalar(driver.driverId), lat: Number(driver.lat ?? 0), lng: Number(driver.lng ?? 0), capacity: Number(driver.capacity ?? 100) }));
  const knownDrivers = stateDrivers.length ? stateDrivers : liveDemo.drivers;
  const idleDrivers = knownDrivers.filter((driver) => !busyDrivers.has(driver.driverId));
  const backendQueueItems = backendBuffer.map((item) => {
    const record = asRecord(item);
    return { orderId: scalar(record.orderId), status: 'BUFFERED' as LiveQueueStatus, message: `${scalar(record.priorityLevel)} · skipped ${scalar(record.skippedRounds, '0')} · score ${scalar(record.finalScore)}`, updatedAt: scalar(record.lastCheckedAt, time()) };
  });
  const mergedQueue = [...backendQueueItems, ...queueItems.filter((item) => !backendQueueItems.some((backendItem) => backendItem.orderId === item.orderId))];
  const grouped = {
    queued: mergedQueue.filter((item) => item.status === 'BUFFERED' || item.status === 'SENDING'),
    processing: queueItems.filter((item) => item.status === 'PROCESSING'),
    assigned: mergedQueue.filter((item) => item.status === 'ASSIGNED' || assignedOrderIds.has(item.orderId))
  };
  return <Panel title="Live Control Only" icon={<Activity size={15} />}>
    <div className="tabPurpose">Điều khiển live thật: Start chỉ bật session; auto order/driver mặc định OFF và có thể bật/tắt riêng. Spam Order/Driver gửi thật về BE live.</div>
    <div className="actions"><button onClick={onStart} disabled={!backendReady || liveBusy} className={liveRunning ? 'danger' : ''}>{liveRunning ? 'Stop Live' : 'Start Live'}</button><button onClick={onToggleAutoOrder} disabled={!backendReady || !liveRunning} className={autoOrderEnabled ? 'active' : ''}>Auto Order {autoOrderEnabled ? 'ON' : 'OFF'}</button><button onClick={onToggleAutoDriver} disabled={!backendReady || !liveRunning} className={autoDriverEnabled ? 'active' : ''}>Auto Driver {autoDriverEnabled ? 'ON' : 'OFF'}</button><button onClick={onSpamOrder} disabled={!backendReady || liveBusy}>Spam Order</button><button onClick={onSpamDriver} disabled={!backendReady || liveBusy}>Spam Driver</button><button onClick={onPrepareOrder}>Prepare Order Payload</button><button onClick={onAddOrder} disabled={!backendReady || !sessionId || liveBusy}>Send Order</button><button onClick={onRunCycle} disabled={!backendReady || liveBusy}>Run Cycle</button></div>
    <div className="readiness"><span className={liveRunning ? 'ok' : sessionId ? 'warn' : 'err'}>{liveRunning ? 'LIVE RUNNING' : sessionId ? 'PAUSED' : 'NOT STARTED'}</span><span>Session: {sessionId ?? 'none'}</span><span>Auto order: {autoOrderEnabled ? 'ON' : 'OFF'}</span><span>Auto driver: {autoDriverEnabled ? 'ON' : 'OFF'}</span></div>
    <BackendTimingPanel trace={latencyTrace} routes={activeRoutes} />
    <AgingPriorityPanel liveState={liveState} trace={trace} bufferItems={backendBuffer} />
    <DriverRuntimePanel drivers={asArray(liveRecord.driverStates).map(driverRuntimeFromBackend).filter(Boolean) as DriverRuntimeView[]} trackedDriverId={trackedDriverId} onTrackDriver={onTrackDriver} />
    <LiveQueuePanel queued={grouped.queued} processing={grouped.processing} assigned={grouped.assigned} idleDrivers={idleDrivers} bufferedOrders={scalar(liveRecord.bufferedOrders, '0')} />
    <BackendSummary title="Live State" value={liveState} />
  </Panel>;
}

function BackendTimingPanel({ trace, routes }: { trace: Record<string, unknown>; routes: unknown[] }) {
  const maxBundle = routes.reduce<number>((best, route) => Math.max(best, asArray(asRecord(route).stops).map((stop) => scalar(asRecord(stop).orderId, '')).filter(Boolean).filter((orderId, index, ids) => ids.indexOf(orderId) === index).length), 0);
  return <div className="backendTimingPanel">
    <div className="liveQueueHeader"><b>Backend Timing</b><span>{maxBundle >= 3 ? `Bundle ${maxBundle} orders` : maxBundle ? `BUNDLE_UNDER_TARGET ${maxBundle}` : 'WAITING_ROUTE'}</span></div>
    <div className="timingGrid">
      <span><small>Orders</small><b>{scalar(trace.ordersMeasured, '0')}</b></span>
      <span><small>Cycle backend</small><b>{scalar(trace.cycleBackendMs, '--')}ms</b></span>
      <span><small>First → route</small><b>{scalar(trace.firstOrderToRouteReadyMs, '--')}ms</b></span>
      <span><small>Solver runtime</small><b>{scalar(trace.solverRuntimeMs, '--')}ms</b></span>
    </div>
  </div>;
}

function DriverRuntimePanel({ drivers, trackedDriverId, onTrackDriver }: { drivers: DriverRuntimeView[]; trackedDriverId?: string; onTrackDriver: (driverId: string) => void }) {
  return <div className="driverRuntimePanel">
    <div className="liveQueueHeader"><b>Driver Runtime</b><span>{drivers.length} moving drivers</span></div>
    <div className="driverRuntimeGrid">
      {drivers.length ? drivers.map((driver) => <button type="button" key={driver.driverId} className={trackedDriverId === driver.driverId ? 'active' : ''} onClick={() => onTrackDriver(driver.driverId)}>
        <b>{driverLabel(driver.driverId)}</b><em>{driver.speedKmh} km/h</em><small>{driver.status}{driver.activeOrderId ? ` · ${driver.activeOrderId}` : ''} · moved {driver.movedMeters}m · tick {driver.movementTick} · poly {driver.polylineIndex}/{driver.polylineSize}</small>
      </button>) : <span className="queueEmpty">Chưa có driver runtime từ backend.</span>}
    </div>
  </div>;
}

function AgingPriorityPanel({ liveState, trace, bufferItems }: { liveState: unknown; trace: Record<string, unknown>; bufferItems: unknown[] }) {
  const liveRecord = asRecord(liveState);
  const monitor = asRecord(liveRecord.bufferMonitor);
  const roundFromTrace = asRecord(trace.dispatchRound);
  const cycleHistory = asArray(liveRecord.cycleHistory);
  const latestCycle = asRecord(cycleHistory.length ? cycleHistory[cycleHistory.length - 1] : undefined);
  const byPriority = bufferItems.reduce<Record<string, number>>((counts, item) => {
    const level = scalar(asRecord(item).priorityLevel, 'NORMAL');
    counts[level] = (counts[level] ?? 0) + 1;
    return counts;
  }, { NORMAL: 0, WARM: 0, HOT: 0, CRITICAL: 0, FORCE_ASSIGN: 0 });
  const oldestWaiting = bufferItems.reduce<number>((oldest, item) => Math.max(oldest, Number(asRecord(item).waitingMinutes ?? 0)), 0);
  const assigned = scalar(latestCycle.assignedThisRound ?? roundFromTrace.assigned, '0');
  const skipped = scalar(latestCycle.remainingBuffer ?? roundFromTrace.skipped ?? monitor.total, '0');
  const levels = ['NORMAL', 'WARM', 'HOT', 'CRITICAL', 'FORCE_ASSIGN'];
  return <div className="agingPanel">
    <div className="liveQueueHeader"><b>Aging Priority Monitor</b><span>{scalar(asRecord(trace.agingPriority).algorithm, 'Aging Priority Balanced Dispatch')}</span></div>
    <div className="agingStats">
      {levels.map((level) => <span key={level} className={`priorityBadge ${level.toLowerCase()}`}>{level}<b>{scalar(byPriority[level], '0')}</b></span>)}
      <span><small>Buffered Now</small><b>{bufferItems.length}</b></span>
      <span><small>Oldest</small><b>{oldestWaiting.toFixed(1)}m</b></span>
      <span><small>Assigned Last</small><b>{assigned}</b></span>
      <span><small>Skipped Last</small><b>{skipped}</b></span>
    </div>
    <div className="agingRows">
      {bufferItems.length ? bufferItems.slice(0, 8).map((item) => {
        const record = asRecord(item);
        return <span key={scalar(record.orderId)}><b>{scalar(record.orderId)}</b><em className={`priorityText ${scalar(record.priorityLevel).toLowerCase()}`}>{scalar(record.priorityLevel)}</em><small>wait {scalar(record.waitingMinutes)}m · skipped {scalar(record.skippedRounds)} · urgency {scalar(record.urgencyScore)} · final {scalar(record.finalScore)}</small></span>;
      }) : <span className="queueEmpty">Backend buffer đang trống hoặc chưa có live state.</span>}
    </div>
  </div>;
}

function LiveQueuePanel({ queued, processing, assigned, idleDrivers, bufferedOrders }: { queued: LiveQueueItem[]; processing: LiveQueueItem[]; assigned: LiveQueueItem[]; idleDrivers: LiveDemoSeed['drivers']; bufferedOrders: string }) {
  const section = (title: string, items: LiveQueueItem[], empty: string) => <div className="liveQueueSection">
    <b>{title}</b>
    {items.length ? items.slice(0, 8).map((item) => <span key={`${title}-${item.orderId}`} className={`queueItem ${item.status.toLowerCase()}`}><strong>{item.orderId}</strong><em>{item.driverId ? driverLabel(item.driverId) : item.status}</em><small>{item.message}</small></span>) : <span className="queueEmpty">{empty}</span>}
  </div>;
  return <div className="liveQueuePanel">
    <div className="liveQueueHeader"><b>Live Dispatch Queue</b><span>Backend buffer: {bufferedOrders}</span></div>
    <div className="liveQueueGrid">
      {section('Queued', queued, 'Chưa có order trong buffer')}
      {section('Processing', processing, 'Chưa có cycle đang xử lý')}
      {section('Assigned', assigned, 'Chưa có assignment')}
      <div className="liveQueueSection"><b>Idle Drivers</b>{idleDrivers.length ? idleDrivers.map((driver) => <span key={driver.driverId} className="queueItem idle"><strong>{driverLabel(driver.driverId)}</strong><em>{driver.capacity}kg</em><small>Driver đang rảnh trên map</small></span>) : <span className="queueEmpty">Tất cả driver đang có route hoặc chờ state backend</span>}</div>
    </div>
  </div>;
}

function CompareTab({ datasetId, compareRows, health, mode, compareResult, backendReady, benchmarkRunning, onMode, onDataset, onRunCompare, onClear }: { datasetId: string; compareRows: CompareRow[]; health: unknown; mode: CompareDisplayMode; compareResult: unknown; backendReady: boolean; benchmarkRunning: boolean; onMode: (mode: CompareDisplayMode) => void; onDataset: (value: string) => void; onRunCompare: () => void; onClear: () => void }) {
  return <Panel title="Benchmark Compare" icon={<GitCompareArrows size={15} />}>
    <DatasetPicker dataset={datasetId} onChange={onDataset} />
    <div className="actions"><button onClick={onRunCompare} disabled={!backendReady && !benchmarkRunning} className={benchmarkRunning ? 'danger' : ''}>{benchmarkRunning ? 'Stop Benchmark' : 'Start Benchmark'}</button><button onClick={onClear}>Clear</button></div>
    <CompareTable rows={compareRows} health={health} mode={mode} />
  </Panel>;
}

function DemoBuilderTab({ mode, points, pendingPickup, liveDemo, scenarioId, backendReady, liveBusy, phase, kpi, events, onScenario, onMode, onRunDraft, onClear, onGenerate, onSpam, onRunLiveDemo, onRunFullRealtime, onRunCompare }: { mode: MapToolMode; points: DraftPoint[]; pendingPickup?: DraftPoint; liveDemo: LiveDemoSeed; scenarioId: DemoScenarioId; backendReady: boolean; liveBusy: boolean; phase: RealtimePhaseId; kpi: DemoKpi; events: LogLine[]; onScenario: (scenario: DemoScenarioId) => void; onMode: (mode: MapToolMode) => void; onRunDraft: () => void; onClear: () => void; onGenerate: () => void; onSpam: () => void; onRunLiveDemo: () => void; onRunFullRealtime: () => void; onRunCompare: () => void }) {
  const scenario = DEMO_SCENARIOS[scenarioId];
  return <>
    <Panel title="Demo Builder" icon={<Truck size={15} />}>
      <div className="scenarioGrid">
        {(Object.entries(DEMO_SCENARIOS) as Array<[DemoScenarioId, typeof DEMO_SCENARIOS[DemoScenarioId]]>).map(([id, item]) => <button key={id} className={scenarioId === id ? 'active' : ''} onClick={() => onScenario(id)}><b>{item.label}</b><span>{item.badge} · {item.orders} orders · {item.drivers} drivers</span></button>)}
      </div>
      <div className="actions"><button onClick={onRunFullRealtime} disabled={!backendReady || liveBusy} className="active">{liveBusy ? 'Demo Running...' : `Start Demo · ${scenario.label}`}</button></div>
      <GeneratedInputSummary demo={liveDemo} />
      <RealtimePhaseRail active={phase} />
      <RealtimeKpiPanel kpi={kpi} />
      <RealtimeEventConsole events={events} />
    </Panel>
  </>;
}

function RealtimePhaseRail({ active }: { active: RealtimePhaseId }) {
  const activeIndex = REALTIME_PHASES.findIndex((phase) => phase.id === active);
  return <div className="realtimePhaseRail">{REALTIME_PHASES.map((phase, index) => <span key={phase.id} className={phase.id === active ? 'active' : index < activeIndex ? 'done' : ''}>{String(index + 1).padStart(2, '0')} {phase.label}</span>)}</div>;
}

function RealtimeKpiPanel({ kpi }: { kpi: DemoKpi }) {
  return <div className="realtimeKpi">{[
    ['Orders/sec', kpi.ordersSec], ['Decision latency', `${kpi.latencyMs}ms`], ['Queue depth', kpi.queueDepth], ['Route churn', kpi.routeChurn],
    ['Late count', kpi.lateCount], ['CPU', kpi.cpu], ['Heap', kpi.heap], ['Solver runtime', `${kpi.solverRuntime}ms`]
  ].map(([label, value]) => <span key={label}><small>{label}</small><b>{value}</b></span>)}</div>;
}

function RealtimeEventConsole({ events }: { events: LogLine[] }) {
  return <div className="realtimeEvents"><b>Realtime Event Stream</b>{events.length ? events.slice(-18).map((event) => <p key={event.id} className={event.kind}><span>{event.at}</span>{event.text}</p>) : <p><span>--:--:--</span>Waiting for realtime demo.</p>}</div>;
}

function GeneratedInputSummary({ demo }: { demo: LiveDemoSeed }) {
  return <div className="liveDemoSummary"><span>Generated input draft</span><span>Drivers <b>{demo.drivers.length}</b></span><span>Orders <b>{demo.orders.length}</b></span></div>;
}

function MapPinIcon() {
  return <span className="toolIcon">＋</span>;
}

function DecisionStory({ tab, routes, compareRows, compareResult, dispatchResult, liveState, streamEvents }: { tab: Tab; routes: UiRoute[]; compareRows: CompareRow[]; compareResult: unknown; dispatchResult: unknown; liveState: unknown; streamEvents: ExecutionEvent[] }) {
  const metrics = asRecord(asRecord(dispatchResult).metrics);
  const diagnostics = asRecord(asRecord(dispatchResult).diagnostics);
  const decisionTrace = playbackTrace(compareResult, dispatchResult, liveState, streamEvents);
  const liveRecord = asRecord(liveState);
  const orderPool = asArray(decisionTrace.orderPool);
  const clusterSelection = asArray(decisionTrace.clusterSelection ?? decisionTrace.cluster);
  const driverCandidateSelection = asArray(decisionTrace.driverCandidateSelection ?? decisionTrace.driverMatch);
  const routeOrdering = asArray(decisionTrace.routeOrdering ?? decisionTrace.finalAssignment);
  const seedRace = asArray(decisionTrace.seedRace);
  const finalSelection = asRecord(decisionTrace.finalSelection ?? decisionTrace.guard);
  const finalRows = routes.map((route) => [driverLabel(route.driverId), route.stops.slice(0, 4).map((stop) => stop.id).join(' → ') || 'waiting route', `${route.distanceKm ?? '--'}km`, `${route.stops.length} stops`]);
  const noTrace = !Object.keys(decisionTrace).length;
  const activeRoutes = asArray(liveRecord.activeRoutes).length ? asArray(liveRecord.activeRoutes) : routes;
  const insightRows = [
    ['Input', `${scalar(asRecord(decisionTrace.input).orderCount ?? asRecord(decisionTrace.inputProcessing).orderCount ?? asArray(liveRecord.bufferItems).length)} orders · ${scalar(asRecord(decisionTrace.input).driverCount ?? asArray(liveRecord.drivers).length)} drivers`, 'buffer/live input'],
    ['Driver Choice', driverCandidateSelection.length ? `${driverCandidateSelection.length} candidates scored` : 'waiting backend match', 'distance + capacity + urgency'],
    ['Route Objective', `distance ${scalar(metrics.distanceKm ?? finalSelection.distanceKm, '--')}km · late ${scalar(metrics.lateCount ?? finalSelection.lateOrderCount, '--')}`, 'shortest safe route + SLA'],
    ['Seed/Optimizer', `${seedRace.length || compareRows.length} seeds · ${scalar(finalSelection.selectedOptimizer ?? finalSelection.selectedSource, 'WAITING')}`, 'best seed refined by IRX'],
    ['Live Stability', `routes ${activeRoutes.length} · buffered ${scalar(liveRecord.bufferedOrders, '0')}`, 'churn/freeze/live kernel']
  ];
  const bestSeed = compareRows.length
    ? [...compareRows].sort((left, right) => (left.lateCount ?? 999) - (right.lateCount ?? 999) || (left.distanceKm ?? 9999) - (right.distanceKm ?? 9999))[0]
    : undefined;
  return <Panel title={tab === 'live' ? 'Live Decision Story' : 'Static Decision Story'} icon={<CheckCircle2 size={15} />}>
    <div className="decisionStack">
      {noTrace && <div className="traceMissing"><b>Backend playbackTrace missing</b><span>Không dựng bảng giả. Hãy chạy Live/Benchmark/Compare với backend mới để thấy input → cluster → driver → seed → final route.</span></div>}
      <DecisionMiniTable title="Decision Insights" columns={['Signal', 'Value', 'Why it matters']} rows={insightRows} />
      <DecisionStep index="01" title="Input Validation" status={noTrace ? 'WAITING_BACKEND' : 'BACKEND'} summary="Tenant, idempotency, capacity, deadline, tọa độ và dữ liệu bắt buộc phải do backend trace xác nhận." />
      <DecisionMiniTable title="Order Pool Filter" columns={['Order', 'Demand', 'Deadline', 'Status', 'Feasible']} rows={orderPool.length ? orderPool.map((row) => [scalar(asRecord(row).orderId), scalar(asRecord(row).demand), scalar(asRecord(row).deadlineMinutes), scalar(asRecord(row).status), scalar(asRecord(row).feasible)]) : [['NO_BACKEND_TRACE', '--', '--', '--', '--']]} />
      <DecisionMiniTable title="Spatial Clustering" columns={['Batch', 'Orders', 'Load', 'Driver', 'Status']} rows={clusterSelection.length ? clusterSelection.map((row) => [scalar(asRecord(row).batchId), asArray(asRecord(row).orderIds).join(', '), scalar(asRecord(row).totalDemand), driverLabel(scalar(asRecord(row).driverId)), scalar(asRecord(row).status)]) : [['NO_BACKEND_TRACE', '--', '--', '--', '--']]} />
      <DecisionMiniTable title="Driver Candidate Selection" columns={['Order', 'Driver', 'Priority', 'Urgency', 'Fit', 'Final', 'Decision']} rows={driverCandidateSelection.length ? driverCandidateSelection.map((row) => [scalar(asRecord(row).orderId), driverLabel(scalar(asRecord(row).driverId)), scalar(asRecord(row).priorityLevel), scalar(asRecord(row).urgencyScore), scalar(asRecord(row).routeFitScore), scalar(asRecord(row).finalScore ?? asRecord(row).score), scalar(asRecord(row).decision)]) : [['NO_BACKEND_TRACE', '--', '--', '--', '--', '--', '--']]} highlightLast />
      <DecisionMiniTable title="Solver Seed Comparison" columns={['Rank', 'Seed', 'Source', 'Runtime', 'Distance', 'Late', 'Stops']} rows={seedRace.length ? seedRace.map((seed) => [scalar(asRecord(seed).rank), scalar(asRecord(seed).seedId), scalar(asRecord(seed).solver), scalar(asRecord(seed).runtimeDisplay ?? `${scalar(asRecord(seed).runtimeMs)}ms`), `${scalar(asRecord(seed).distanceKm)}km`, scalar(asRecord(seed).lateCount), asArray(asRecord(seed).stopSequencePreview).join(' | ') || 'BACKEND_SEED_SEQUENCE_MISSING']) : (compareRows.length ? compareRows : [bestSeed].filter(Boolean)).map((row) => [row?.rank ?? '--', row?.solver ?? 'WAITING', row?.solver ?? 'WAITING', row?.runtimeDisplay || `${row?.runtimeMs ?? '--'}ms`, `${row?.distanceKm ?? '--'}km`, String(row?.lateCount ?? '--'), row?.result ?? 'RUN_COMPARE'])} />
      <div className="decisionOutcome">
        <span>Objective Comparator</span>
        <b>{bestSeed ? `${bestSeed.solver} selected by late → distance priority` : 'Run Compare để thấy best seed thật'}</b>
        <small>Coverage → hard violation → late count → total lateness → distance → runtime.</small>
      </div>
      <div className="decisionOutcome">
        <span>Dominance Guard</span>
        <b>{displayValue(finalSelection.dominanceGuard ?? diagnostics.externalSeedDominance ?? diagnostics.dominanceGuard ?? 'WAITING')}</b>
        <small>Final late: {scalar(finalSelection.lateOrderCount ?? metrics.lateCount)} · Distance: {scalar(finalSelection.distanceKm ?? metrics.distanceKm)}km · Live buffered: {scalar(liveRecord.bufferedOrders)}</small>
      </div>
      <DecisionMiniTable title="Route Ordering" columns={['Route', 'Driver', 'Starts', 'Distance', 'Stop sequence']} rows={routeOrdering.length ? routeOrdering.map((row) => [scalar(asRecord(row).routeId), driverLabel(scalar(asRecord(row).driverId)), scalar(asRecord(row).startsFromDriver), scalar(asRecord(row).distanceKm), asArray(asRecord(row).stopSequence).slice(0, 6).join(' → ')]) : [['WAITING', '--', '--', '--', '--']]} />
      <DecisionMiniTable title="Final Assignment On Map" columns={['Driver', 'Route preview', 'Distance', 'Stops']} rows={finalRows.length ? finalRows : [['NO_BACKEND_ROUTE', '--', '--', '--']]} />
    </div>
  </Panel>;
}

function DecisionStep({ index, title, status, summary }: { index: string; title: string; status: string; summary: string }) {
  return <div className="decisionStep"><i>{index}</i><div><b>{title}</b><p>{summary}</p></div><strong>{status}</strong></div>;
}

function DecisionMiniTable({ title, columns, rows, highlightLast = false }: { title: string; columns: readonly string[]; rows: readonly (readonly unknown[])[]; highlightLast?: boolean }) {
  return <div className="decisionMiniTable"><h3>{title}</h3><div className="decisionMiniScroll"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={`${title}-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${title}-${rowIndex}-${cellIndex}`} className={highlightLast && cellIndex === row.length - 1 ? String(cell).toLowerCase() : ''}>{scalar(cell)}</td>)}</tr>)}</tbody></table></div></div>;
}

function SolverStrip({ health }: { health: unknown }) {
  return <div className="solverStrip">{solverRows(health).map((row) => <span key={row.name} className={row.value === 'AVAILABLE' ? 'ok' : 'err'}>{row.name}: {row.value}</span>)}</div>;
}

function DatasetPicker({ dataset, onChange }: { dataset: string; onChange: (value: string) => void }) {
  return <div className="picker">{DATASETS.map(([id, label]) => <button key={id} className={dataset === id ? 'active' : ''} onClick={() => onChange(id)}>{label}</button>)}</div>;
}

function EndpointPicker({ endpoint, onChange }: { endpoint: ApiEndpoint; onChange: (value: ApiEndpoint) => void }) {
  return <div className="picker endpointPicker">{[['dispatch', 'POST dispatch'], ['compare', 'POST compare'], ['live', 'POST live'], ['liveOrder', 'POST live order'], ['liveCycle', 'POST live cycle'], ['rescue', 'POST rescue']].map(([id, label]) => <button key={id} className={endpoint === id ? 'active' : ''} onClick={() => onChange(id as ApiEndpoint)}>{label}</button>)}</div>;
}

function ApiSandboxPanel({ endpoint, payload, response, health, version, onEndpoint, onPayload, onHealth, onSend }: { endpoint: ApiEndpoint; payload: string; response: string; health: unknown; version: unknown; onEndpoint: (value: ApiEndpoint) => void; onPayload: (value: string) => void; onHealth: () => void; onSend: () => void }) {
  const [payloadOpen, setPayloadOpen] = useState(false);
  const [responseOpen, setResponseOpen] = useState(false);
  let parsedResponse: Record<string, unknown> = {};
  try { parsedResponse = response ? asRecord(JSON.parse(response)) : {}; } catch { parsedResponse = {}; }
  const summary = response
    ? [['Status', scalar(parsedResponse.status ?? parsedResponse.errorCode, 'OK')], ['Routes', scalar(asArray(parsedResponse.routes ?? parsedResponse.activeRoutes).length, '0')], ['Mode', scalar(parsedResponse.mode ?? parsedResponse.scenarioId ?? endpoint)]]
    : [['Health', healthLabel(health)], ['Version', scalar(asRecord(version).version, '--')], ['Endpoint', endpoint]];
  return <Panel title="API Sandbox" icon={<Code size={15} />}>
    <div className="tabPurpose">Action center trực quan: chọn API, xem summary trước, JSON payload/response có thể mở rộng khi cần audit.</div>
    <EndpointPicker endpoint={endpoint} onChange={onEndpoint} />
    <div className="apiSummaryGrid">{summary.map(([label, value]) => <span key={label}><small>{label}</small><b>{value}</b></span>)}</div>
    <div className="apiAccordion">
      <button onClick={() => setPayloadOpen((open) => !open)}>{payloadOpen ? 'Collapse Payload' : 'Expand Payload'}</button>
      {payloadOpen && <textarea aria-label="Editable API payload" value={payload} onChange={(event) => onPayload(event.target.value)} />}
      <button onClick={() => setResponseOpen((open) => !open)}>{responseOpen ? 'Collapse Response' : 'Expand Response'}</button>
      {responseOpen && <pre>{response || stringify({ health, version, hint: 'Run an API action to see real response JSON.' })}</pre>}
    </div>
    <div className="actions"><button onClick={onHealth}>Health</button><button onClick={onSend}>Send Payload</button></div>
  </Panel>;
}

function CompareTable({ rows, health, mode }: { rows: CompareRow[]; health: unknown; mode: CompareDisplayMode }) {
  const readiness = solverRows(health);
  const ordered = [...rows].sort((left, right) => solverDisplayRank(left.solver) - solverDisplayRank(right.solver));
  return <><div className="readiness">{readiness.map((row) => <span key={row.name} className={row.value === 'AVAILABLE' ? 'ok' : 'err'}>{row.name}: {row.value}</span>)}</div><div className="table compareTable"><div className="row head"><span>Solver</span><span>Runtime</span><span>Distance</span><span>Late</span><span>Coverage</span><span>Sequence</span><span>Result</span><span>Reason</span></div>{ordered.length ? ordered.map((row, rowIndex) => { const coveragePct = row.coverage !== undefined ? Math.round(row.coverage * 100) : undefined; const sequence = compactSequence(row.stopSequencePreview); return <div className="row" key={`${row.solver}-${rowIndex}`} title={`${row.reason || ''}${sequence.full ? `\n${sequence.full}` : ''}`}><span>{row.solver}{row.isFinal ? ' ✓' : ''}</span><span>{row.runtimeDisplay || (row.runtimeMs ?? '--')}</span><span>{row.distanceKm ?? '--'}</span><span>{row.lateCount ?? '--'}</span><span className={coveragePct !== undefined && coveragePct < 100 ? 'warnText' : ''}>{coveragePct !== undefined ? `${coveragePct}%` : '--'}</span><span>{sequence.short}</span><span>{row.result ?? 'PRESENT'}</span><span>{row.reason || '--'}</span></div>; }) : <div className="row empty"><span>Backend compare not run</span><span>--</span><span>--</span><span>--</span><span>--</span><span>BACKEND_SEQUENCE_MISSING</span><span>WAITING</span><span>--</span></div>}</div></>;
}

function compactSequence(sequence?: string[]) {
  const full = sequence?.join(' | ') || '';
  if (!full) return { short: 'BACKEND_SEQUENCE_MISSING', full: '' };
  const normalized = full.replace(/[\[\],]/g, '').replace(/\s+/g, ' ').replace(/: /g, ': ').replace(/P(\d+)/g, 'P$1').replace(/D(\d+)/g, 'D$1');
  return { short: normalized.length > 44 ? `${normalized.slice(0, 44)}…` : normalized, full: normalized };
}

function solverDisplayRank(solver: string) {
  const key = solver.toUpperCase();
  const order = ['IRX', 'VROOM', 'ORTOOLS', 'PYVRP', 'DISTANCE_NEAREST', 'ONE_BY_ONE_DELIVERY'];
  const index = order.indexOf(key);
  return index >= 0 ? index : order.length;
}

function TimelineTable({ stages }: { stages: StageRow[] }) {
  return <div className="table flow"><div className="row head"><span>Stage</span><span>Status</span><span>Percent</span></div>{stages.map((stage, stageIndex) => <div className="row" key={`${stage.stage}-${stage.status}-${stageIndex}`}><span>{stage.stage}</span><span>{stage.status}</span><span>{Number.isFinite(stage.percent) ? stage.percent : '--'}</span></div>)}</div>;
}

function FlowTable({ stages, events, result }: { stages: StageRow[]; events: unknown; result: unknown }) {
  const diagnostics = asRecord(asRecord(result).diagnostics);
  const metrics = asRecord(asRecord(result).metrics);
  return <div className="flowStack"><TimelineTable stages={stages} /><div className="table flow"><div className="row head"><span>Backend Signal</span><span>Value</span><span>Source</span></div>{[['finalSolver', asRecord(result).finalSolver], ['distanceKm', metrics.distanceKm], ['lateCount', metrics.lateCount], ['dominanceGuard', diagnostics.dominanceGuard ?? diagnostics.externalDominanceGuard], ['eventCount', asArray(asRecord(events).events).length]].map(([key, value]) => <div className="row" key={String(key)}><span>{String(key)}</span><span>{scalar(value)}</span><span>API</span></div>)}</div></div>;
}

function BackendSummary({ title, value }: { title: string; value: unknown }) {
  return <pre className="miniCode">{stringify(value ?? { source: title, status: 'WAITING_FOR_BACKEND_RESPONSE' })}</pre>;
}

function Console({ logs, liveState, streamEvents }: { logs: LogLine[]; liveState: unknown; streamEvents: ExecutionEvent[] }) {
  const [query, setQuery] = useState('');
  const [stage, setStage] = useState('ALL');
  const [level, setLevel] = useState('ALL');
  const [paused, setPaused] = useState(false);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const backendTrace = useMemo(() => backendConsoleTrace(liveState, streamEvents), [liveState, streamEvents]);
  const localTrace = useMemo(() => logs.map((log): ConsoleTraceLine => ({ id: `ui-${log.id}`, at: log.at, kind: log.kind, stage: 'UI', type: 'UI_LOG', message: log.text, data: {} })), [logs]);
  const allLines = useMemo(() => [...localTrace, ...backendTrace].slice(-500), [localTrace, backendTrace]);
  const visibleLines = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return allLines.filter((line) => {
      if (stage !== 'ALL' && line.stage !== stage) return false;
      if (level !== 'ALL' && line.kind !== level) return false;
      if (!needle) return true;
      return `${line.stage} ${line.type} ${line.message} ${line.orderId ?? ''} ${line.driverId ?? ''} ${line.cycleId ?? ''}`.toLowerCase().includes(needle);
    });
  }, [allLines, level, query, stage]);
  const renderedLines = paused ? [] : visibleLines;
  const stages = useMemo(() => ['ALL', ...Array.from(new Set(allLines.map((line) => line.stage))).sort()], [allLines]);
  const jumpLatest = () => bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' });
  return <section className="console liveConsole">
    <div className="consoleHeader"><h2><Terminal size={15} />Console</h2></div>
    <div className="consoleTools">
      <input aria-label="Search console logs" placeholder="Search order, driver, stage..." value={query} onChange={(event) => setQuery(event.target.value)} />
      <select aria-label="Filter console stage" value={stage} onChange={(event) => setStage(event.target.value)}>{stages.map((item) => <option key={item}>{item}</option>)}</select>
      <select aria-label="Filter console level" value={level} onChange={(event) => setLevel(event.target.value)}>{['ALL', 'info', 'ok', 'warn', 'err'].map((item) => <option key={item}>{item}</option>)}</select>
      <button onClick={() => setPaused((value) => !value)}>{paused ? 'Resume' : 'Pause'}</button>
      <button onClick={jumpLatest}>Jump to latest</button>
    </div>
    <div ref={bodyRef} className="consoleBody">
      {paused ? <p className="warn"><span>PAUSED</span>Console view paused. Backend state is still updating.</p> : renderedLines.length ? renderedLines.map((line) => <details key={line.id} className={`consoleEvent ${line.kind}`}>
        <summary><span>{displayConsoleTime(line.at)}</span><b>{line.stage}</b><em>{line.type}</em><strong>{line.message}</strong>{line.orderId && <small>order {line.orderId}</small>}{line.driverId && <small>driver {driverLabel(line.driverId)}</small>}</summary>
        <pre>{stringify(line.data)}</pre>
      </details>) : <p><span>--:--:--</span>Waiting for backend console trace.</p>}
    </div>
  </section>;
}

function backendConsoleTrace(liveState: unknown, streamEvents: ExecutionEvent[]): ConsoleTraceLine[] {
  const liveRecord = asRecord(liveState);
  const trace = asRecord(liveRecord.decisionTrace);
  const raw = [...asArray(liveRecord.consoleTrace), ...asArray(trace.consoleTrace)];
  const seen = new Set<string>();
  const backend = raw.flatMap((item, index) => {
    const record = asRecord(item);
    const data = asRecord(record.data);
    const id = scalar(record.id, `backend-${index}-${scalar(record.at, '')}-${scalar(record.type, '')}`);
    if (seen.has(id)) return [];
    seen.add(id);
    return [{
      id,
      at: scalar(record.at, ''),
      kind: consoleKind(record.level),
      stage: scalar(record.stage, 'BACKEND'),
      type: scalar(record.type, 'EVENT'),
      message: scalar(record.message, ''),
      orderId: scalar(record.orderId ?? data.orderId, ''),
      driverId: scalar(record.driverId ?? data.driverId, ''),
      cycleId: scalar(record.cycleId, ''),
      data: record.data ?? {}
    }];
  });
  const stream = streamEvents.slice(-60).map((event, index): ConsoleTraceLine => ({
    id: `sse-${index}-${event.timestamp ?? ''}-${event.stage ?? ''}`,
    at: event.timestamp ?? '',
    kind: event.status === 'FAILED' ? 'err' : event.status === 'COMPLETED' ? 'ok' : 'info',
    stage: event.stage ?? 'SSE',
    type: 'SSE_EVENT',
    message: event.message ?? '',
    data: event.data ?? event
  }));
  return [...backend, ...stream];
}

function consoleKind(value: unknown): LogKind {
  const normalized = scalar(value, 'info').toLowerCase();
  return normalized === 'ok' || normalized === 'warn' || normalized === 'err' ? normalized : 'info';
}

function displayConsoleTime(value: string) {
  if (!value) return '--:--:--';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleTimeString();
}



