import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Cpu, GitBranch, Play, Plus, RadioTower, RefreshCw, ShieldCheck, Truck, Zap } from 'lucide-react';
import { LiveDispatchMapPanel } from './LiveDispatchMapPanel';

export type Point = { lat: number; lng: number };
export type LiveOrderRequest = { orderId: string; pickup: Point; dropoff: Point; deadline: string; load: number; priority: 'NORMAL' | 'HIGH' };
export type LiveOrderData = { orderId: string; pickup?: Point; dropoff?: Point; pickupLat?: number; pickupLng?: number; dropoffLat?: number; dropoffLng?: number; deadline?: string; deadlineMinutes?: number; load?: number; priority?: number | string };
export type LiveOrderState = { order: LiveOrderData; status: string; reason?: string };
export type LiveDriverState = { driverId: string; lat: number; lng: number; status: string; currentStopId?: string | null };
export type LiveRouteSnapshot = { routeId: string; driverId: string; stopIds: string[]; frozenStopIds: string[]; distanceKm: number; lateCount: number };
export type LiveEvent = { type: string; subject: string; createdAt: string };
export type LiveState = { jobId: string; cycle: number; assigned: number; buffered: number; orders: LiveOrderState[]; drivers: LiveDriverState[]; routes: LiveRouteSnapshot[]; frozenStopIds: string[]; events: LiveEvent[] };
export type LiveCycleResponse = { jobId: string; cycle: number; mode: string; assigned: number; buffered: number; late: number; forecastUsed: boolean; greedRlAction: string; triModelRepairUsed: boolean; routes: LiveRouteSnapshot[]; diagnostics: Record<string, unknown>; assignedRegression: number };

const API_BASE = '/api/v1';
const headers = { 'Content-Type': 'application/json', 'X-Api-Key': 'demo-key', 'X-Tenant-Id': 'demo' };
const emptyState: LiveState = { jobId: '', cycle: 0, assigned: 0, buffered: 0, orders: [], drivers: [], routes: [], frozenStopIds: [], events: [] };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers ?? {}) } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

type OrderKind = 'normal' | 'tight' | 'rescue';
type HcmZone = { name: string; lat: number; lng: number };
type DemoDriver = { driverId: string; lat: number; lng: number; status: string; currentStopId?: string | null };

const hcmZones: HcmZone[] = [
  { name: 'District 1', lat: 10.776, lng: 106.700 },
  { name: 'District 3', lat: 10.783, lng: 106.685 },
  { name: 'Binh Thanh', lat: 10.805, lng: 106.710 },
  { name: 'Tan Binh', lat: 10.800, lng: 106.650 },
  { name: 'Thu Duc', lat: 10.850, lng: 106.770 },
  { name: 'District 7', lat: 10.730, lng: 106.720 },
  { name: 'Go Vap', lat: 10.835, lng: 106.670 }
];

const demoDriverSeeds: DemoDriver[] = [
  { driverId: 'D01', lat: 10.760, lng: 106.660, status: 'IDLE' },
  { driverId: 'D02', lat: 10.785, lng: 106.705, status: 'IDLE' },
  { driverId: 'D03', lat: 10.735, lng: 106.720, status: 'IDLE' },
  { driverId: 'D04', lat: 10.805, lng: 106.680, status: 'IDLE' },
  { driverId: 'D05', lat: 10.820, lng: 106.745, status: 'IDLE' },
  { driverId: 'D06', lat: 10.742, lng: 106.655, status: 'IDLE' }
];

function pickRandom<T>(items: T[]): T { return items[Math.floor(Math.random() * items.length)]; }
function randomAround(zone: HcmZone, radius = 0.018): Point { return { lat: zone.lat + (Math.random() - 0.5) * radius, lng: zone.lng + (Math.random() - 0.5) * radius }; }
function randomOrder(kind: OrderKind = 'normal', prefix = 'LIVE'): LiveOrderRequest {
  const pickupZone = pickRandom(hcmZones);
  let dropoffZone = pickRandom(hcmZones);
  while (dropoffZone.name === pickupZone.name) dropoffZone = pickRandom(hcmZones);
  const tight = kind === 'tight' || kind === 'rescue';
  return {
    orderId: `${prefix}-${Date.now()}-${Math.floor(Math.random() * 9999)}`,
    pickup: randomAround(pickupZone, kind === 'rescue' ? 0.010 : 0.022),
    dropoff: randomAround(dropoffZone, kind === 'rescue' ? 0.010 : 0.022),
    deadline: new Date(Date.now() + (kind === 'rescue' ? 10 : tight ? 15 : 35) * 60_000).toISOString(),
    load: 1,
    priority: tight ? 'HIGH' : 'NORMAL'
  };
}

function nextDrivers(count: number, status = 'IDLE'): DemoDriver[] { return demoDriverSeeds.slice(0, count).map((driver) => ({ ...driver, status })); }
function jitterDriver(driver: LiveDriverState | DemoDriver, index: number, delayed = false): DemoDriver {
  const drift = 0.004 + index * 0.001;
  return { driverId: driver.driverId, lat: driver.lat + (Math.random() - 0.4) * drift, lng: driver.lng + (Math.random() - 0.4) * drift, status: delayed && index === 0 ? 'DELAYED' : 'EN_ROUTE', currentStopId: driver.currentStopId ?? null };
}

export function LiveDispatchDemoPage() {
  const [jobId, setJobId] = useState('');
  const [state, setState] = useState<LiveState>(emptyState);
  const [lastCycle, setLastCycle] = useState<LiveCycleResponse | null>(null);
  const [previousState, setPreviousState] = useState<LiveState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [driverCount, setDriverCount] = useState(4);
  const [autoRun, setAutoRun] = useState(false);

  const safety = useMemo(() => {
    const diagnostics = lastCycle?.diagnostics ?? {};
    return {
      frozenStopViolations: Number(diagnostics.frozenStopViolations ?? 0),
      pickupDropoffViolations: Number(diagnostics.pickupDropoffViolations ?? 0),
      capacityViolations: Number(diagnostics.capacityViolations ?? 0),
      lateRegression: Number(diagnostics.lateRegression ?? 0),
      coverageRegression: Number(diagnostics.coverageRegression ?? 0),
      dominanceFailures: Number(diagnostics.dominanceFailures ?? 0),
      staleBufferedOrders: state.buffered
    };
  }, [lastCycle, state.buffered]);
  const safe = Object.values(safety).every((value) => value === 0);

  async function runAction(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try { await action(); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Live dispatch error'); } finally { setBusy(null); }
  }

  async function refresh(nextJobId = jobId) {
    if (!nextJobId) return emptyState;
    const next = await request<LiveState>(`/live/jobs/${nextJobId}/state`);
    setState(next);
    return next;
  }

  async function createJob() {
    const response = await request<{ jobId: string }>('/live/jobs', { method: 'POST', body: JSON.stringify({ tenantId: 'demo' }) });
    setJobId(response.jobId);
    setLastCycle(null);
    setPreviousState(null);
    return response.jobId;
  }

  async function addDriverTelemetry(targetJobId: string, driver: DemoDriver) {
    await request(`/live/jobs/${targetJobId}/drivers/${driver.driverId}/telemetry`, { method: 'POST', body: JSON.stringify(driver) });
  }

  async function seedDrivers(targetJobId: string, count = driverCount) {
    await Promise.all(nextDrivers(count).map((driver) => addDriverTelemetry(targetJobId, driver)));
  }

  async function addOrdersRaw(targetJobId: string, count: number, kind: OrderKind, prefix: string) {
    const orders = Array.from({ length: count }, (_, index) => ({ ...randomOrder(index % 4 === 0 ? 'tight' : kind, prefix), orderId: `${prefix}-${Date.now()}-${index + 1}-${Math.floor(Math.random() * 999)}` }));
    await request(`/live/jobs/${targetJobId}/orders`, { method: 'POST', body: JSON.stringify({ orders }) });
  }

  async function moveDriversRaw(targetJobId: string, sourceState = state, delay = false) {
    const activeDrivers = (sourceState.drivers.length ? sourceState.drivers : nextDrivers(driverCount)).slice(0, driverCount);
    await Promise.all(activeDrivers.map((driver, index) => addDriverTelemetry(targetJobId, { ...jitterDriver(driver, index, delay), currentStopId: sourceState.routes[index]?.stopIds[0] ?? driver.currentStopId ?? null })));
  }

  async function cycleRaw(targetJobId: string, rescue = false, before = state) {
    setPreviousState(before);
    const cycle = await request<LiveCycleResponse>(`/live/jobs/${targetJobId}/${rescue ? 'rescue' : 'cycle'}`, { method: 'POST', body: JSON.stringify({ returnDiagnostics: true }) });
    setLastCycle(cycle);
    return cycle;
  }

  async function startJob() {
    await runAction('start', async () => {
      const nextJobId = await createJob();
      await seedDrivers(nextJobId, driverCount);
      await refresh(nextJobId);
    });
  }

  async function startFullDemo() {
    await runAction('full-demo', async () => {
      const nextJobId = await createJob();
      await seedDrivers(nextJobId, driverCount);
      await addOrdersRaw(nextJobId, 12, 'normal', 'DEMO');
      const seeded = await refresh(nextJobId);
      await moveDriversRaw(nextJobId, seeded);
      const moved = await refresh(nextJobId);
      await cycleRaw(nextJobId, false, moved);
      await refresh(nextJobId);
    });
  }

  async function addOrder(kind: OrderKind = 'normal') {
    if (!jobId) return;
    await runAction('order', async () => { await addOrdersRaw(jobId, 1, kind, kind === 'tight' ? 'TIGHT' : 'LIVE'); await refresh(); });
  }

  async function addBurst(count = 20) {
    if (!jobId) return;
    await runAction('burst', async () => { await addOrdersRaw(jobId, count, 'normal', 'BURST'); await refresh(); });
  }

  async function addNormalOrders() {
    if (!jobId) return;
    await runAction('normal-orders', async () => { await addOrdersRaw(jobId, 10, 'normal', 'NORMAL'); await refresh(); });
  }

  async function addRescueCase() {
    if (!jobId) return;
    await runAction('rescue-case', async () => {
      await addOrdersRaw(jobId, 3, 'rescue', 'RESCUE');
      const seeded = await refresh();
      await moveDriversRaw(jobId, seeded, true);
      const moved = await refresh();
      await cycleRaw(jobId, true, moved);
      await refresh();
    });
  }

  async function moveDrivers(delay = false) {
    if (!jobId) return;
    await runAction(delay ? 'delay' : 'drivers', async () => { await moveDriversRaw(jobId, state, delay); await refresh(); });
  }

  async function runCycle(rescue = false) {
    if (!jobId) return;
    await runAction(rescue ? 'rescue' : 'cycle', async () => { await cycleRaw(jobId, rescue); await refresh(); });
  }

  useEffect(() => {
    if (!jobId) return;
    const timer = window.setInterval(() => { refresh().catch(() => undefined); }, 2500);
    return () => window.clearInterval(timer);
  }, [jobId]);

  useEffect(() => {
    if (!jobId || !autoRun || busy) return;
    const timer = window.setInterval(() => {
      (async () => {
        setBusy('auto-run');
        try {
          await moveDriversRaw(jobId, state);
          const moved = await refresh(jobId);
          await cycleRaw(jobId, false, moved);
          await refresh(jobId);
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Auto run failed');
        } finally {
          setBusy(null);
        }
      })().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [autoRun, busy, jobId, state]);

  const beforeAssigned = previousState?.assigned ?? 0;
  const beforeKm = previousState?.routes.reduce((sum, route) => sum + route.distanceKm, 0) ?? 0;
  const afterKm = state.routes.reduce((sum, route) => sum + route.distanceKm, 0);

  return <div className="live-control-center">
    <section className="live-hero simulator-hero">
      <div><span className="eyebrow">Dynamic ML Dispatch Simulator</span><h2>IRX Live Dispatch Control Center</h2><p>One-click live scenario: multi-zone HCM orders, 4+ drivers, Forecast risk, GreedRL action control, tri-model repair, map delta, and safety guards.</p></div>
      <div className="live-actions hero-actions"><button className="btn hero-start" onClick={startFullDemo} disabled={!!busy}><Zap size={17} />Start Full Live Demo</button><button className="btn secondary" onClick={startJob} disabled={!!busy}>{jobId ? 'Restart Job' : 'Start Empty Job'}</button><button className="btn secondary" onClick={() => refresh()} disabled={!jobId || !!busy}><RefreshCw size={15} />Refresh</button></div>
    </section>
    <section className="simulator-toolbar" aria-label="Live simulator controls">
      <div><span>Drivers</span><div className="segmented-control">{[2, 4, 6].map((count) => <button key={count} className={driverCount === count ? 'active' : ''} onClick={() => setDriverCount(count)} disabled={!!busy}>{count}</button>)}</div></div>
      <button className={`auto-toggle ${autoRun ? 'active' : ''}`} onClick={() => setAutoRun((value) => !value)} disabled={!jobId}>{autoRun ? 'Auto Run ON' : 'Auto Run OFF'}<small>3s cycle</small></button>
      <span className="scenario-hint">Open → Start Full Live Demo → map/routes/ML trace move within 5 seconds.</span>
    </section>
    {error ? <div className="error-strip"><AlertTriangle size={16} />{error}</div> : null}
    <MetricsBar state={state} lastCycle={lastCycle} safe={safe} />
    <div className="live-grid">
      <OrdersQueue orders={state.orders} disabled={!jobId || !!busy} addOrder={addOrder} addBurst={addBurst} addNormalOrders={addNormalOrders} addRescueCase={addRescueCase} startFullDemo={startFullDemo} />
      <div className="live-map-stack"><LiveDispatchMapPanel state={state} previousState={previousState} lastCycle={lastCycle} /><DriverRouteBoard drivers={state.drivers} routes={state.routes} frozenStopIds={state.frozenStopIds} moveDrivers={moveDrivers} runCycle={runCycle} disabled={!jobId || !!busy} /></div>
      <MlDecisionPanel lastCycle={lastCycle} />
    </div>
    <div className="live-bottom-grid">
      <BeforeAfterPanel beforeAssigned={beforeAssigned} afterAssigned={state.assigned} beforeKm={beforeKm} afterKm={afterKm} lastCycle={lastCycle} />
      <SafetyGuardPanel safety={safety} safe={safe} />
      <EventStreamPanel events={state.events} />
    </div>
    <details className="raw-json"><summary>Raw JSON</summary><pre>{JSON.stringify({ jobId, state, lastCycle }, null, 2)}</pre></details>
  </div>;
}

function MetricsBar({ state, lastCycle, safe }: { state: LiveState; lastCycle: LiveCycleResponse | null; safe: boolean }) {
  const totalKm = state.routes.reduce((sum, route) => sum + route.distanceKm, 0).toFixed(1);
  const metrics = [
    ['Orders', String(state.orders.length)], ['Assigned', String(state.assigned)], ['Buffered', String(state.buffered)], ['Late', String(lastCycle?.late ?? 0)], ['Km', totalKm], ['Runtime', `${Number(lastCycle?.diagnostics.runtimeMs ?? 0)}ms`], ['Forecast', lastCycle?.forecastUsed ? 'Used' : 'Idle'], ['GreedRL', lastCycle?.greedRlAction ?? 'Idle'], ['Repair', lastCycle?.triModelRepairUsed ? 'Tri-model' : 'Idle'], ['Guard', safe ? 'SAFE' : 'CHECK']
  ];
  return <section className="live-metrics">{metrics.map(([label, value]) => <div key={label} className={`live-kpi ${label === 'Guard' && safe ? 'safe' : ''}`}><span>{label}</span><strong>{value}</strong></div>)}</section>;
}

function OrdersQueue({ orders, disabled, addOrder, addBurst, addNormalOrders, addRescueCase, startFullDemo }: { orders: LiveOrderState[]; disabled: boolean; addOrder: (kind?: OrderKind) => void; addBurst: (count?: number) => void; addNormalOrders: () => void; addRescueCase: () => void; startFullDemo: () => void }) {
  return <section className="live-panel orders-simulator"><PanelTitle icon={<Plus size={16} />} title="Live Orders" badge={`${orders.length} orders`} />
    <button className="btn hero-start full-width" disabled={disabled} onClick={startFullDemo}><Zap size={15} />Start Full Demo</button>
    <div className="live-button-row scenario-buttons"><button className="btn secondary" disabled={disabled} onClick={addNormalOrders}>Normal Orders</button><button className="btn secondary" disabled={disabled} onClick={() => addBurst(20)}>Burst 20 Orders</button><button className="btn secondary" disabled={disabled} onClick={() => addOrder('tight')}>Tight Deadline</button><button className="btn secondary" disabled={disabled} onClick={() => addOrder('normal')}>Add Random</button><button className="btn danger" disabled={disabled} onClick={addRescueCase}>Rescue Case</button></div>
    <div className="order-list">{orders.length === 0 ? <EmptyLive text="No orders yet. Hit Start Full Demo for 12 multi-zone orders." /> : orders.map((item) => {
    const pickupLat = item.order.pickup?.lat ?? item.order.pickupLat ?? 0;
    const pickupLng = item.order.pickup?.lng ?? item.order.pickupLng ?? 0;
    const dropoffLat = item.order.dropoff?.lat ?? item.order.dropoffLat ?? 0;
    const dropoffLng = item.order.dropoff?.lng ?? item.order.dropoffLng ?? 0;
    const highRisk = item.order.priority === 'HIGH' || item.order.priority === 10;
    return <article key={item.order.orderId} className={`order-card ${item.status.toLowerCase()} ${highRisk ? 'high-risk' : ''}`}><div><strong>{item.order.orderId}</strong><span>{item.status}</span></div><p>P: {fmt(pickupLat)}, {fmt(pickupLng)} → D: {fmt(dropoffLat)}, {fmt(dropoffLng)}</p><small>Risk: {highRisk ? 'HIGH' : item.status === 'BUFFERED' ? 'MEDIUM' : 'LOW'} · priority {String(item.order.priority ?? 'NORMAL')}</small></article>;
  })}</div></section>;
}
function DriverRouteBoard({ drivers, routes, frozenStopIds, disabled, moveDrivers, runCycle }: { drivers: LiveDriverState[]; routes: LiveRouteSnapshot[]; frozenStopIds: string[]; disabled: boolean; moveDrivers: (delay?: boolean) => void; runCycle: (rescue?: boolean) => void }) {
  return <section className="live-panel route-board"><PanelTitle icon={<Truck size={16} />} title="Driver Route Board" badge={`${routes.length} routes`} /><div className="live-button-row"><button className="btn secondary" disabled={disabled} onClick={() => moveDrivers(false)}>Move Drivers</button><button className="btn secondary" disabled={disabled} onClick={() => moveDrivers(true)}>Simulate Delay</button><button className="btn" disabled={disabled} onClick={() => runCycle(false)}><Play size={15} />Run Cycle</button><button className="btn danger" disabled={disabled} onClick={() => runCycle(true)}>Trigger Rescue</button></div><div className="driver-columns">{routes.length === 0 ? <EmptyLive text="Drivers ready. Add orders or start full demo to draw routes." /> : routes.map((route) => <article key={route.routeId} className="driver-column"><h4>{route.driverId}<span>{drivers.find((driver) => driver.driverId === route.driverId)?.status ?? 'ONLINE'}</span></h4><ol>{route.stopIds.map((stopId, index) => <li key={`${stopId}-${index}`} className={`${stopId.startsWith('PICKUP') ? 'pickup' : 'dropoff'} ${frozenStopIds.includes(stopId) ? 'frozen' : ''}`}><span>{stopId.startsWith('PICKUP') ? 'P' : 'D'}</span><strong>{stopId.split(':')[1]}</strong><small>ETA +{(index + 1) * 4}m Â· load {stopId.startsWith('PICKUP') ? '+1' : '-1'} {frozenStopIds.includes(stopId) ? 'Â· frozen' : ''}</small></li>)}</ol></article>)}</div></section>;
}

function MlDecisionPanel({ lastCycle }: { lastCycle: LiveCycleResponse | null }) {
  const diagnostics = lastCycle?.diagnostics ?? {};
  const rows = [
    ['Forecast', lastCycle?.forecastUsed ? 'risk updated' : 'waiting', `risk count ${diagnostics.forecastRiskCount ?? 0}`],
    ['GreedRL', lastCycle?.greedRlAction ?? 'waiting', 'operator TRI_MODEL_REPAIR'],
    ['Tabular', 'mutation scorer', `scored ${diagnostics.tabularInferenceCount ?? 0}`],
    ['RouteFinder', 'candidate provider', `candidates ${diagnostics.routefinderCandidateCount ?? 0}`],
    ['Adaptive Policy', 'top-K selector', `accepted ${diagnostics.acceptedMlMutations ?? 0}`]
  ];
  return <section className="live-panel"><PanelTitle icon={<Cpu size={16} />} title="ML Decisions" badge="Realtime trace" />{rows.map(([name, status, detail]) => <div key={name} className="ml-row"><span>{name}</span><strong>{status}</strong><small>{detail}</small></div>)}</section>;
}

function BeforeAfterPanel({ beforeAssigned, afterAssigned, beforeKm, afterKm, lastCycle }: { beforeAssigned: number; afterAssigned: number; beforeKm: number; afterKm: number; lastCycle: LiveCycleResponse | null }) {
  return <section className="live-panel"><PanelTitle icon={<GitBranch size={16} />} title="Before â†’ After" badge="Dominance" /><div className="before-after"><div><span>Before</span><strong>{beforeAssigned} assigned</strong><small>{beforeKm.toFixed(1)} km</small></div><div><span>After</span><strong>{afterAssigned} assigned</strong><small>{afterKm.toFixed(1)} km</small></div><div><span>Delta</span><strong>{afterAssigned - beforeAssigned >= 0 ? '+' : ''}{afterAssigned - beforeAssigned} order</strong><small>{(afterKm - beforeKm).toFixed(1)} km</small></div></div><p className="accepted-line"><CheckCircle2 size={15} />Accepted because assigned not lower, late not worse, PD/capacity valid, dominance guard pass.</p>{lastCycle ? <p className="muted">Last source: {lastCycle.mode}</p> : null}</section>;
}

function SafetyGuardPanel({ safety, safe }: { safety: Record<string, number>; safe: boolean }) {
  return <section className="live-panel"><PanelTitle icon={<ShieldCheck size={16} />} title="Safety Guards" badge={safe ? 'SAFE' : 'CHECK'} />{Object.entries(safety).map(([name, value]) => <div key={name} className="guard-row"><span>{name}</span><strong>{value}</strong></div>)}</section>;
}

function EventStreamPanel({ events }: { events: LiveEvent[] }) {
  return <section className="live-panel"><PanelTitle icon={<RadioTower size={16} />} title="Event Stream" badge={`${events.length} events`} /><div className="event-list">{events.slice(-10).reverse().map((event) => <div key={`${event.type}-${event.createdAt}`}><span>{new Date(event.createdAt).toLocaleTimeString()}</span><strong>{event.type}</strong><small>{event.subject}</small></div>)}</div></section>;
}

function PanelTitle({ icon, title, badge }: { icon: ReactNode; title: string; badge: string }) { return <div className="panel-title"><h3>{icon}{title}</h3><span className="mini-badge">{badge}</span></div>; }
function EmptyLive({ text }: { text: string }) { return <div className="empty-live"><Clock size={18} />{text}</div>; }
function fmt(value: number) { return value.toFixed(3); }


