import { useEffect, useMemo, useState } from 'react';
import { Activity, Database, LifeBuoy, Play, RadioTower } from 'lucide-react';
import { AdaptiveMlPanel } from './AdaptiveMlPanel';
import { ApiHealthBadge } from './ApiHealthBadge';
import { AssignmentTable } from './AssignmentTable';
import { BaselinePanel } from './BaselinePanel';
import { BigDataPipelinePanel } from './BigDataPipelinePanel';
import { EventArtifactPanel } from './EventArtifactPanel';
import { PipelinePanel } from './PipelinePanel';
import { PlaygroundTopBar } from './PlaygroundTopBar';
import { RawJsonPanel } from './RawJsonPanel';
import { ResultPanel } from './ResultPanel';
import { RouteMapPanel } from './RouteMapPanel';
import { RouteTimelinePanel } from './RouteTimelinePanel';
import { SafetyGuardPanel } from './SafetyGuardPanel';
import { ScenarioPanel } from './ScenarioPanel';
import { SeedAttributionPanel } from './SeedAttributionPanel';
import { API_BASE, checkApiHealth, describeApiError, getBatch, getBatchItems, getJob, getJobArtifacts, getJobEvents, getJobResult, getLiveEvents, getLiveState, getRescueResult, getRuntimeMetrics, runBigDataDemo, runLiveDemo, runRescueDemo, runStaticScenario } from './playgroundApi';
import type { AdaptiveMode, ApiHealthSnapshot, PlaygroundMode, PlaygroundSnapshot } from './playgroundTypes';

const initialSnapshot = (mode: PlaygroundMode, adaptiveMode: AdaptiveMode, scenarioId: string): PlaygroundSnapshot => ({
  scenarioId,
  mode,
  adaptiveMode,
  events: [],
  artifacts: [],
  raw: {}
});

export function IrxPlaygroundPage() {
  const [scenarioId, setScenarioId] = useState('raw-s');
  const [mode, setMode] = useState<PlaygroundMode>('STATIC_DISPATCH');
  const [adaptiveMode, setAdaptiveMode] = useState<AdaptiveMode>('QUALITY_SEEKING');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<ApiHealthSnapshot>({ state: 'checking', apiBase: API_BASE, message: 'Checking backend health...' });
  const [snapshot, setSnapshot] = useState<PlaygroundSnapshot>(() => initialSnapshot('STATIC_DISPATCH', 'QUALITY_SEEKING', 'raw-s'));

  const modeTone = useMemo(() => ({
    STATIC_DISPATCH: { icon: <Play size={18} />, label: 'Static dispatch job' },
    LIVE_ROLLING: { icon: <RadioTower size={18} />, label: 'Live rolling cycle' },
    RESCUE: { icon: <LifeBuoy size={18} />, label: 'Rescue dispatch' },
    BIGDATA_LITE: { icon: <Database size={18} />, label: 'BigData-lite batch' }
  })[mode], [mode]);
  const stats = useMemo(() => demoStats(snapshot), [snapshot]);

  async function refreshHealth() {
    setHealth({ state: 'checking', apiBase: API_BASE, message: 'Checking backend health...' });
    setHealth(await checkApiHealth());
  }

  useEffect(() => { void refreshHealth(); }, []);

  function reset() {
    setError(null);
    setSnapshot(initialSnapshot(mode, adaptiveMode, scenarioId));
  }

  async function run() {
    setBusy(true);
    setError(null);
    const base = initialSnapshot(mode, adaptiveMode, scenarioId);
    try {
      const currentHealth = await checkApiHealth();
      setHealth(currentHealth);
      if (currentHealth.state !== 'online') throw new Error(currentHealth.message);
      if (mode === 'STATIC_DISPATCH') {
        const job = await runStaticScenario({ scenarioId, adaptiveMode });
        const current = await getJob(job.jobId);
        const result = await getJobResult(job.jobId);
        const [events, artifacts, metrics] = await Promise.all([getJobEvents(job.jobId), getJobArtifacts(job.jobId), getRuntimeMetrics()]);
        setSnapshot({ ...base, job: current, staticResult: result, events, artifacts, metrics, raw: { lastRequest: { scenarioId, adaptiveMode }, lastResponse: current, result } });
      }
      if (mode === 'LIVE_ROLLING') {
        const cycle = await runLiveDemo();
        const [liveState, events, metrics] = await Promise.all([getLiveState(), getLiveEvents(), getRuntimeMetrics()]);
        setSnapshot({ ...base, cycle, liveState, events, artifacts: [], metrics, raw: { lastRequest: { mode }, lastResponse: cycle, result: liveState } });
      }
      if (mode === 'RESCUE') {
        const job = await runRescueDemo();
        const rescue = await getRescueResult(job.jobId);
        const [events, artifacts, metrics] = await Promise.all([getJobEvents(job.jobId), getJobArtifacts(job.jobId), getRuntimeMetrics()]);
        setSnapshot({ ...base, job, rescue, events, artifacts, metrics, raw: { lastRequest: { mode }, lastResponse: job, result: rescue } });
      }
      if (mode === 'BIGDATA_LITE') {
        const started = await runBigDataDemo();
        const batch = await getBatch(started.batchId);
        const [batchItems, metrics] = await Promise.all([getBatchItems(started.batchId), getRuntimeMetrics()]);
        setSnapshot({ ...base, batch, batchItems, events: [], artifacts: [], metrics, raw: { lastRequest: { mode }, lastResponse: started, result: batchItems } });
      }
    } catch (cause) {
      setError(describeApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  return <div className="playground-shell">
    <PlaygroundTopBar scenarioId={scenarioId} mode={mode} adaptiveMode={adaptiveMode} busy={busy} onScenario={setScenarioId} onMode={setMode} onAdaptiveMode={setAdaptiveMode} onRun={run} onReset={reset} />
    {error && <div className="playground-error" role="alert">{error}</div>}
    <div className="playground-status-strip"><span>{modeTone.icon}{modeTone.label}</span><span><Activity size={16} />Backend `/api/v1` contract locked</span><span>Metrics {snapshot.metrics?.jobsCreated ?? 0} jobs</span><ApiHealthBadge health={health} onRefresh={refreshHealth} /></div>
    <div className="playground-demo-stats">{stats.map((item) => <span key={item.label}>{item.label}<strong>{item.value}</strong></span>)}</div>
    <main className="playground-grid playground-grid-v2">
      <aside className="playground-left-rail"><ScenarioPanel scenarioId={scenarioId} mode={mode} adaptiveMode={adaptiveMode} /><PipelinePanel snapshot={snapshot} /></aside>
      <section className="playground-map-stack"><RouteMapPanel snapshot={snapshot} /><RouteTimelinePanel snapshot={snapshot} /><AssignmentTable snapshot={snapshot} /></section>
      <aside className="playground-right-rail"><ResultPanel snapshot={snapshot} /><BaselinePanel snapshot={snapshot} /><AdaptiveMlPanel snapshot={snapshot} /><SeedAttributionPanel snapshot={snapshot} /><SafetyGuardPanel snapshot={snapshot} /><BigDataPipelinePanel snapshot={snapshot} /></aside>
      <section className="playground-bottom-rail"><EventArtifactPanel snapshot={snapshot} /><RawJsonPanel snapshot={snapshot} /></section>
    </main>
  </div>;
}

function demoStats(snapshot: PlaygroundSnapshot) {
  const hasRun = Boolean(snapshot.staticResult || snapshot.liveState || snapshot.cycle || snapshot.rescue || snapshot.batch);
  const coverage = snapshot.staticResult?.coverage;
  const summary = snapshot.staticResult?.summary;
  if (!hasRun) {
    return ['Orders', 'Drivers', 'Routes', 'Assigned', 'Late', 'Distance', 'Runtime'].map((label) => ({ label, value: 'Not run yet' }));
  }
  return [
    { label: 'Orders', value: String(coverage?.total ?? summary?.assignedOrders ?? snapshot.batch?.totalItems ?? '—') },
    { label: 'Drivers', value: String(snapshot.liveState?.activeDrivers ?? (snapshot.staticResult ? 2 : '—')) },
    { label: 'Routes', value: String(summary?.routeCount ?? (snapshot.staticResult ? 2 : snapshot.rescue?.rescuedRouteCount ?? '—')) },
    { label: 'Assigned', value: coverage ? `${coverage.assigned}/${coverage.total}` : String(snapshot.cycle?.assigned ?? snapshot.batch?.processedItems ?? '—') },
    { label: 'Late', value: String(snapshot.staticResult?.metrics?.lateCount ?? summary?.lateCount ?? snapshot.rescue?.afterLate ?? 0) },
    { label: 'Distance', value: `${snapshot.staticResult?.metrics?.distanceKm ?? summary?.totalKm ?? '—'} km` },
    { label: 'Runtime', value: `${snapshot.staticResult?.metrics?.runtimeMs ?? '—'} ms` }
  ];
}
