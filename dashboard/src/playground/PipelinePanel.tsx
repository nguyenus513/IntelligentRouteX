import { CheckCircle2, CircleDashed } from 'lucide-react';
import type { PlaygroundSnapshot } from './playgroundTypes';

const stages = ['Input', 'Seeds', 'Adaptive ML', 'Guard', 'Final'];

export function PipelinePanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const done = Boolean(snapshot.staticResult || snapshot.liveState || snapshot.rescue || snapshot.batch);
  return <section className="playground-card pipeline-panel" aria-label="Optimization pipeline">
    <div className="playground-card-title"><span>Optimization pipeline</span><strong>{done ? 'evidence ready' : 'waiting'}</strong></div>
    <div className="pipeline-rail">
      {stages.map((stage, index) => <div className={`pipeline-stage ${done ? 'done' : ''}`} key={stage}>
        {done ? <CheckCircle2 size={16} /> : <CircleDashed size={16} />}
        <strong>{stage}</strong>
        <span>{index === 2 ? snapshot.adaptiveMode : index === 3 ? 'no-regression' : snapshot.mode}</span>
      </div>)}
    </div>
  </section>;
}
