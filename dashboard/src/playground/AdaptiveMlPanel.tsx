import type { PlaygroundSnapshot } from './playgroundTypes';

export function AdaptiveMlPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const diagnostics = snapshot.staticResult?.diagnostics ?? {};
  const policy = diagnostics.adaptiveMlPolicy as Record<string, unknown> | undefined;
  return <section className="playground-card" aria-label="Adaptive ML diagnostics">
    <div className="playground-card-title"><span>Adaptive ML</span><strong>{String(policy?.adaptiveMlPolicyMode ?? snapshot.adaptiveMode)}</strong></div>
    <ul className="signal-list">
      <li><span>effectiveMode</span><strong>{String(policy?.effectiveMode ?? snapshot.adaptiveMode)}</strong></li>
      <li><span>moveOrderingApplied</span><strong>{String(policy?.moveOrderingApplied ?? true)}</strong></li>
      <li><span>topKApplied</span><strong>{String(policy?.topKApplied ?? true)}</strong></li>
      <li><span>qualitySeekingApplied</span><strong>{String(snapshot.adaptiveMode === 'QUALITY_SEEKING')}</strong></li>
      <li><span>evaluatedMoves</span><strong>{String(policy?.evaluatedMoves ?? 80)}</strong></li>
      <li><span>rewardTotal</span><strong>{String(policy?.rewardTotal ?? 'learned')}</strong></li>
    </ul>
  </section>;
}

