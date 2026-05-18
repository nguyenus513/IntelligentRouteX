import { toMapModel } from './playgroundMapModel';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function AssignmentTable({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const rows = snapshot.batchItems?.items ?? toMapModel(snapshot).points.filter((point) => point.kind === 'PICKUP').map((point, index) => ({
    orderId: point.orderId,
    routeId: point.driverId,
    eta: `P ${8}:${String(10 + index * 3).padStart(2, '0')} / G ${8}:${String(25 + index * 3).padStart(2, '0')}`,
    source: point.source ?? 'ASSIGNED'
  }));
  return <section className="playground-card assignment-panel" aria-label="Assignments">
    <div className="playground-card-title"><span>Assignments</span><strong>{rows.length} rows</strong></div>
    <div className="playground-table" role="table">
      <div className="playground-table-head" role="row"><span>Order</span><span>Driver</span><span>Pickup / dropoff ETA</span><span>Source</span></div>
      {rows.slice(0, 8).map((row, index) => <div className="playground-table-row" role="row" key={index}>
        <span>{String(row.orderId ?? `ORD-${index + 1}`)}</span>
        <span>{String(row.routeId ?? 'D01')}</span>
        <span>{String(row.eta ?? 'on-time')}</span>
        <span className="ok-chip">{String(row.source ?? 'ASSIGNED')}</span>
      </div>)}
      {rows.length === 0 && <div className="playground-empty">Run a flow to preview assignments.</div>}
    </div>
  </section>;
}
