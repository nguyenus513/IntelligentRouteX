import { MapPin } from 'lucide-react';
import { useMemo, useState } from 'react';
import { LeafletHcmMap } from './LeafletHcmMap';
import { routeColor, toMapModel, type MapModel, type MapPoint } from './playgroundMapModel';
import type { PlaygroundSnapshot } from './playgroundTypes';

export function RouteMapPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  const [selected, setSelected] = useState<MapPoint | null>(null);
  const [mapMode, setMapMode] = useState<'hcm' | 'synthetic'>('hcm');
  const model = useMemo(() => toMapModel(snapshot), [snapshot]);

  return <section className="playground-card route-map-panel" aria-label="Route map panel" data-testid="route-map-panel">
    <div className="playground-card-title"><span>Ho Chi Minh route map</span><strong>{model.summary.routeCount} routes · {model.points.length} pins</strong></div>
    <div className="route-map-toolbar">
      <button className={mapMode === 'hcm' ? 'active' : ''} onClick={() => setMapMode('hcm')} type="button">HCM map</button>
      <button className={mapMode === 'synthetic' ? 'active' : ''} onClick={() => setMapMode('synthetic')} type="button">Synthetic fallback</button>
      <span>Coordinate mode: {mapMode === 'hcm' ? model.coordinateMode : 'SYNTHETIC'}</span>
      <span>Coverage pins: P{model.summary.pickupCount}/G{model.summary.dropoffCount}</span>
      <span>Late: {model.summary.lateCount}</span>
    </div>
    {model.warnings.map((warning) => <div className="map-warning" key={warning}>{warning}</div>)}
    <div className="route-map-canvas">
      {model.points.length === 0 ? <MapEmptyState message={model.warnings[0]} /> : mapMode === 'hcm' ? <LeafletHcmMap model={model} onSelectPoint={setSelected} /> : <SvgSyntheticMap model={model} selected={selected} onSelectPoint={setSelected} />}
      <MapLegend />
      <div className="map-tooltip">
        {selected ? <><strong>{selected.kind} · {selected.label}</strong><span>Area: {selected.area ?? 'HCM demo'}</span><span>Order: {selected.orderId ?? '—'}</span><span>Driver: {selected.driverId ?? '—'}</span><span>ETA: demo +{selected.label.replace(/\D/g, '') || '0'} min</span><span>Late: 0</span><span>Source: {selected.source ?? '—'}</span><span>Status: {selected.status ?? 'ASSIGNED'}</span></> : <><MapPin size={16} /><span>Click a pin to inspect route state.</span></>}
      </div>
    </div>
  </section>;
}

function MapEmptyState({ message }: { message?: string }) {
  return <div className="map-empty-state" data-testid="map-empty-state"><MapPin size={22} /><strong>No route result yet</strong><span>{message ?? 'Choose a scenario and click Run.'}</span></div>;
}

function SvgSyntheticMap({ model, onSelectPoint }: { model: MapModel; selected: MapPoint | null; onSelectPoint: (point: MapPoint) => void }) {
  const project = useProjector(model.points);
  return <svg viewBox="0 0 900 520" role="img" aria-label="Synthetic dispatch routes with pickup and dropoff pins" data-testid="synthetic-route-map">
    <defs>
      <pattern id="map-grid" width="42" height="42" patternUnits="userSpaceOnUse"><path d="M 42 0 L 0 0 0 42" fill="none" stroke="rgba(148,163,184,.11)" strokeWidth="1" /></pattern>
      <filter id="pin-glow"><feGaussianBlur stdDeviation="4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
      <marker id="route-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#e5f5ff" opacity=".75" /></marker>
    </defs>
    <rect width="900" height="520" rx="26" fill="url(#map-grid)" />
    {model.routes.map((route) => {
      const d = route.points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${project(point).x} ${project(point).y}`).join(' ');
      return <g key={route.driverId}>
        <path className="map-route-line" d={d} fill="none" stroke="rgba(2,6,23,.85)" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
        <path d={d} fill="none" stroke={routeColor(route.driverId)} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={route.source.includes('LIVE') ? '10 10' : undefined} markerEnd="url(#route-arrow)" />
      </g>;
    })}
    {model.points.map((point) => {
      const pos = project(point);
      const color = routeColor(point.driverId ?? point.id);
      return <g className={`map-pin map-pin-${point.kind.toLowerCase()}`} data-testid="map-pin" key={point.id} transform={`translate(${pos.x} ${pos.y})`} onClick={() => onSelectPoint(point)} tabIndex={0} role="button" aria-label={`${point.kind} ${point.label}`}>
        <circle r={point.kind === 'DRIVER' ? 15 : 12} fill={point.kind === 'RESCUE' ? '#fb7185' : color} opacity=".22" filter="url(#pin-glow)" />
        <circle r={point.kind === 'DRIVER' ? 11 : 9} fill="#020617" stroke={point.kind === 'RESCUE' ? '#fb7185' : color} strokeWidth="3" />
        <text y="4" textAnchor="middle" fontSize="9" fontWeight="800" fill="#e5f5ff">{point.label.slice(0, 3)}</text>
      </g>;
    })}
  </svg>;
}

function MapLegend() {
  return <div className="map-legend" data-testid="map-legend"><strong>Legend</strong><span>🚗/T Driver</span><span>S Start</span><span>P Pickup</span><span>G Dropoff</span><span>! Rescue</span><span>Solid: IRX final</span><span>Dashed: live/baseline</span><span>Purple border: ML touched</span></div>;
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
