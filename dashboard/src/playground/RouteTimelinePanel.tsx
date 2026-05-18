import { GitBranch } from 'lucide-react';
import type { CSSProperties } from 'react';
import { useMemo } from 'react';
import { routeColor, toMapModel } from './playgroundMapModel';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function RouteTimelinePanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const model = useMemo(() => toMapModel(snapshot), [snapshot]);
  return <section className="playground-card route-timeline-panel" aria-label="Route timeline">
    <div className="playground-card-title"><span>Route timeline</span><strong><GitBranch size={15} /> sequence</strong></div>
    <div className="timeline-routes">
      {model.routes.map((route) => <div className="timeline-route" key={route.driverId} style={{ '--route-color': routeColor(route.driverId) } as CSSProperties}>
        <div className="timeline-driver"><strong>{route.driverId}</strong><span>{route.source}</span></div>
        <div className="timeline-stops">
          {route.points.slice(0, 10).map((point, index) => <span className={`timeline-stop ${point.kind.toLowerCase()}`} key={point.id}><b>{index + 1}</b>{point.label}<small>{point.kind}</small></span>)}
        </div>
      </div>)}
    </div>
  </section>;
}
