import type { PlaygroundViewModel } from '../lib/irxResultMapper';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function BaselinePanel({ snapshot, viewModel }: { snapshot: PlaygroundSnapshot; viewModel: PlaygroundViewModel }) {
  const best = viewModel.baselines.filter((row) => row.solver !== 'IRX Final').sort((a, b) => a.distanceKm - b.distanceKm)[0];
  const gain = best ? Math.round((best.distanceKm - viewModel.metrics.distanceKm) * 10) / 10 : 0;
  return <section className="playground-card" aria-label="Baseline comparison">
    <div className="playground-card-title"><span>Baseline</span><strong>{viewModel.hasResult ? `Gain ${gain}km` : 'Waiting'}</strong></div>
    <div className="baseline-grid">
      {(viewModel.baselines.length ? viewModel.baselines : [
        { solver: 'OR-Tools', distanceKm: 0, late: 0, verdict: 'Not run' },
        { solver: 'VROOM', distanceKm: 0, late: 0, verdict: 'Not run' },
        { solver: 'PyVRP', distanceKm: 0, late: 0, verdict: 'Not run' },
        { solver: 'IRX Final', distanceKm: 0, late: 0, verdict: snapshot.mode }
      ]).map((row) => <span key={row.solver}>{row.solver}<strong>{row.distanceKm ? `${row.distanceKm} km` : row.verdict}</strong></span>)}
    </div>
  </section>;
}
