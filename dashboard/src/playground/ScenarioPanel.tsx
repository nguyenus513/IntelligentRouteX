import type { AdaptiveMode, PlaygroundMode } from './playgroundTypes';

export function ScenarioPanel({ scenarioId, mode, adaptiveMode }: { scenarioId: string; mode: PlaygroundMode; adaptiveMode: AdaptiveMode }) {
  const endpoint = mode === 'STATIC_DISPATCH' ? 'POST /api/v1/static/dispatch/jobs' : mode === 'LIVE_ROLLING' ? 'POST /api/v1/live/cycles/run-now' : mode === 'RESCUE' ? 'POST /api/v1/rescue/jobs' : 'POST /api/v1/bigdata/batches';
  return <section className="playground-card scenario-card" aria-label="Scenario config">
    <div className="playground-card-title"><span>Scenario</span><strong>{scenarioId}</strong></div>
    <div className="scenario-grid">
      <Metric label="Mode" value={mode} />
      <Metric label="Adaptive" value={adaptiveMode} />
      <Metric label="Coverage" value="DRAIN_UNTIL_ACCOUNTED" />
      <Metric label="Contract" value="/api/v1 locked" />
    </div>
    <div className="api-preview"><span>API request</span><code>{endpoint}</code></div>
    <div className="input-preview">
      <strong>Input preview</strong>
      <p>Orders: ORD-001..ORD-012 · pickup/dropoff/time windows enabled</p>
      <p>Drivers: D01, D02 · capacity 6 · depot/start points enabled</p>
      <p>Policy: TopK 30 · exploration 0.10 · diagnostics/artifacts true</p>
    </div>
  </section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="playground-metric"><span>{label}</span><strong>{value}</strong></div>;
}

