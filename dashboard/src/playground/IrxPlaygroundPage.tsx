import { useMemo, useState } from 'react';
import { Activity, Database, LifeBuoy, Play, RefreshCcw, RadioTower } from 'lucide-react';
import { AdaptiveMlPanel } from './AdaptiveMlPanel';
import { AssignmentTable } from './AssignmentTable';
import { BaselinePanel } from './BaselinePanel';
import { EventArtifactPanel } from './EventArtifactPanel';
import { PlaygroundTopBar } from './PlaygroundTopBar';
import { RawJsonPanel } from './RawJsonPanel';
import { ResultPanel } from './ResultPanel';
import { ScenarioPanel } from './ScenarioPanel';
import { getBatch, getBatchItems, getJob, getJobArtifacts, getJobEvents, getJobResult, getLiveEvents, getLiveState, getRescueResult, getRuntimeMetrics, runBigDataDemo, runLiveDemo, runRescueDemo, runStaticScenario } from './playgroundApi';
import type { AdaptiveMode, PlaygroundMode, PlaygroundSnapshot } from './playgroundTypes';

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
  const [snapshot, setSnapshot] = useState<PlaygroundSnapshot>(() => initialSnapshot('STATIC_DISPATCH', 'QUALITY_SEEKING', 'raw-s'));

  const modeTone = useMemo(() => ({
    STATIC_DISPATCH: { icon: <Play size={18} />, label: 'Static dispatch job' },
    LIVE_ROLLING: { icon: <RadioTower size={18} />, label: 'Live rolling cycle' },
    RESCUE: { icon: <LifeBuoy size={18} />, label: 'Rescue dispatch' },
    BIGDATA_LITE: { icon: <Database size={18} />, label: 'BigData-lite batch' }
  })[mode], [mode]);

  function reset() {
    setError(null);
    setSnapshot(initialSnapshot(mode, adaptiveMode, scenarioId));
  }

  async function run() {
    setBusy(true);
    setError(null);
    const base = initialSnapshot(mode, adaptiveMode, scenarioId);
    try {
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
      setError(cause instanceof Error ? cause.message : 'Playground API flow failed');
    } finally {
      setBusy(false);
    }
  }

  return <div className="playground-shell">
    <PlaygroundTopBar scenarioId={scenarioId} mode={mode} adaptiveMode={adaptiveMode} busy={busy} onScenario={setScenarioId} onMode={setMode} onAdaptiveMode={setAdaptiveMode} onRun={run} onReset={reset} />
    {error && <div className="playground-error" role="alert">{error}</div>}
    <div className="playground-status-strip"><span>{modeTone.icon}{modeTone.label}</span><span><Activity size={16} />Backend `/api/v1` contract locked</span><span>Metrics {snapshot.metrics?.jobsCreated ?? 0} jobs</span></div>
    <main className="playground-grid">
      <ScenarioPanel scenarioId={scenarioId} mode={mode} adaptiveMode={adaptiveMode} />
      <ResultPanel snapshot={snapshot} />
      <AdaptiveMlPanel snapshot={snapshot} />
      <BaselinePanel snapshot={snapshot} />
      <AssignmentTable snapshot={snapshot} />
      <EventArtifactPanel snapshot={snapshot} />
      <RawJsonPanel snapshot={snapshot} />
    </main>
  </div>;
}

