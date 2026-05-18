import type { PlaygroundSnapshot } from './playgroundTypes';

export type MapPointKind = 'DRIVER' | 'PICKUP' | 'DROPOFF' | 'DEPOT' | 'RESCUE';

export interface MapPoint {
  id: string;
  kind: MapPointKind;
  lat: number;
  lng: number;
  label: string;
  driverId?: string;
  orderId?: string;
  source?: string;
  status?: string;
}

export interface MapRoute {
  driverId: string;
  source: string;
  distanceKm?: number;
  lateCount?: number;
  points: MapPoint[];
}

export interface MapModel {
  points: MapPoint[];
  routes: MapRoute[];
  synthetic: boolean;
}

const colors = ['#22d3ee', '#34d399', '#f59e0b', '#f472b6', '#a78bfa'];

export function routeColor(driverId: string): string {
  const hash = [...driverId].reduce((total, char) => total + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

export function toMapModel(snapshot: PlaygroundSnapshot): MapModel {
  const routes = extractRoutes(snapshot);
  const points = routes.flatMap((route) => route.points);
  return { points, routes, synthetic: true };
}

function extractRoutes(snapshot: PlaygroundSnapshot): MapRoute[] {
  const source = snapshot.staticResult?.finalSolver ?? snapshot.mode;
  if (snapshot.batchItems?.items?.length) return fromBatch(snapshot, source);
  if (snapshot.mode === 'LIVE_ROLLING') return liveDemoRoute(snapshot);
  if (snapshot.mode === 'RESCUE') return rescueRoute(snapshot);
  return staticDemoRoutes(snapshot, source);
}

function staticDemoRoutes(snapshot: PlaygroundSnapshot, source: string): MapRoute[] {
  const assigned = snapshot.staticResult?.coverage?.assigned ?? snapshot.staticResult?.summary?.assignedOrders ?? 8;
  return [0, 1].map((routeIndex) => {
    const driverId = `D0${routeIndex + 1}`;
    const baseLat = 10.77 + routeIndex * 0.026;
    const baseLng = 106.68 + routeIndex * 0.018;
    const points: MapPoint[] = [
      point(`${driverId}-S`, 'DEPOT', baseLat, baseLng, 'S', driverId, undefined, 'Depot'),
      ...Array.from({ length: Math.max(2, Math.min(4, Math.ceil(assigned / 4))) }, (_, index) => point(`${driverId}-P${index + 1}`, 'PICKUP', baseLat + 0.008 + index * 0.006, baseLng + 0.014 + index * 0.006, `P${index + 1}`, driverId, `ORD-${routeIndex * 4 + index + 1}`, source)),
      ...Array.from({ length: Math.max(2, Math.min(4, Math.ceil(assigned / 4))) }, (_, index) => point(`${driverId}-G${index + 1}`, 'DROPOFF', baseLat + 0.038 - index * 0.005, baseLng + 0.044 + index * 0.005, `G${index + 1}`, driverId, `ORD-${routeIndex * 4 + index + 1}`, 'Adaptive ML sequenced'))
    ];
    return { driverId, source, distanceKm: snapshot.staticResult?.metrics?.distanceKm, lateCount: snapshot.staticResult?.metrics?.lateCount, points };
  });
}

function liveDemoRoute(snapshot: PlaygroundSnapshot): MapRoute[] {
  const driverId = 'D-LIVE-1';
  const assigned = snapshot.cycle?.assigned ?? 3;
  const points = [
    point('live-driver', 'DRIVER', 10.78, 106.7, 'DRV', driverId, undefined, 'Latest telemetry'),
    ...Array.from({ length: Math.max(2, assigned) }, (_, index) => point(`live-p-${index}`, 'PICKUP', 10.786 + index * 0.007, 106.704 + index * 0.006, `P${index + 1}`, driverId, `LIVE-${index + 1}`, 'LIVE_QUEUE')),
    ...Array.from({ length: Math.max(2, assigned) }, (_, index) => point(`live-g-${index}`, 'DROPOFF', 10.812 - index * 0.004, 106.728 + index * 0.005, `G${index + 1}`, driverId, `LIVE-${index + 1}`, 'Rolling cycle'))
  ];
  return [{ driverId, source: 'LIVE_ROLLING', lateCount: snapshot.cycle?.lateRegression, points }];
}

function rescueRoute(snapshot: PlaygroundSnapshot): MapRoute[] {
  const driverId = 'D-RESCUE';
  return [{
    driverId,
    source: 'RESCUE',
    lateCount: snapshot.rescue?.afterLate,
    points: [
      point('rescue-driver', 'DRIVER', 10.776, 106.692, 'DRV', driverId, undefined, 'Delayed driver'),
      point('rescue-problem', 'RESCUE', 10.795, 106.716, '!', driverId, 'ORD-001', 'Problem stop'),
      point('rescue-drop', 'DROPOFF', 10.823, 106.742, 'G', driverId, 'ORD-001', snapshot.rescue?.lateNotWorse ? 'lateNotWorse PASS' : 'Rescue pending')
    ]
  }];
}

function fromBatch(snapshot: PlaygroundSnapshot, source: string): MapRoute[] {
  const items = snapshot.batchItems?.items.slice(0, 10) ?? [];
  const points = [point('bd-depot', 'DEPOT', 10.762, 106.681, 'S', 'BD-QUEUE', undefined, 'Normalized batch')];
  items.forEach((item, index) => {
    const orderId = String(item.orderId ?? `BD-${index + 1}`);
    points.push(point(`bd-p-${index}`, 'PICKUP', 10.765 + index * 0.004, 106.69 + (index % 4) * 0.008, `P${index + 1}`, 'BD-QUEUE', orderId, 'Normalized'));
    points.push(point(`bd-g-${index}`, 'DROPOFF', 10.805 + index * 0.003, 106.718 + (index % 4) * 0.007, `G${index + 1}`, 'BD-QUEUE', orderId, 'Queued output'));
  });
  return [{ driverId: 'BD-QUEUE', source, points }];
}

function point(id: string, kind: MapPointKind, lat: number, lng: number, label: string, driverId?: string, orderId?: string, source?: string): MapPoint {
  return { id, kind, lat, lng, label, driverId, orderId, source, status: kind === 'RESCUE' ? 'risk' : 'active' };
}
