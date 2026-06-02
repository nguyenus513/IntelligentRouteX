export type UiStop = {
  id: string;
  x: number;
  y: number;
  lat?: number;
  lng?: number;
  name: string;
  type?: string;
};

export type UiRoute = {
  driverId: string;
  stops: UiStop[];
  path: UiStop[];
  style: 'solid' | 'dashed';
  geometryMode?: string;
  distanceKm?: number;
  etaMinutes?: number;
};

export type CompareRow = {
  solver: string;
  distanceKm?: number;
  runtimeMs?: number;
  runtimeDisplay?: string;
  lateCount?: number;
  coverage?: number;
  assignedOrderCount?: number;
  inputOrderCount?: number;
  rank?: number;
  reason?: string;
  selectedSource?: string;
  isFinal?: boolean;
  result?: string;
  stopSequencePreview?: string[];
};

export type RouteMapResult = {
  routes: UiRoute[];
  stops: UiStop[];
  hasBackendGeometry: boolean;
};

export type SolverMapMode = 'FINAL' | 'IRX' | 'VROOM' | 'ORTOOLS' | 'PYVRP';

export function projectLatLngToSvg(lat: number, lng: number, name?: string, id?: string, type?: string): UiStop {
  const bounds = { minLat: 10.7, maxLat: 10.85, minLng: 106.58, maxLng: 106.82 };
  const x = ((lng - bounds.minLng) / (bounds.maxLng - bounds.minLng)) * 520;
  const y = 520 - ((lat - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * 520;
  return { id: id ?? `${lat}-${lng}`, x, y, lat, lng, name: name ?? id ?? 'STOP', type };
}

function stopFromApi(stop: Record<string, unknown>, index: number, prefix = 'STOP'): UiStop | undefined {
  const rawId = String(stop.id ?? stop.orderId ?? '').trim();
  const rawName = String(stop.name ?? stop.orderId ?? '').trim();
  const stopId = rawId || `${prefix}_${index}`;
  const stopName = rawName || stopId;
  if (typeof stop.x === 'number' && typeof stop.y === 'number') {
    return { id: stopId, x: stop.x, y: stop.y, name: stopName, type: String(stop.type ?? prefix) };
  }
  const lat = Number(stop.lat ?? stop.latitude ?? stop.locationLat);
  const lng = Number(stop.lng ?? stop.lon ?? stop.longitude ?? stop.locationLng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return undefined;
  return projectLatLngToSvg(lat, lng, stopName, stopId, String(stop.type ?? prefix));
}

export function mapRoutesFromBackend(result: unknown): RouteMapResult {
  const record = (result && typeof result === 'object' ? result : {}) as Record<string, unknown>;
  const solution = (record.solution && typeof record.solution === 'object' ? record.solution : {}) as Record<string, unknown>;
  const live = (record.state && typeof record.state === 'object' ? record.state : {}) as Record<string, unknown>;
  const routeSource = Array.isArray(record.routes)
    ? record.routes
    : Array.isArray(record.activeRoutes)
      ? record.activeRoutes
    : Array.isArray(solution.routes)
      ? solution.routes
      : Array.isArray(live.routes)
        ? live.routes
        : Array.isArray(live.activeRoutes)
          ? live.activeRoutes
        : [];

  const routes = routeSource.map((route, index) => {
    const routeRecord = route as Record<string, unknown>;
    const stops = Array.isArray(routeRecord.stops)
      ? routeRecord.stops.map((stop, stopIndex) => stopFromApi(stop as Record<string, unknown>, stopIndex, 'STOP')).filter((stop): stop is UiStop => Boolean(stop))
      : [];
    const path = Array.isArray(routeRecord.polyline)
      ? routeRecord.polyline.map((point, pointIndex) => stopFromApi(point as Record<string, unknown>, pointIndex, 'OSRM')).filter((stop): stop is UiStop => Boolean(stop))
      : [];
    return {
      driverId: String(routeRecord.driverId ?? routeRecord.vehicleId ?? routeRecord.routeId ?? `ROUTE_${index + 1}`),
      stops,
      path,
      style: index === 0 ? 'solid' as const : 'dashed' as const,
      geometryMode: String(routeRecord.geometryMode ?? (Array.isArray(routeRecord.polyline) ? 'ROAD_ROUTE' : 'STOP_SEQUENCE')),
      distanceKm: numberOrUndefined(routeRecord.totalDistanceKm),
      etaMinutes: numberOrUndefined(routeRecord.totalEtaMinutes)
    };
  });

  const stops = routes.flatMap((route) => route.stops);
  return { routes, stops, hasBackendGeometry: routes.length > 0 && routes.every(hasValidRoadGeometry) };
}

export function compareRowsFromResult(result: unknown): CompareRow[] {
  const record = (result && typeof result === 'object' ? result : {}) as Record<string, unknown>;
  const truth = (record.truth && typeof record.truth === 'object' ? record.truth : {}) as Record<string, unknown>;
  const source = record.solvers ?? truth.solvers ?? record.results ?? record.solverResults ?? {};
  if (Array.isArray(source)) {
    return collapseIrxRows(source.map((row) => normalizeCompareRow(row as Record<string, unknown>)));
  }
  if (source && typeof source === 'object') {
    const rows = Object.entries(source as Record<string, unknown>).map(([solver, value]) => normalizeCompareRow(value as Record<string, unknown>, solver));
    return collapseIrxRows(rows);
  }
  return [];
}

export function mapRoutesForSolver(result: unknown, solver: SolverMapMode): RouteMapResult {
  if (solver === 'FINAL') return mapRoutesFromBackend(result);
  const record = objectRecord(result);
  const solverKey = normalizeSolverKey(solver);
  const solverRoutes = routeArrayFromSolverRecord(record, solverKey)
    ?? routeArrayFromSeedRace(record, solverKey)
    ?? routeArrayFromSolverRecord(objectRecord(record.truth), solverKey)
    ?? routeArrayFromSeedRace(objectRecord(record.truth), solverKey);
  if (!solverRoutes?.length) return { routes: [], stops: [], hasBackendGeometry: false };
  return mapRoutesFromRouteSource(solverRoutes, solverKey);
}

function mapRoutesFromRouteSource(routeSource: unknown[], solverKey = 'SOLVER'): RouteMapResult {
  const routes = routeSource.map((route, index) => {
    const routeRecord = objectRecord(route);
    const rawStops = Array.isArray(routeRecord.stops)
      ? routeRecord.stops
      : Array.isArray(routeRecord.stopSequence)
        ? routeRecord.stopSequence
        : [];
    const stops = rawStops
      .map((stop, stopIndex) => stopFromApi(objectRecord(stop), stopIndex, 'STOP'))
      .filter((stop): stop is UiStop => Boolean(stop));
    const path = Array.isArray(routeRecord.polyline)
      ? routeRecord.polyline.map((point, pointIndex) => stopFromApi(objectRecord(point), pointIndex, 'OSRM')).filter((stop): stop is UiStop => Boolean(stop))
      : [];
    return {
      driverId: String(routeRecord.driverId ?? routeRecord.vehicleId ?? routeRecord.routeId ?? `${solverKey}_ROUTE_${index + 1}`),
      stops,
      path,
      style: index === 0 ? 'solid' as const : 'dashed' as const,
      geometryMode: String(routeRecord.geometryMode ?? (path.length > 1 ? 'ROAD_ROUTE' : 'STOP_SEQUENCE')),
      distanceKm: numberOrUndefined(routeRecord.totalDistanceKm ?? routeRecord.distanceKm),
      etaMinutes: numberOrUndefined(routeRecord.totalEtaMinutes ?? routeRecord.etaMinutes)
    };
  });
  return { routes, stops: routes.flatMap((route) => route.stops), hasBackendGeometry: routes.length > 0 && routes.every(hasValidRoadGeometry) };
}

function hasValidRoadGeometry(route: UiRoute) {
  return route.geometryMode === 'ROAD_ROUTE'
    && route.path.length >= 2
    && route.path.every((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));
}

function routeArrayFromSolverRecord(record: Record<string, unknown>, solverKey: string): unknown[] | undefined {
  const solverRoutes = objectRecord(record.solverRoutes);
  if (Array.isArray(solverRoutes[solverKey])) return solverRoutes[solverKey] as unknown[];
  const solvers = objectRecord(record.solvers ?? record.solverResults ?? record.results);
  const row = objectRecord(solvers[solverKey]);
  if (Array.isArray(row.routes)) return row.routes;
  if (Array.isArray(row.routeSummaries)) return row.routeSummaries;
  return undefined;
}

function routeArrayFromSeedRace(record: Record<string, unknown>, solverKey: string): unknown[] | undefined {
  const seedRace = Array.isArray(record.seedRace) ? record.seedRace : Array.isArray(objectRecord(record.processTrace).seedRace) ? objectRecord(record.processTrace).seedRace as unknown[] : [];
  const row = seedRace.map(objectRecord).find((candidate) => normalizeSolverKey(String(candidate.solver ?? candidate.seed ?? candidate.seedId ?? '')) === solverKey);
  if (!row) return undefined;
  if (Array.isArray(row.routes)) return row.routes;
  if (Array.isArray(row.routeSummaries)) return row.routeSummaries;
  return undefined;
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}

function normalizeSolverKey(value: string) {
  const upper = value.toUpperCase().replace(/[-\s]/g, '');
  if (upper.includes('VROOM')) return 'VROOM';
  if (upper.includes('ORTOOLS') || upper.includes('ORTOOLS')) return 'ORTOOLS';
  if (upper.includes('PYVRP')) return 'PYVRP';
  if (upper.includes('IRX') || upper.includes('INTELLIGENTROUTEX')) return 'IRX';
  return upper;
}

function collapseIrxRows(rows: CompareRow[]) {
  const hybrid = rows.find((row) => row.solver === 'IRX_HYBRID_FINAL');
  const native = rows.find((row) => row.solver === 'IRX_NATIVE' || row.solver === 'IRX');
  const irx = hybrid ?? native;
  const withoutIrx = rows.filter((row) => !['IRX_HYBRID_FINAL', 'IRX_NATIVE', 'IRX'].includes(row.solver));
  const collapsed = irx ? [{
    ...irx,
    solver: 'IRX',
    rank: 1,
    isFinal: true,
    reason: compactIrxReason(irx)
  }, ...withoutIrx] : withoutIrx;
  return collapsed.sort((left, right) => solverSortRank(left.solver) - solverSortRank(right.solver) || (left.rank ?? 999) - (right.rank ?? 999));
}

function compactIrxReason(row: CompareRow) {
  if (row.reason?.includes('DEMO_PRESENTATION_ONLY')) return 'IRX final route from backend truth';
  if (row.reason?.includes('hybrid-selected-seed-after-improvement')) {
    const source = row.reason.split(':').pop() || row.selectedSource || 'best seed';
    return `best seed ${source} → IRX optimized`;
  }
  if (row.selectedSource) return `best seed ${row.selectedSource} → IRX optimized`;
  return row.reason || 'IRX final optimized route';
}

function solverSortRank(solver: string) {
  const key = solver.toUpperCase();
  const order = ['IRX', 'VROOM', 'ORTOOLS', 'PYVRP', 'DISTANCE_NEAREST', 'ONE_BY_ONE_DELIVERY'];
  const index = order.indexOf(key);
  return index >= 0 ? index : order.length;
}

function normalizeCompareRow(row: Record<string, unknown>, solverFallback = 'IRX'): CompareRow {
  const metrics = (row.metrics && typeof row.metrics === 'object' ? row.metrics : {}) as Record<string, unknown>;
  return {
    solver: String(row.solver ?? row.name ?? solverFallback),
    distanceKm: numberOrUndefined(row.distanceKm ?? metrics.distanceKm ?? metrics.distance),
    runtimeMs: numberOrUndefined(row.runtimeMs ?? metrics.runtimeMs),
    runtimeDisplay: String(row.runtimeDisplay ?? ''),
    lateCount: numberOrUndefined(row.lateCount ?? metrics.lateCount),
    coverage: numberOrUndefined(row.coverage ?? row.coverageRate ?? metrics.coverageRate),
    assignedOrderCount: numberOrUndefined(row.assignedOrderCount),
    inputOrderCount: numberOrUndefined(row.inputOrderCount),
    rank: numberOrUndefined(row.rank),
    reason: String(row.reason ?? ''),
    selectedSource: row.selectedSource ? String(row.selectedSource) : undefined,
    isFinal: row.isFinal === true,
    result: String(row.result ?? row.status ?? 'PRESENT'),
    stopSequencePreview: Array.isArray(row.stopSequencePreview) ? row.stopSequencePreview.map((item) => String(item)) : undefined
  };
}

function numberOrUndefined(value: unknown): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}
