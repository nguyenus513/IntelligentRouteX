import type { PlaygroundViewModel } from '../lib/irxResultMapper';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function AssignmentTable({ snapshot, viewModel }: { snapshot: PlaygroundSnapshot; viewModel: PlaygroundViewModel }) {
  const rows = snapshot.batchItems?.items?.length ? snapshot.batchItems.items.map((item) => ({
    orderId: String(item.orderId ?? 'batch-order'),
    routeId: String(item.routeId ?? 'BD-QUEUE'),
    eta: 'paged output',
    source: 'BIGDATA_LITE'
  })) : viewModel.stops.map((stop) => ({
    orderId: stop.kind === 'DROPOFF' ? `G ${stop.orderId}` : `P ${stop.orderId}`,
    routeId: stop.driverId,
    eta: stop.eta,
    source: stop.source
  }));
  return <section className="playground-card assignment-panel" aria-label="Assignments">
    <div className="playground-card-title"><span>Assignments</span><strong>{rows.length} stops</strong></div>
    <div className="playground-table" role="table">
      <div className="playground-table-head" role="row"><span>Order</span><span>Driver</span><span>ETA</span><span>Source</span></div>
      {rows.slice(0, 12).map((row, index) => <div className="playground-table-row" role="row" key={`${row.orderId}-${index}`}>
        <span>{row.orderId}</span>
        <span>{row.routeId}</span>
        <span>{row.eta}</span>
        <span className="ok-chip">{row.source}</span>
      </div>)}
      {rows.length === 0 && <div className="playground-empty">Run a flow to preview assignments.</div>}
    </div>
  </section>;
}
