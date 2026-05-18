import type { AdaptiveMode, PlaygroundMode } from './playgroundTypes';

interface Props {
  scenarioId: string;
  mode: PlaygroundMode;
  adaptiveMode: AdaptiveMode;
  busy: boolean;
  onScenario: (value: string) => void;
  onMode: (value: PlaygroundMode) => void;
  onAdaptiveMode: (value: AdaptiveMode) => void;
  onRun: () => void;
  onReset: () => void;
}

export function PlaygroundTopBar({ scenarioId, mode, adaptiveMode, busy, onScenario, onMode, onAdaptiveMode, onRun, onReset }: Props) {
  return <header className="playground-topbar">
    <div>
      <p className="playground-eyebrow">API-first dispatch platform</p>
      <h1>IRX Playground</h1>
      <span>Locked `/api/v1` contract demo for static, live, rescue, and BigData-lite flows.</span>
    </div>
    <div className="playground-controls" aria-label="Playground controls">
      <label>Scenario<select value={scenarioId} onChange={(event) => onScenario(event.target.value)}><option value="raw-s">raw-s</option><option value="raw-m">raw-m</option><option value="random-spread">random-spread</option></select></label>
      <label>Mode<select value={mode} onChange={(event) => onMode(event.target.value as PlaygroundMode)}><option value="STATIC_DISPATCH">Static</option><option value="LIVE_ROLLING">Live</option><option value="RESCUE">Rescue</option><option value="BIGDATA_LITE">BigData</option></select></label>
      <label>Adaptive ML<select value={adaptiveMode} onChange={(event) => onAdaptiveMode(event.target.value as AdaptiveMode)}><option value="QUALITY_SEEKING">QUALITY_SEEKING</option><option value="TOP_K_ASSISTED">TOP_K_ASSISTED</option></select></label>
      <button className="playground-primary" onClick={onRun} disabled={busy}>{busy ? 'Running…' : 'Run'}</button>
      <button className="playground-secondary" onClick={onReset} disabled={busy}>Reset</button>
    </div>
  </header>;
}

