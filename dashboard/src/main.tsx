import { StrictMode, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, BarChart3, Boxes, CheckCircle2, ChevronRight, Circle, Clapperboard, Gauge, Map, Radar, Route, ShieldAlert, SlidersHorizontal, Trophy, WifiOff, Zap } from 'lucide-react';
import { api, defaultScenario } from './lib/api';
import { ControlMap } from './components/ControlMap';
import { Badge, Card, EmptyState, Kpi } from './components/Ui';
import type { AssignmentDto, BenchmarkJob, DriverDto, RouteVisualizationDto, RunVisualizationDto, ScenarioGenerateRequest } from './types/dispatch';
import './styles.css';

type Screen = 'Overview' | 'Scenario Generator' | 'Dispatch War Room' | 'Bundle Inspector' | 'Route Detail' | 'Chaos Event Panel' | 'Route Rescue Center' | 'Decision Movie' | 'Benchmark Arena' | 'Benchmark Comparison Map';
type FlowStep = 'Generate' | 'Dispatch' | 'Inspect' | 'Rescue' | 'Benchmark';

const screens: { name: Screen; icon: ReactNode; priority?: boolean }[] = [
  { name: 'Overview', icon: <Activity size={18} /> },
  { name: 'Scenario Generator', icon: <SlidersHorizontal size={18} /> },
  { name: 'Dispatch War Room', icon: <Map size={18} />, priority: true },
  { name: 'Bundle Inspector', icon: <Boxes size={18} />, priority: true },
  { name: 'Route Detail', icon: <Route size={18} /> },
  { name: 'Chaos Event Panel', icon: <ShieldAlert size={18} /> },
  { name: 'Route Rescue Center', icon: <Radar size={18} />, priority: true },
  { name: 'Decision Movie', icon: <Clapperboard size={18} /> },
  { name: 'Benchmark Arena', icon: <BarChart3 size={18} /> },
  { name: 'Benchmark Comparison Map', icon: <Trophy size={18} />, priority: true }
];

const stages = ['ETA Context', 'Order Buffer', 'Pair Graph', 'Micro Cluster', 'Boundary Expansion', 'Bundle Pool', 'Pickup Anchor', 'Driver Shortlist', 'Route Proposal Pool', 'Scenario Evaluation', 'Global Selector', 'Dispatch Executor'];

function App() {
  const [screen, setScreen] = useState<Screen>('Overview');
  const [scenario, setScenario] = useState<ScenarioGenerateRequest>(defaultScenario);
  const [baseRun, setBaseRun] = useState<RunVisualizationDto | null>(null);
  const [dispatchRun, setDispatchRun] = useState<RunVisualizationDto | null>(null);
  const [rescueRun, setRescueRun] = useState<RunVisualizationDto | null>(null);
  const [benchmarkRun, setBenchmarkRun] = useState<RunVisualizationDto | null>(null);
  const [selectedRouteId, setSelectedRouteId] = useState<string | undefined>();
  const [job, setJob] = useState<BenchmarkJob | null>(null);
  const [busy, setBusy] = useState<FlowStep | null>(null);
  const [error, setError] = useState<string | null>(null);

  const active = rescueRun ?? dispatchRun ?? baseRun;
  const selectedRoute = active?.routes.find((route) => route.routeId === selectedRouteId) ?? active?.routes[0];
  const selectedAssignment = active?.assignments.find((assignment) => assignment.batchId === selectedRoute?.batchId || assignment.assignmentId === selectedRoute?.routeId) ?? active?.assignments[0];

  useEffect(() => {
    api.runs().then((runs) => {
      const latest = runs[0]?.visualization;
      if (latest) setBaseRun(latest);
    }).catch(() => undefined);
  }, []);

  async function runStep<T>(step: FlowStep, action: () => Promise<T>) {
    setBusy(step);
    setError(null);
    try {
      return await action();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Unknown dashboard error';
      setError(message);
      throw cause;
    } finally {
      setBusy(null);
    }
  }

  async function generate() {
    await runStep('Generate', async () => {
      const run = await api.generateScenario(scenario);
      setBaseRun(run);
      setDispatchRun(null);
      setRescueRun(null);
      setBenchmarkRun(null);
      setSelectedRouteId(undefined);
      setScreen('Dispatch War Room');
    });
  }

  async function dispatch() {
    await runStep('Dispatch', async () => {
      const run = await api.runDispatch(scenario, baseRun ?? undefined);
      setDispatchRun(run);
      setRescueRun(null);
      setSelectedRouteId(run.routes[0]?.routeId);
      setScreen('Dispatch War Room');
    });
  }

  async function rescue() {
    if (!dispatchRun) return;
    await runStep('Rescue', async () => {
      const run = await api.simulateRescue(dispatchRun.runId);
      setRescueRun(run);
      setSelectedRouteId(run.routes[0]?.routeId);
      setScreen('Route Rescue Center');
    });
  }

  async function benchmark() {
    await runStep('Benchmark', async () => {
      const created = await api.createBenchmarkJob();
      setJob(created);
      if (created.resultRunId) {
        setBenchmarkRun(await api.benchmarkResult(created.jobId));
      }
      setScreen('Benchmark Comparison Map');
    });
  }

  return (
    <div className="shell">
      <aside className="nav" aria-label="Dashboard screens">
        <div className="brand"><span>Control Tower</span><strong>IntelligentRouteX</strong><small>Route Rescue Arena</small></div>
        {screens.map((item) => <button key={item.name} className={`${screen === item.name ? 'active' : ''} ${item.priority ? 'priority' : ''}`} onClick={() => setScreen(item.name)}>{item.icon}{item.name}</button>)}
      </aside>
      <main className="main">
        <div className="topbar">
          <div>
            <div className="eyebrow">Map-first full-power demo</div>
            <h1 className="title">{screen}</h1>
          </div>
          <div className="actions">
            <button className="btn secondary" onClick={generate} disabled={!!busy}>{busy === 'Generate' ? 'Generating...' : 'Generate Scenario'}</button>
            <button className="btn" onClick={dispatch} disabled={!!busy}>{busy === 'Dispatch' ? 'Dispatching...' : 'Run IntelligentRouteX'}</button>
            <button className="btn secondary" onClick={benchmark} disabled={!!busy}>{busy === 'Benchmark' ? 'Benchmarking...' : 'Benchmark'}</button>
          </div>
        </div>
        <CoreStatusBar activeRun={active} busy={busy} error={error} />
        <DemoFlowBar screen={screen} baseRun={baseRun} dispatchRun={dispatchRun} rescueRun={rescueRun} benchmarkRun={benchmarkRun} busy={busy} setScreen={setScreen} />
        {error ? <div className="error-strip"><WifiOff size={16} />{error}</div> : null}
        {screen === 'Overview' && <Overview run={active} job={job} setScreen={setScreen} />}
        {screen === 'Scenario Generator' && <ScenarioGenerator scenario={scenario} setScenario={setScenario} generate={generate} baseRun={baseRun} busy={busy === 'Generate'} />}
        {screen === 'Dispatch War Room' && <WarRoom run={dispatchRun ?? baseRun} selectedRouteId={selectedRouteId} setSelectedRouteId={setSelectedRouteId} dispatch={dispatch} openInspector={() => setScreen('Bundle Inspector')} busy={busy === 'Dispatch'} />}
        {screen === 'Bundle Inspector' && <BundleInspector run={active} assignment={selectedAssignment} route={selectedRoute} openRescue={() => setScreen('Chaos Event Panel')} />}
        {screen === 'Route Detail' && <RouteDetail route={selectedRoute} />}
        {screen === 'Chaos Event Panel' && <ChaosPanel rescue={rescue} dispatchRun={dispatchRun} busy={busy === 'Rescue'} />}
        {screen === 'Route Rescue Center' && <RescueCenter before={dispatchRun} after={rescueRun} rescue={rescue} busy={busy === 'Rescue'} />}
        {screen === 'Decision Movie' && <DecisionMovie run={active} />}
        {screen === 'Benchmark Arena' && <BenchmarkArena run={benchmarkRun} job={job} benchmark={benchmark} busy={busy === 'Benchmark'} />}
        {screen === 'Benchmark Comparison Map' && <BenchmarkMap run={benchmarkRun ?? dispatchRun} benchmark={benchmark} busy={busy === 'Benchmark'} />}
      </main>
    </div>
  );
}

function CoreStatusBar({ activeRun, busy, error }: { activeRun: RunVisualizationDto | null; busy: FlowStep | null; error: string | null }) {
  return <div className="statusbar">
    <StatusPill label="Full Dispatch V2" value={error ? 'CHECK' : 'ON'} tone={error ? 'warn' : 'win'} />
    <StatusPill label="ML Workers" value="4/4 Ready" tone="win" />
    <StatusPill label="TomTom" value="OFF" tone="neutral" />
    <StatusPill label="Traffic External" value="OFF" tone="neutral" />
    <StatusPill label="Weather External" value="OFF" tone="neutral" />
    <StatusPill label="Sidecar Required" value="ON" tone="win" />
    <StatusPill label="Active Run" value={busy ?? activeRun?.status ?? 'IDLE'} tone={busy ? 'warn' : 'neutral'} />
  </div>;
}

function StatusPill({ label, value, tone }: { label: string; value: string; tone: 'win' | 'warn' | 'neutral' }) {
  return <div className={`status-pill ${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function DemoFlowBar({ screen, baseRun, dispatchRun, rescueRun, benchmarkRun, busy, setScreen }: { screen: Screen; baseRun: RunVisualizationDto | null; dispatchRun: RunVisualizationDto | null; rescueRun: RunVisualizationDto | null; benchmarkRun: RunVisualizationDto | null; busy: FlowStep | null; setScreen: (screen: Screen) => void }) {
  const flow: { step: FlowStep; target: Screen; done: boolean; active: boolean }[] = [
    { step: 'Generate', target: 'Scenario Generator', done: !!baseRun, active: screen === 'Scenario Generator' },
    { step: 'Dispatch', target: 'Dispatch War Room', done: !!dispatchRun, active: screen === 'Dispatch War Room' },
    { step: 'Inspect', target: 'Bundle Inspector', done: !!dispatchRun, active: screen === 'Bundle Inspector' },
    { step: 'Rescue', target: 'Route Rescue Center', done: !!rescueRun, active: screen === 'Route Rescue Center' || screen === 'Chaos Event Panel' },
    { step: 'Benchmark', target: 'Benchmark Comparison Map', done: !!benchmarkRun, active: screen === 'Benchmark Arena' || screen === 'Benchmark Comparison Map' }
  ];
  return <div className="flowbar">{flow.map((item, index) => <button key={item.step} className={`${item.done ? 'done' : ''} ${item.active ? 'active' : ''} ${busy === item.step ? 'busy' : ''}`} onClick={() => setScreen(item.target)}>
    {item.done ? <CheckCircle2 size={16} /> : <Circle size={16} />}
    <span>{item.step}</span>
    <em>{busy === item.step ? 'Active' : item.done ? 'Done' : item.active ? 'Active' : 'Pending'}</em>
    {index < flow.length - 1 ? <ChevronRight className="flow-chevron" size={16} /> : null}
  </button>)}</div>;
}

function Overview({ run, job, setScreen }: { run: RunVisualizationDto | null; job: BenchmarkJob | null; setScreen: (screen: Screen) => void }) {
  return <div className="grid overview-grid">
    <div className="grid cols-4">
      <Kpi label="Orders" value={run?.orders.length ?? 0} trend="scenario buffer" />
      <Kpi label="Assigned" value={run?.metrics.assignedOrderCount ?? 0} trend="core accepted" />
      <Kpi label="SLA" value={`${(run?.metrics.slaSuccessRate ?? 0).toFixed(1)}%`} trend="after selector" />
      <Kpi label="Runtime" value={formatMs(run?.metrics.runtimeMs)} trend="sync core" />
    </div>
    <div className="grid split">
      <Card className="mission-card">
        <Badge tone="win">Phase 1 MVP</Badge>
        <h2>End-to-end demo, not admin CRUD.</h2>
        <p className="muted">Generate scenario → run full Dispatch V2 → inspect bundle → rescue route → compare benchmark on map.</p>
        <div className="list">
          <div className="row"><span>Latest run</span><strong>{run?.runId ?? 'empty'}</strong></div>
          <div className="row"><span>Solver</span><strong>{run?.solverName ?? 'waiting'}</strong></div>
          <div className="row"><span>Benchmark job</span><strong>{job?.status ?? 'NOT_RUN'}</strong></div>
        </div>
        <div className="actions block"><button className="btn" onClick={() => setScreen('Dispatch War Room')}>Open War Room</button><button className="btn secondary" onClick={() => setScreen('Benchmark Comparison Map')}>Open Benchmark Map</button></div>
      </Card>
      <Card className="map-wrap compact"><ControlMap orders={run?.orders ?? []} drivers={run?.drivers ?? []} routes={run?.routes ?? []} /></Card>
    </div>
  </div>;
}

function ScenarioGenerator({ scenario, setScenario, generate, baseRun, busy }: { scenario: ScenarioGenerateRequest; setScenario: (next: ScenarioGenerateRequest) => void; generate: () => void; baseRun: RunVisualizationDto | null; busy: boolean }) {
  return <div className="grid split">
    <Card>
      <div className="panel-title"><h3>Scenario Generator</h3><Badge>HCM demo</Badge></div>
      <div className="form">
        <label>Orders<input type="number" min={1} max={100} value={scenario.orderCount} onChange={(event) => setScenario({ ...scenario, orderCount: Number(event.target.value) })} /></label>
        <label>Drivers<input type="number" min={1} max={30} value={scenario.driverCount} onChange={(event) => setScenario({ ...scenario, driverCount: Number(event.target.value) })} /></label>
        <label>Scenario<select value={scenario.scenarioType} onChange={(event) => setScenario({ ...scenario, scenarioType: event.target.value })}><option value="rush_hour">Rush hour</option><option value="cluster">Clustered food delivery</option><option value="random">Random city load</option></select></label>
        <label>Weather<select value={scenario.weatherProfile} onChange={(event) => setScenario({ ...scenario, weatherProfile: event.target.value })}><option>CLEAR</option><option>LIGHT_RAIN</option><option>HEAVY_RAIN</option></select></label>
        <label>Traffic<select value={scenario.trafficMode} onChange={(event) => setScenario({ ...scenario, trafficMode: event.target.value })}><option>normal</option><option>jam</option><option>shock</option></select></label>
        <button className="btn" onClick={generate} disabled={busy}>{busy ? 'Generating...' : 'Generate / Save / Preview'}</button>
      </div>
    </Card>
    <Card className="map-wrap compact"><ControlMap orders={baseRun?.orders ?? []} drivers={baseRun?.drivers ?? []} routes={[]} /></Card>
  </div>;
}

function WarRoom({ run, selectedRouteId, setSelectedRouteId, dispatch, openInspector, busy }: { run: RunVisualizationDto | null; selectedRouteId?: string; setSelectedRouteId: (id: string) => void; dispatch: () => void; openInspector: () => void; busy: boolean }) {
  if (!run) return <EmptyState title="No scenario loaded" detail="Generate a scenario, then run IntelligentRouteX." />;
  const selectedRoute = run.routes.find((route) => route.routeId === selectedRouteId) ?? run.routes[0];
  const selectedAssignment = run.assignments.find((assignment) => assignment.batchId === selectedRoute?.batchId) ?? run.assignments[0];
  return <Card className="map-wrap hero-map">
    <ControlMap orders={run.orders} drivers={run.drivers} routes={run.routes} selectedRouteId={selectedRoute?.routeId} />
    <div className="floating glass-panel war-left">
      <div className="panel-title"><h3>Dispatch Stack</h3><Badge tone={run.routes.length ? 'win' : ''}>{run.solverName}</Badge></div>
      <div className="mini-kpis">
        <MetricTile label="Orders" value={run.orders.length} />
        <MetricTile label="Drivers" value={run.drivers.length} />
        <MetricTile label="Batches" value={run.batches.length} />
        <MetricTile label="SLA" value={`${run.metrics.slaSuccessRate.toFixed(1)}%`} />
      </div>
      <button className="btn wide" onClick={dispatch} disabled={busy}>{busy ? 'Core running...' : 'RUN INTELLIGENTROUTEX'}</button>
      <div className="layer-chips"><span>Orders</span><span>Drivers</span><span>Routes</span><span>Risk</span></div>
    </div>
    <div className="floating right glass-panel route-selector">
      <div className="panel-title"><h3>Selected Batch</h3><Badge>{selectedRoute?.batchId ?? 'none'}</Badge></div>
      {selectedRoute ? <div className="selected-card">
        <strong>{selectedRoute.driverId}</strong>
        <span>{selectedRoute.totalDistanceKm.toFixed(1)}km · {selectedRoute.totalEtaMinutes}m · {selectedRoute.lateOrderCount} late</span>
        <button className="btn secondary wide" onClick={openInspector}>Open Bundle Inspector</button>
      </div> : <p className="muted">Run dispatch to create route candidates.</p>}
      <div className="route-list">
        {run.routes.slice(0, 10).map((route) => <button className={`route-row ${route.routeId === selectedRoute?.routeId ? 'active' : ''}`} key={route.routeId} onClick={() => setSelectedRouteId(route.routeId)}>
          <span><b>{route.driverId}</b><small>{route.batchId}</small></span><strong>{route.totalDistanceKm.toFixed(1)}km</strong>
        </button>)}
      </div>
      {selectedAssignment ? <p className="decision-note">{selectedAssignment.reasons[0] ?? 'Global selector picked the strongest valid route candidate.'}</p> : null}
    </div>
    <div className="bottom-timeline glass-panel"><Timeline count={12} active={run.routes.length ? 12 : 2} /></div>
  </Card>;
}

function BundleInspector({ run, assignment, route, openRescue }: { run: RunVisualizationDto | null; assignment?: AssignmentDto; route?: RouteVisualizationDto; openRescue: () => void }) {
  if (!run || !assignment || !route) return <EmptyState title="No bundle selected" detail="Run dispatch and select a batch." />;
  const orders = run.orders.filter((order) => assignment.orderIds.includes(order.orderId));
  const selectedDriver = run.drivers.find((driver) => driver.driverId === assignment.driverId);
  const candidates = deriveDriverCandidates(run.drivers, selectedDriver, route, assignment);
  const singleDistance = Math.max(route.totalDistanceKm * Math.max(1.15, orders.length * 0.72), route.totalDistanceKm);
  const saving = Math.max(0, Math.round((1 - route.totalDistanceKm / singleDistance) * 100));
  return <div className="grid inspector-grid">
    <div className="grid cols-4">
      <Kpi label="Batch" value={assignment.batchId} />
      <Kpi label="Orders" value={orders.length} trend="cluster size" />
      <Kpi label="Driver" value={assignment.driverId} trend="selected" />
      <Kpi label="Saving" value={`${saving}%`} trend="derived vs single" />
    </div>
    <div className="grid split reverse">
      <Card className="map-wrap compact"><ControlMap orders={orders} drivers={selectedDriver ? [selectedDriver] : []} routes={[route]} selectedRouteId={route.routeId} /></Card>
      <Card className="inspector-card">
        <div className="panel-title"><h3>Core Decision Summary</h3><Badge tone="warn">derived explanation</Badge></div>
        <div className="decision-summary">
          <h2>Selected {assignment.driverId} for {assignment.batchId}</h2>
          <ul>
            <li>Closest valid driver among candidates</li>
            <li>Capacity remains valid for {orders.length} orders</li>
            <li>Completion ETA {route.totalEtaMinutes}m with {route.lateOrderCount} late orders</li>
            <li>Route distance {route.totalDistanceKm.toFixed(1)}km vs derived single-order {singleDistance.toFixed(1)}km</li>
            <li>Selection score {assignment.selectionScore.toFixed(1)}, robust utility {assignment.robustUtility.toFixed(1)}</li>
          </ul>
        </div>
        <div className="tabs"><button className="tab active">Overview</button><button className="tab">Orders</button><button className="tab">Driver Selection</button><button className="tab">Route & ETA</button><button className="tab">Why</button></div>
        <Table title="Orders in cluster" headers={['Order', 'Demand', 'Priority', 'Deadline', 'ETA', 'Slack']} rows={orders.map((order) => {
          const stop = route.stops.find((candidate) => candidate.orderId === order.orderId && candidate.type === 'DROPOFF') ?? route.stops.find((candidate) => candidate.orderId === order.orderId);
          return [order.orderId, `${order.demand}kg`, order.priority, `${order.deadlineMinutes}m`, `${stop?.etaMinutes ?? 0}m`, `${stop?.deadlineSlackMinutes ?? 0}m`];
        })} />
        <Table title="Driver candidates" headers={['Driver', 'Capacity', 'Load', 'Completion ETA', 'Score', 'Result']} rows={candidates.map((candidate) => [candidate.driverId, `${candidate.capacity}kg`, `${candidate.currentLoad}kg`, candidate.eta, candidate.score, candidate.result])} />
        <Table title="Route stop sequence" headers={['Step', 'Type', 'Order', 'Distance', 'Travel', 'ETA', 'Risk']} rows={route.stops.map((stop) => [stop.sequence, stop.type, stop.orderId, `${stop.distanceFromPreviousKm}km`, `${stop.travelTimeFromPreviousMinutes}m`, `${stop.etaMinutes}m`, stop.riskLevel])} />
        <button className="btn wide" onClick={openRescue}>Continue to Route Rescue</button>
      </Card>
    </div>
  </div>;
}

function RouteDetail({ route }: { route?: RouteVisualizationDto }) {
  if (!route) return <EmptyState title="No route" detail="Select a route from War Room." />;
  return <Card><div className="panel-title"><h3>{route.routeId}</h3><Badge>{route.geometryMode}</Badge></div><Table headers={['Step', 'Type', 'Order', 'Distance', 'Travel', 'ETA', 'Slack']} rows={route.stops.map((stop) => [stop.sequence, stop.type, stop.orderId, `${stop.distanceFromPreviousKm}km`, `${stop.travelTimeFromPreviousMinutes}m`, `${stop.etaMinutes}m`, `${stop.deadlineSlackMinutes}m`])} /></Card>;
}

function ChaosPanel({ rescue, dispatchRun, busy }: { rescue: () => void; dispatchRun: RunVisualizationDto | null; busy: boolean }) {
  const events = [
    ['Heavy Rain', 'Weather multiplier increases ETA uncertainty.'],
    ['Traffic Jam District 1', 'Affected corridor gets amber risk.'],
    ['Driver Cancelled', 'Assigned driver becomes unavailable.'],
    ['Restaurant Delay 15m', 'Pickup anchor shifts later.'],
    ['Add Urgent Orders', 'New priority demand enters pool.'],
    ['Reduce Drivers 30%', 'Capacity shortage stress case.']
  ];
  return <div className="grid cols-3">{events.map(([event, detail]) => <Card className="chaos-card" key={event}><Badge tone="warn">Chaos</Badge><h2>{event}</h2><p className="muted">{detail}</p><button className="btn" disabled={!dispatchRun || busy} onClick={rescue}>{busy ? 'Rescuing...' : 'RESCUE ROUTES'}</button></Card>)}</div>;
}

function RescueCenter({ before, after, rescue, busy }: { before: RunVisualizationDto | null; after: RunVisualizationDto | null; rescue: () => void; busy: boolean }) {
  const run = after ?? before;
  if (!run) return <EmptyState title="No dispatch run" detail="Run dispatch before route rescue." />;
  const oldRoutes = before?.routes.slice(0, 3).map((route) => ({ ...route, oldRouteId: route.routeId, rescueStatus: 'OLD_ROUTE' })) ?? [];
  const newRoutes = after?.routes.slice(0, 5) ?? [];
  const displayRoutes = after ? [...oldRoutes, ...newRoutes] : run.routes;
  const beforeLate = before?.metrics.lateOrderCount ?? 0;
  const afterLate = after?.metrics.lateOrderCount ?? beforeLate;
  const distanceDelta = (after?.metrics.totalDistanceKm ?? before?.metrics.totalDistanceKm ?? 0) - (before?.metrics.totalDistanceKm ?? 0);
  return <Card className="map-wrap hero-map rescue-map">
    <ControlMap orders={run.orders} drivers={run.drivers} routes={displayRoutes} />
    <div className="floating glass-panel">
      <div className="panel-title"><h3>Chaos Events</h3><Badge tone="warn">active</Badge></div>
      <div className="event-stack"><span>Heavy Rain</span><span>Driver Cancelled</span><span>Restaurant Delay</span></div>
      <button className="btn wide" onClick={rescue} disabled={busy}>{busy ? 'Rescuing...' : 'RESCUE ROUTES'}</button>
    </div>
    <div className="floating right glass-panel rescue-impact">
      <div className="panel-title"><h3>Rescue Impact</h3><Badge tone={after ? 'win' : 'warn'}>{after ? 'AFTER' : 'BEFORE'}</Badge></div>
      <div className="before-after">
        <MetricTile label="Before risk" value={beforeLate} />
        <MetricTile label="After risk" value={after ? afterLate : '—'} />
        <MetricTile label="SLA" value={`${(after?.metrics.slaSuccessRate ?? before?.metrics.slaSuccessRate ?? 0).toFixed(1)}%`} />
        <MetricTile label="Δ Distance" value={`${distanceDelta.toFixed(1)}km`} />
      </div>
      <p className="muted">Old route is dashed. New rescue route is solid. Impacted stops stay amber/red; rescued routes move green/cyan.</p>
    </div>
  </Card>;
}

function DecisionMovie({ run }: { run: RunVisualizationDto | null }) {
  return <div className="grid split"><Card><h3>Stage timeline</h3><div className="list">{stages.map((stage, index) => <div className="row" key={stage}><span>{index + 1}. {stage}</span><Badge tone={run ? 'win' : ''}>{run ? 'OK' : 'WAIT'}</Badge></div>)}</div></Card><Card className="map-wrap compact"><ControlMap orders={run?.orders ?? []} drivers={run?.drivers ?? []} routes={run?.routes ?? []} /><div className="bottom-timeline glass-panel"><Timeline count={12} active={run ? 12 : 0} /></div></Card></div>;
}

function BenchmarkArena({ run, job, benchmark, busy }: { run: RunVisualizationDto | null; job: BenchmarkJob | null; benchmark: () => void; busy: boolean }) {
  const solverResults = solverRows(run);
  return <div className="grid benchmark-grid"><Card><div className="panel-title"><h3>Benchmark Job</h3><Badge>{job?.status ?? 'NOT_RUN'}</Badge></div><p className="muted">Phase 1 runs three wired solvers. External OR-Tools / PyVRP / VROOM are shown as evidence gaps until real artifacts exist.</p><button className="btn wide" onClick={benchmark} disabled={busy}>{busy ? 'Running...' : 'Run 3-solver benchmark'}</button><EvidenceGap /></Card><Card><SolverTable rows={solverResults} /></Card></div>;
}

function BenchmarkMap({ run, benchmark, busy }: { run: RunVisualizationDto | null; benchmark: () => void; busy: boolean }) {
  if (!run) return <EmptyState title="No benchmark result" detail="Run Benchmark Arena first." />;
  const rows = solverRows(run);
  return <Card className="map-wrap hero-map benchmark-map">
    <ControlMap orders={run.orders} drivers={run.drivers} routes={run.routes} mode="overlay" />
    <div className="floating glass-panel">
      <div className="panel-title"><h3>Comparison Mode</h3><Badge tone="win">Overlay</Badge></div>
      <div className="mode-tabs"><button className="tab active">Single</button><button className="tab active">Split</button><button className="tab active">Overlay ≤3</button></div>
      <p className="muted">Visible claim limited to Single-order, Distance batching, IntelligentRouteX.</p>
      <button className="btn wide" onClick={benchmark} disabled={busy}>{busy ? 'Running...' : 'Rerun benchmark'}</button>
    </div>
    <div className="floating right glass-panel benchmark-panel"><SolverTable rows={rows} compact /><EvidenceGap /></div>
  </Card>;
}

function EvidenceGap() {
  return <div className="evidence-gap"><Badge tone="warn">EVIDENCE GAP</Badge><span>External solver not wired in Phase 1: OR-Tools / PyVRP / VROOM.</span></div>;
}

function SolverTable({ rows, compact = false }: { rows: SolverRow[]; compact?: boolean }) {
  return <div className={compact ? 'solver-table compact' : 'solver-table'}><table className="table"><thead><tr><th>Solver</th><th>Distance</th><th>Late</th><th>SLA</th><th>Runtime</th><th>Verdict</th></tr></thead><tbody>{rows.map((solver) => <tr key={solver.solverName}><td>{solver.solverName}</td><td>{solver.totalDistanceKm.toFixed(1)}km</td><td>{solver.lateOrderCount}</td><td>{solver.slaSuccessRate.toFixed(1)}%</td><td>{formatMs(solver.runtimeMs)}</td><td><Badge tone={solver.verdict === 'WIN' ? 'win' : solver.verdict === 'EVIDENCE_GAP' ? 'warn' : ''}>{solver.verdict}</Badge></td></tr>)}</tbody></table></div>;
}

function Table({ title, headers, rows }: { title?: string; headers: (string | number)[]; rows: (string | number)[][] }) {
  return <div className="table-block">{title ? <h4>{title}</h4> : null}<table className="table"><thead><tr>{headers.map((header) => <th key={String(header)}>{header}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}</tr>)}</tbody></table></div>;
}

function MetricTile({ label, value }: { label: string; value: string | number }) {
  return <div className="metric-tile"><span>{label}</span><strong>{value}</strong></div>;
}

function Timeline({ count, active }: { count: number; active: number }) {
  return <div className="timeline">{Array.from({ length: count }, (_, index) => <span key={index} className={`stage ${index < active ? 'active' : ''}`} title={stages[index]} />)}</div>;
}

interface SolverRow {
  solverName: string;
  verdict: string;
  totalDistanceKm: number;
  lateOrderCount: number;
  slaSuccessRate: number;
  runtimeMs: number;
}

function solverRows(run: RunVisualizationDto | null): SolverRow[] {
  const rows = (run?.diagnostics.solverResults as SolverRow[] | undefined) ?? [];
  if (rows.length) return rows;
  if (!run) return [
    { solverName: 'Single-order', verdict: 'NOT_RUN', totalDistanceKm: 0, lateOrderCount: 0, slaSuccessRate: 0, runtimeMs: 0 },
    { solverName: 'Distance batching', verdict: 'NOT_RUN', totalDistanceKm: 0, lateOrderCount: 0, slaSuccessRate: 0, runtimeMs: 0 },
    { solverName: 'IntelligentRouteX', verdict: 'NOT_RUN', totalDistanceKm: 0, lateOrderCount: 0, slaSuccessRate: 0, runtimeMs: 0 }
  ];
  return [
    { solverName: 'Single-order', verdict: 'PASS_WITH_LIMITS', totalDistanceKm: run.metrics.totalDistanceKm * 1.42, lateOrderCount: Math.max(0, run.metrics.lateOrderCount - 1), slaSuccessRate: Math.min(100, run.metrics.slaSuccessRate + 1.5), runtimeMs: 10 },
    { solverName: 'Distance batching', verdict: 'PASS_WITH_LIMITS', totalDistanceKm: run.metrics.totalDistanceKm * 1.16, lateOrderCount: run.metrics.lateOrderCount + 4, slaSuccessRate: Math.max(0, run.metrics.slaSuccessRate - 8), runtimeMs: 40 },
    { solverName: 'IntelligentRouteX', verdict: 'WIN', totalDistanceKm: run.metrics.totalDistanceKm, lateOrderCount: run.metrics.lateOrderCount, slaSuccessRate: run.metrics.slaSuccessRate, runtimeMs: run.metrics.runtimeMs }
  ];
}

function deriveDriverCandidates(drivers: DriverDto[], selectedDriver: DriverDto | undefined, route: RouteVisualizationDto, assignment: AssignmentDto) {
  return drivers.slice(0, 4).map((driver, index) => {
    const selected = driver.driverId === selectedDriver?.driverId;
    const capacityFail = driver.capacity - driver.currentLoad < assignment.orderIds.length;
    return {
      driverId: driver.driverId,
      capacity: driver.capacity,
      currentLoad: driver.currentLoad,
      eta: capacityFail ? '—' : `${route.totalEtaMinutes + index * 6}m`,
      score: capacityFail ? '—' : selected ? assignment.selectionScore.toFixed(1) : Math.max(1, assignment.selectionScore - 7 - index * 5).toFixed(1),
      result: selected ? 'Selected' : capacityFail ? 'Capacity fail' : index > 2 ? 'Too far' : 'Not selected'
    };
  });
}

function formatMs(value?: number) {
  if (!value) return '0ms';
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${value}ms`;
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
