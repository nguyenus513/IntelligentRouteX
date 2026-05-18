import type { PlaygroundSnapshot } from './playgroundTypes';

export function SeedAttributionPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const diagnostics = snapshot.staticResult?.diagnostics ?? {};
  const policy = diagnostics.adaptiveMlPolicy as Record<string, unknown> | undefined;
  const finalSource = snapshot.staticResult?.finalSolver ?? snapshot.mode;
  const rows = [
    ['Best base seed', String(policy?.bestSeed ?? 'PYVRP_SEED')],
    ['Selected final source', finalSource],
    ['VROOM_SEED', snapshot.mode === 'STATIC_DISPATCH' ? 'evidence gap / optional' : 'not used'],
    ['PYVRP_SEED', snapshot.mode === 'STATIC_DISPATCH' ? '1 route candidate' : 'not used'],
    ['ADAPTIVE_ML_MOVE', snapshot.adaptiveMode === 'QUALITY_SEEKING' ? 'accepted moves' : 'ranking assist'],
    ['COVERAGE_DRAIN', 'enabled']
  ];
  return <section className="playground-card seed-panel" aria-label="Seed attribution">
    <div className="playground-card-title"><span>Seed attribution</span><strong>source trace</strong></div>
    <ul className="signal-list">{rows.map(([label, value]) => <li key={label}><span>{label}</span><strong>{value}</strong></li>)}</ul>
  </section>;
}
