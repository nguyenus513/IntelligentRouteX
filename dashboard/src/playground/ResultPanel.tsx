import type { PlaygroundViewModel } from '../lib/irxResultMapper';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function ResultPanel({ snapshot, viewModel }: { snapshot: PlaygroundSnapshot; viewModel: PlaygroundViewModel }) {
  const ready = viewModel.hasResult;
  const status = snapshot.staticResult?.finalSolver ?? snapshot.staticResult?.status ?? snapshot.job?.status ?? (ready ? 'Loaded' : 'Ready');
  return <section className="playground-card result-panel" aria-label="Result summary">
    <div className="playground-card-title"><span>Result</span><strong>{status}</strong></div>
    <div className="result-kpis">
      <Tile label="Coverage" value={ready ? `${viewModel.metrics.assigned}/${viewModel.metrics.orders}` : 'Not run yet'} />
      <Tile label="Distance" value={ready ? `${viewModel.metrics.distanceKm} km` : 'Not run yet'} />
      <Tile label="Late" value={ready ? String(viewModel.metrics.late) : 'Not run yet'} />
      <Tile label="Runtime" value={ready ? `${viewModel.metrics.runtimeMs} ms` : 'Not run yet'} />
    </div>
    <div className="playground-route-strip">
      {viewModel.routes.slice(0, 5).map((route) => <span key={route.routeId}>{route.driverId} · {route.distanceKm}km · {route.stops.length / 2} orders</span>)}
      {viewModel.routes.length ? null : <span>No route result yet</span>}
    </div>
  </section>;
}

function Tile({ label, value }: { label: string; value: string }) {
  return <div className="result-tile"><span>{label}</span><strong>{value}</strong></div>;
}
