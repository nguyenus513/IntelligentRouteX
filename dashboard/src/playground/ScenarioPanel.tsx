import type { AdaptiveMode, PlaygroundMode } from './playgroundTypes';

export function ScenarioPanel({ scenarioId, mode, adaptiveMode }: { scenarioId: string; mode: PlaygroundMode; adaptiveMode: AdaptiveMode }) {
  return <section className="playground-card scenario-card" aria-label="Scenario config">
    <div className="playground-card-title"><span>Scenario</span><strong>{scenarioId}</strong></div>
    <div className="scenario-grid">
      <Metric label="Mode" value={mode} />
      <Metric label="Adaptive" value={adaptiveMode} />
      <Metric label="Coverage" value="DRAIN_UNTIL_ACCOUNTED" />
      <Metric label="Contract" value="/api/v1 locked" />
    </div>
  </section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="playground-metric"><span>{label}</span><strong>{value}</strong></div>;
}

