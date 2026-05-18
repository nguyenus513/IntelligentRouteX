import { DatabaseZap } from 'lucide-react';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function BigDataPipelinePanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const batch = snapshot.batch;
  const total = batch?.totalItems ?? batch?.accepted ?? 0;
  const normalized = batch?.normalizedItems ?? batch?.accepted ?? 0;
  const dead = batch?.deadLetterItems ?? batch?.rejected ?? 0;
  const processed = batch?.processedItems ?? normalized;
  const steps = [
    ['Ingest', total],
    ['Normalize', normalized],
    ['Dead-letter', dead],
    ['Queue', batch?.queuedItems ?? normalized],
    ['Process', processed],
    ['Paginate', snapshot.batchItems?.size ?? snapshot.batchItems?.items.length ?? 0]
  ];
  return <section className="playground-card bigdata-pipeline-panel" aria-label="BigData-lite pipeline">
    <div className="playground-card-title"><span>BigData-lite pipeline</span><strong><DatabaseZap size={15} /> batch runtime</strong></div>
    <div className="bigdata-flow">{steps.map(([label, value]) => <div className="bigdata-step" key={label}><span>{label}</span><strong>{String(value)}</strong></div>)}</div>
  </section>;
}
