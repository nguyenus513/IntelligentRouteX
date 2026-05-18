import { MapPin } from 'lucide-react';
import { useMemo, useState } from 'react';
import { routeColor, toMapModel, type MapPoint } from './playgroundMapModel';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function RouteMapPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const model = useMemo(() => toMapModel(snapshot), [snapshot]);
  const project = useProjector(model.points);

  return <section className="playground-card route-map-panel" aria-label="Route map panel">
    <div className="playground-card-title"><span>Map-first dispatch view</span><strong>{model.routes.length} routes · {model.points.length} pins</strong></div>
    {model.synthetic && <div className="map-warning">Synthetic playground coordinates — not a street-level map.</div>}
    <div className="route-map-canvas">
      <svg viewBox="0 0 900 520" role="img" aria-label="Dispatch routes with pickup and dropoff pins">
        <defs>
          <pattern id="map-grid" width="42" height="42" patternUnits="userSpaceOnUse"><path d="M 42 0 L 0 0 0 42" fill="none" stroke="rgba(148,163,184,.11)" strokeWidth="1" /></pattern>
          <filter id="pin-glow"><feGaussianBlur stdDeviation="4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <rect width="900" height="520" rx="26" fill="url(#map-grid)" />
        <path d="M80 410 C210 300 270 360 410 210 S670 170 820 72" fill="none" stroke="rgba(34,211,238,.12)" strokeWidth="26" strokeLinecap="round" />
        {model.routes.map((route) => {
          const d = route.points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${project(point).x} ${project(point).y}`).join(' ');
          return <g key={route.driverId}>
            <path d={d} fill="none" stroke="rgba(2,6,23,.85)" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
            <path d={d} fill="none" stroke={routeColor(route.driverId)} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={route.source.includes('LIVE') ? '10 10' : undefined} />
          </g>;
        })}
        {model.points.map((point) => {
          const pos = project(point);
          const color = routeColor(point.driverId ?? point.id);
          return <g className="map-pin" key={point.id} transform={`translate(${pos.x} ${pos.y})`} onClick={() => setSelected(point)} tabIndex={0} role="button" aria-label={`${point.kind} ${point.label}`}>
            <circle r={point.kind === 'DRIVER' ? 15 : 12} fill={point.kind === 'RESCUE' ? '#fb7185' : color} opacity=".22" filter="url(#pin-glow)" />
            <circle r={point.kind === 'DRIVER' ? 11 : 9} fill="#020617" stroke={point.kind === 'RESCUE' ? '#fb7185' : color} strokeWidth="3" />
            <text y="4" textAnchor="middle" fontSize="9" fontWeight="800" fill="#e5f5ff">{point.label.slice(0, 3)}</text>
          </g>;
        })}
      </svg>
      <div className="map-tooltip">
        {selected ? <><strong>{selected.kind} · {selected.label}</strong><span>Order: {selected.orderId ?? '—'}</span><span>Driver: {selected.driverId ?? '—'}</span><span>Source: {selected.source ?? '—'}</span></> : <><MapPin size={16} /><span>Click a pin to inspect route state.</span></>}
      </div>
    </div>
  </section>;
}

function useProjector(points: MapPoint[]) {
  return useMemo(() => {
    const latMin = Math.min(...points.map((point) => point.lat));
    const latMax = Math.max(...points.map((point) => point.lat));
    const lngMin = Math.min(...points.map((point) => point.lng));
    const lngMax = Math.max(...points.map((point) => point.lng));
    const latSpan = Math.max(0.001, latMax - latMin);
    const lngSpan = Math.max(0.001, lngMax - lngMin);
    return (point: MapPoint) => ({ x: 70 + ((point.lng - lngMin) / lngSpan) * 760, y: 450 - ((point.lat - latMin) / latSpan) * 380 });
  }, [points]);
}
