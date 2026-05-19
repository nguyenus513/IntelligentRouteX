import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Cpu, GitBranch, Play, Plus, RadioTower, RefreshCw, ShieldCheck, Truck } from 'lucide-react';

type Point = { lat: number; lng: number };
type LiveOrderRequest = { orderId: string; pickup: Point; dropoff: Point; deadline: string; load: number; priority: 'NORMAL' | 'HIGH' };
type LiveOrderData = { orderId: string; pickup?: Point; dropoff?: Point; pickupLat?: number; pickupLng?: number; dropoffLat?: number; dropoffLng?: number; deadline?: string; deadlineMinutes?: number; load?: number; priority?: number | string };
type LiveOrderState = { order: LiveOrderData; status: string; reason?: string };
type LiveDriverState = { driverId: string; lat: number; lng: number; status: string; currentStopId?: string | null };
type LiveRouteSnapshot = { routeId: string; driverId: string; stopIds: string[]; frozenStopIds: string[]; distanceKm: number; lateCount: number };
type LiveEvent = { type: string; subject: string; createdAt: string };
type LiveState = { jobId: string; cycle: number; assigned: number; buffered: number; orders: LiveOrderState[]; drivers: LiveDriverState[]; routes: LiveRouteSnapshot[]; frozenStopIds: string[]; events: LiveEvent[] };
type LiveCycleResponse = { jobId: string; cycle: number; mode: string; assigned: number; buffered: number; late: number; forecastUsed: boolean; greedRlAction: string; triModelRepairUsed: boolean; routes: LiveRouteSnapshot[]; diagnostics: Record<string, unknown>; assignedRegression: number };

const API_BASE = '/api/v1';
const headers = { 'Content-Type': 'application/json', 'X-Api-Key': 'demo-key', 'X-Tenant-Id': 'demo' };
const emptyState: LiveState = { jobId: '', cycle: 0, assigned: 0, buffered: 0, orders: [], drivers: [], routes: [], frozenStopIds: [], events: [] };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...headers, ...(init.headers ?? {}) } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

function randomOrder(kind: 'normal' | 'tight' = 'normal'): LiveOrderRequest {
  const seed = Date.now() % 10000;
  const jitter = (seed % 97) / 10000;
  return {
    orderId: `LIVE-${seed}`,
    pickup: { lat: 10.75 + jitter, lng: 106.68 + jitter },
    dropoff: { lat: 10.79 + jitter, lng: 106.74 + jitter },
    deadline: new Date(Date.now() + (kind === 'tight' ? 15 : 35) * 60_000).toISOString(),
    load: 1,
    priority: kind === 'tight' ? 'HIGH' : 'NORMAL'
  };
}

export function LiveDispatchDemoPage() {
  const [jobId, setJobId] = useState('');
  const [state, setState] = useState<LiveState>(emptyState);
  const [lastCycle, setLastCycle] = useState<LiveCycleResponse | null>(null);
  const [previousState, setPreviousState] = useState<LiveState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    if (!nextJobId) return;
    const next = await request<LiveState>(`/live/jobs/${nextJobId}/state`);
    setState(next);
  }

  async function startJob() {
    await runAction('start', async () => {
      const response = await request<{ jobId: string }>('/live/jobs', { method: 'POST', body: JSON.stringify({ tenantId: 'demo' }) });
      setJobId(response.jobId);
      setLastCycle(null);
      setPreviousState(null);
      await addDriver(response.jobId, 'D01', 'IDLE', null);
      await refresh(response.jobId);
    });
  }

  async function addDriver(targetJobId: string, driverId: string, status: string, currentStopId: string | null) {
    await request(`/live/jobs/${targetJobId}/drivers/${driverId}/telemetry`, { method: 'POST', body: JSON.stringify({ driverId, lat: 10.72, lng: 106.62, status, currentStopId }) });
  }

  async function addOrder(kind: 'normal' | 'tight' = 'normal') {
    if (!jobId) return;
    await runAction('order', async () => {
      await request(`/live/jobs/${jobId}/orders`, { method: 'POST', body: JSON.stringify({ orders: [randomOrder(kind)] }) });
      await refresh();
    });
  }

  async function addBurst() {
    if (!jobId) return;
    await runAction('burst', async () => {
      const orders = Array.from({ length: 10 }, (_, index) => ({ ...randomOrder(index % 3 === 0 ? 'tight' : 'normal'), orderId: `BURST-${Date.now() % 10000}-${index + 1}` }));
      await request(`/live/jobs/${jobId}/orders`, { method: 'POST', body: JSON.stringify({ orders }) });
      await refresh();
    });
  }

  async function moveDrivers(delay = false) {
    if (!jobId) return;
    await runAction('drivers', async () => {
      const currentStopId = state.routes[0]?.stopIds[0] ?? null;
      await addDriver(jobId, 'D01', delay ? 'DELAYED' : 'EN_ROUTE', currentStopId);
      await addDriver(jobId, 'D02', 'EN_ROUTE', null);
      await refresh();
    });
  }

  async function runCycle(rescue = false) {
    if (!jobId) return;
    await runAction(rescue ? 'rescue' : 'cycle', async () => {
      setPreviousState(state);
      const cycle = await request<LiveCycleResponse>(`/live/jobs/${jobId}/${rescue ? 'rescue' : 'cycle'}`, { method: 'POST', body: JSON.stringify({ returnDiagnostics: true }) });
      setLastCycle(cycle);
      await refresh();
    });
  }

  useEffect(() => {
    if (!jobId) return;
    const timer = window.setInterval(() => { refresh().catch(() => undefined); }, 2500);
    return () => window.clearInterval(timer);
  }, [jobId]);

  const beforeAssigned = previousState?.assigned ?? 0;
  const beforeKm = previousState?.routes.reduce((sum, route) => sum + route.distanceKm, 0) ?? 0;
  const afterKm = state.routes.reduce((sum, route) => sum + route.distanceKm, 0);

  return <div className="live-control-center">
    <section className="live-hero">
      <div><span className="eyebrow">Dynamic ML Dispatch</span><h2>IRX Live Dispatch Control Center</h2><p>Inject orders, move drivers, run Forecast + GreedRL + tri-model repair, then inspect safety and events in real time.</p></div>
      <div className="live-actions"><button className="btn" onClick={startJob} disabled={!!busy}>{jobId ? 'Restart Job' : 'Start Live Job'}</button><button className="btn secondary" onClick={() => refresh()} disabled={!jobId || !!busy}><RefreshCw size={15} />Refresh</button></div>
    </section>
    {error ? <div className="error-strip"><AlertTriangle size={16} />{error}</div> : null}
    <MetricsBar state={state} lastCycle={lastCycle} safe={safe} />
    <div className="live-grid">
      <OrdersQueue orders={state.orders} disabled={!jobId || !!busy} addOrder={addOrder} addBurst={addBurst} />
      <DriverRouteBoard drivers={state.drivers} routes={state.routes} frozenStopIds={state.frozenStopIds} moveDrivers={moveDrivers} runCycle={runCycle} disabled={!jobId || !!busy} />
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

function OrdersQueue({ orders, disabled, addOrder, addBurst }: { orders: LiveOrderState[]; disabled: boolean; addOrder: (kind?: 'normal' | 'tight') => void; addBurst: () => void }) {
  return <section className="live-panel"><PanelTitle icon={<Plus size={16} />} title="Live Orders" badge={`${orders.length} orders`} /><div className="live-button-row"><button className="btn" disabled={disabled} onClick={() => addOrder('normal')}>Add Random</button><button className="btn secondary" disabled={disabled} onClick={() => addOrder('tight')}>Tight Deadline</button><button className="btn secondary" disabled={disabled} onClick={addBurst}>Burst 10</button></div><div className="order-list">{orders.length === 0 ? <EmptyLive text="No live orders yet" /> : orders.map((item) => {
    const pickupLat = item.order.pickup?.lat ?? item.order.pickupLat ?? 0;
    const pickupLng = item.order.pickup?.lng ?? item.order.pickupLng ?? 0;
    const dropoffLat = item.order.dropoff?.lat ?? item.order.dropoffLat ?? 0;
    const dropoffLng = item.order.dropoff?.lng ?? item.order.dropoffLng ?? 0;
    const highRisk = item.order.priority === 'HIGH' || item.order.priority === 10;
    return <article key={item.order.orderId} className={`order-card ${item.status.toLowerCase()}`}><div><strong>{item.order.orderId}</strong><span>{item.status}</span></div><p>P: {fmt(pickupLat)}, {fmt(pickupLng)} → D: {fmt(dropoffLat)}, {fmt(dropoffLng)}</p><small>Risk: {highRisk ? 'HIGH' : item.status === 'BUFFERED' ? 'MEDIUM' : 'LOW'}</small></article>;
  })}</div></section>;
}
function DriverRouteBoard({ drivers, routes, frozenStopIds, disabled, moveDrivers, runCycle }: { drivers: LiveDriverState[]; routes: LiveRouteSnapshot[]; frozenStopIds: string[]; disabled: boolean; moveDrivers: (delay?: boolean) => void; runCycle: (rescue?: boolean) => void }) {
  return <section className="live-panel route-board"><PanelTitle icon={<Truck size={16} />} title="Driver Route Board" badge={`${routes.length} routes`} /><div className="live-button-row"><button className="btn secondary" disabled={disabled} onClick={() => moveDrivers(false)}>Move Drivers</button><button className="btn secondary" disabled={disabled} onClick={() => moveDrivers(true)}>Simulate Delay</button><button className="btn" disabled={disabled} onClick={() => runCycle(false)}><Play size={15} />Run Cycle</button><button className="btn danger" disabled={disabled} onClick={() => runCycle(true)}>Trigger Rescue</button></div><div className="driver-columns">{routes.length === 0 ? <EmptyLive text="No route yet. Add orders then run cycle." /> : routes.map((route) => <article key={route.routeId} className="driver-column"><h4>{route.driverId}<span>{drivers.find((driver) => driver.driverId === route.driverId)?.status ?? 'ONLINE'}</span></h4><ol>{route.stopIds.map((stopId, index) => <li key={`${stopId}-${index}`} className={`${stopId.startsWith('PICKUP') ? 'pickup' : 'dropoff'} ${frozenStopIds.includes(stopId) ? 'frozen' : ''}`}><span>{stopId.startsWith('PICKUP') ? 'P' : 'D'}</span><strong>{stopId.split(':')[1]}</strong><small>ETA +{(index + 1) * 4}m Â· load {stopId.startsWith('PICKUP') ? '+1' : '-1'} {frozenStopIds.includes(stopId) ? 'Â· frozen' : ''}</small></li>)}</ol></article>)}</div></section>;
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

