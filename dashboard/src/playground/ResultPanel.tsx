import type { PlaygroundSnapshot } from './playgroundTypes';

export function ResultPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const result = snapshot.staticResult;
  const coverage = result?.coverage;
  const summary = result?.summary;
  const metrics = result?.metrics;
  return <section className="playground-card result-panel" aria-label="Result summary">
    <div className="playground-card-title"><span>Result</span><strong>{result?.finalSolver ?? result?.status ?? snapshot.job?.status ?? 'Ready'}</strong></div>
    <div className="result-kpis">
      <Tile label="Coverage" value={coverage ? `${coverage.assigned}/${coverage.total}` : summary ? String(summary.assignedOrders ?? 0) : '—'} />
      <Tile label="Distance" value={`${metrics?.distanceKm ?? summary?.totalKm ?? 0} km`} />
      <Tile label="Late" value={String(metrics?.lateCount ?? summary?.lateCount ?? snapshot.rescue?.afterLate ?? 0)} />
      <Tile label="Runtime" value={`${metrics?.runtimeMs ?? 0} ms`} />
    </div>
    <div className="playground-route-strip">
      {(snapshot.batchItems?.items ?? []).slice(0, 5).map((item, index) => <span key={index}>{String(item.orderId ?? item.routeId ?? `item-${index + 1}`)}</span>)}
      {snapshot.batchItems?.items.length ? null : <span>No assignment page loaded yet</span>}
    </div>
  </section>;
}

function Tile({ label, value }: { label: string; value: string }) {
  return <div className="result-tile"><span>{label}</span><strong>{value}</strong></div>;
}

