import type { LiveCycleResponse, LiveOrderData, LiveOrderState, LiveState, Point } from './LiveDispatchDemoPage';

export type LiveMapPointKind = 'DRIVER' | 'PICKUP' | 'DROPOFF';
export type LiveMapPoint = {
  id: string;
  kind: LiveMapPointKind;
  label: string;
  lat: number;
  lng: number;
  orderId?: string;
  driverId?: string;
  status?: string;
  risk?: 'LOW' | 'MEDIUM' | 'HIGH';
  frozen?: boolean;
  mlTouched?: boolean;
  routefinderCandidate?: boolean;
  accepted?: boolean;
  gainKm?: number;
};
export type LiveMapRoute = { id: string; driverId: string; points: LiveMapPoint[]; previous?: boolean; mlTouched?: boolean; frozen?: boolean };
export type LiveMapModel = {
  drivers: LiveMapPoint[];
  pickups: LiveMapPoint[];
  dropoffs: LiveMapPoint[];
  routes: LiveMapRoute[];
  previousRoutes: LiveMapRoute[];
  warnings: string[];
  summary: { drivers: number; orders: number; routes: number; frozenStops: number; highRiskOrders: number };
};

export function toLiveMapModel(state: LiveState, previousState: LiveState | null, lastCycle: LiveCycleResponse | null): LiveMapModel {
  const warnings: string[] = [];
  const orderById = new Map(state.orders.map((entry) => [entry.order.orderId, entry]));
  const frozen = new Set(state.frozenStopIds ?? []);
  const drivers: LiveMapPoint[] = state.drivers.map((driver) => ({ id: `driver:${driver.driverId}`, kind: 'DRIVER', label: driver.driverId, lat: driver.lat, lng: driver.lng, driverId: driver.driverId, status: driver.status, mlTouched: driver.status === 'DELAYED' }));
  const pickups = state.orders.flatMap((entry) => pointForOrder(entry, 'PICKUP', frozen, lastCycle));
  const dropoffs = state.orders.flatMap((entry) => pointForOrder(entry, 'DROPOFF', frozen, lastCycle));
  const routes = state.routes.map((route) => routeFromStops(route.routeId, route.driverId, route.stopIds, orderById, frozen, false, lastCycle)).filter((route): route is LiveMapRoute => Boolean(route));
  const previousRoutes = (previousState?.routes ?? []).map((route) => routeFromStops(`before:${route.routeId}`, route.driverId, route.stopIds, new Map((previousState?.orders ?? []).map((entry) => [entry.order.orderId, entry])), new Set(previousState?.frozenStopIds ?? []), true, lastCycle)).filter((route): route is LiveMapRoute => Boolean(route));
  if (!drivers.length) warnings.push('No driver telemetry yet. Click Move Drivers.');
  if (!pickups.length && !dropoffs.length) warnings.push('No live orders yet. Add a random order or burst.');
  return { drivers, pickups, dropoffs, routes, previousRoutes, warnings, summary: { drivers: drivers.length, orders: state.orders.length, routes: routes.length, frozenStops: frozen.size, highRiskOrders: state.orders.filter((entry) => riskFor(entry.order, entry.status) === 'HIGH').length } };
}

function pointForOrder(entry: LiveOrderState, type: 'PICKUP' | 'DROPOFF', frozen: Set<string>, lastCycle: LiveCycleResponse | null): LiveMapPoint[] {
  const point = pointFor(type, entry.order);
  if (!point) return [];
  const stopId = `${type}:${entry.order.orderId}`;
  return [{ id: stopId, kind: type, label: `${type === 'PICKUP' ? 'P' : 'D'} ${entry.order.orderId}`, lat: point.lat, lng: point.lng, orderId: entry.order.orderId, status: entry.status, risk: riskFor(entry.order, entry.status), frozen: frozen.has(stopId), mlTouched: Boolean(lastCycle?.triModelRepairUsed), routefinderCandidate: Boolean(lastCycle?.diagnostics.routefinderCandidateCount), accepted: entry.status === 'ASSIGNED', gainKm: Number(lastCycle?.diagnostics.gainKm ?? 0) }];
}

function routeFromStops(id: string, driverId: string, stopIds: string[], orders: Map<string, LiveOrderState>, frozen: Set<string>, previous: boolean, lastCycle: LiveCycleResponse | null): LiveMapRoute | null {
  const points = stopIds.map((stopId) => pointForStop(stopId, orders, frozen, lastCycle)).filter((point): point is LiveMapPoint => Boolean(point));
  if (points.length < 2) return null;
  return { id, driverId, points, previous, mlTouched: Boolean(lastCycle?.triModelRepairUsed), frozen: points.some((point) => point.frozen) };
}

function pointForStop(stopId: string, orders: Map<string, LiveOrderState>, frozen: Set<string>, lastCycle: LiveCycleResponse | null): LiveMapPoint | null {
  const [type, orderId] = stopId.split(':');
  const entry = orders.get(orderId);
  if (!entry || (type !== 'PICKUP' && type !== 'DROPOFF')) return null;
  return pointForOrder(entry, type, frozen, lastCycle)[0] ?? null;
}

function pointFor(type: 'PICKUP' | 'DROPOFF', order: LiveOrderData): Point | null {
  if (type === 'PICKUP') return fromPoint(order.pickup, order.pickupLat, order.pickupLng);
  return fromPoint(order.dropoff, order.dropoffLat, order.dropoffLng);
}

function fromPoint(point?: Point, lat?: number, lng?: number): Point | null {
  const nextLat = point?.lat ?? lat;
  const nextLng = point?.lng ?? lng;
  return typeof nextLat === 'number' && typeof nextLng === 'number' ? { lat: nextLat, lng: nextLng } : null;
}

function riskFor(order: LiveOrderData, status: string): 'LOW' | 'MEDIUM' | 'HIGH' {
  if (order.priority === 'HIGH' || order.priority === 10) return 'HIGH';
  if (status === 'BUFFERED') return 'MEDIUM';
  return 'LOW';
}

