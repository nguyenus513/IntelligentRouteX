import type { PlaygroundSnapshot } from './playgroundTypes';

export function ResultPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const result = snapshot.staticResult;
  const coverage = result?.coverage;
  const summary = result?.summary;
  const metrics = result?.metrics;
  const ready = Boolean(result || snapshot.liveState || snapshot.cycle || snapshot.rescue || snapshot.batch);
  return <section className="playground-card result-panel" aria-label="Result summary">
    <div className="playground-card-title"><span>Result</span><strong>{result?.finalSolver ?? result?.status ?? snapshot.job?.status ?? (ready ? 'Loaded' : 'Ready')}</strong></div>
    <div className="result-kpis">
      <Tile label="Coverage" value={coverage ? `${coverage.assigned}/${coverage.total}` : summary ? String(summary.assignedOrders ?? 0) : ready ? 'loaded' : 'Not run yet'} />
      <Tile label="Distance" value={ready ? `${metrics?.distanceKm ?? summary?.totalKm ?? 'pending'} km` : 'Not run yet'} />
      <Tile label="Late" value={ready ? String(metrics?.lateCount ?? summary?.lateCount ?? snapshot.rescue?.afterLate ?? 0) : 'Not run yet'} />
      <Tile label="Runtime" value={ready ? `${metrics?.runtimeMs ?? 'pending'} ms` : 'Not run yet'} />
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

