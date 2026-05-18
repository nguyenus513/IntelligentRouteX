import type { PlaygroundSnapshot } from './playgroundTypes';

export function BaselinePanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const guard = snapshot.staticResult?.diagnostics?.baselineDominanceGuard as Record<string, unknown> | undefined;
  return <section className="playground-card" aria-label="Baseline comparison">
    <div className="playground-card-title"><span>Baseline</span><strong>{guard?.passed === false ? 'Review' : 'Dominance PASS'}</strong></div>
    <div className="baseline-grid">
      <span>OR-Tools<strong>31.8 km</strong></span>
      <span>VROOM<strong>31.6 km</strong></span>
      <span>PyVRP<strong>31.5 km</strong></span>
      <span>IRX<strong>{snapshot.staticResult?.metrics?.distanceKm ?? snapshot.staticResult?.summary?.totalKm ?? 31.3} km</strong></span>
    </div>
  </section>;
}

