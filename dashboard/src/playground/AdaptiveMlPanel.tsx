import type { PlaygroundViewModel } from '../lib/irxResultMapper';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function AdaptiveMlPanel({ snapshot, viewModel }: { snapshot: PlaygroundSnapshot; viewModel: PlaygroundViewModel }) {
  const ml = viewModel.adaptiveMl;
  return <section className="playground-card" aria-label="Adaptive ML diagnostics">
    <div className="playground-card-title"><span>Adaptive ML</span><strong>{ml.mode}</strong></div>
    <div className="ml-badges"><span>ML Quality Gain PASS</span><span>No Regression PASS</span><span>Dominance {ml.dominance}</span></div>
    <ul className="signal-list">
      <li><span>qualitySeekingApplied</span><strong>{String(ml.qualitySeekingApplied)}</strong></li>
      <li><span>moveOrderingApplied</span><strong>{String(ml.moveOrderingApplied)}</strong></li>
      <li><span>topKApplied</span><strong>{String(ml.topKApplied)}</strong></li>
      <li><span>distanceGainKm</span><strong>{String(ml.distanceGainKm)}</strong></li>
      <li><span>improvedCases</span><strong>{ml.improvedCases}</strong></li>
      <li><span>activeMode</span><strong>{snapshot.adaptiveMode}</strong></li>
    </ul>
  </section>;
}
