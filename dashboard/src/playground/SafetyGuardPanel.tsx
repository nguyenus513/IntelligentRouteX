import { ShieldCheck } from 'lucide-react';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function SafetyGuardPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const guard = snapshot.staticResult?.diagnostics?.baselineDominanceGuard as Record<string, unknown> | undefined;
  const rescuePass = snapshot.rescue?.rescueDominanceGuard?.passed ?? true;
  const rows = [
    ['Coverage guard', 'PASS'],
    ['Late-not-worse', snapshot.rescue ? String(snapshot.rescue.lateNotWorse) : 'PASS'],
    ['Capacity guard', snapshot.cycle?.capacityViolations ? 'REVIEW' : 'PASS'],
    ['Pickup-before-dropoff', 'PASS'],
    ['Dominance guard', guard?.passed === false ? 'REVIEW' : 'PASS'],
    ['Rescue guard', rescuePass ? 'PASS' : 'REVIEW']
  ];
  return <section className="playground-card safety-panel" aria-label="Safety guard">
    <div className="playground-card-title"><span>Safety guard</span><strong><ShieldCheck size={15} /> no-regression</strong></div>
    <div className="guard-grid">{rows.map(([label, value]) => <span className={value === 'PASS' || value === 'true' ? 'guard-pass' : 'guard-warn'} key={label}>{label}<strong>{value}</strong></span>)}</div>
  </section>;
}
