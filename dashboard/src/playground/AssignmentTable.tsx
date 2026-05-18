import type { PlaygroundSnapshot } from './playgroundTypes';

export function AssignmentTable({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const rows = snapshot.batchItems?.items ?? [];
  return <section className="playground-card assignment-panel" aria-label="Assignments">
    <div className="playground-card-title"><span>Assignments</span><strong>{rows.length} rows</strong></div>
    <div className="playground-table" role="table">
      <div className="playground-table-head" role="row"><span>Order</span><span>Route</span><span>ETA</span><span>Status</span></div>
      {rows.slice(0, 8).map((row, index) => <div className="playground-table-row" role="row" key={index}>
        <span>{String(row.orderId ?? `ORD-${index + 1}`)}</span>
        <span>{String(row.routeId ?? 'R-1')}</span>
        <span>{String(row.eta ?? 'on-time')}</span>
        <span className="ok-chip">ASSIGNED</span>
      </div>)}
      {rows.length === 0 && <div className="playground-empty">Run BigData demo to preview paginated assignments.</div>}
    </div>
  </section>;
}

