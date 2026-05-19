import 'leaflet/dist/leaflet.css';
import { useEffect } from 'react';
import L from 'leaflet';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip, useMap } from 'react-leaflet';
import type { LiveMapModel, LiveMapPoint } from './liveMapModel';

const HCM_CENTER: [number, number] = [10.7769, 106.7009];

export function LiveLeafletMap({ model, showMlImpact }: { model: LiveMapModel; showMlImpact: boolean }) {
  const points = [...model.drivers, ...model.pickups, ...model.dropoffs];
  return <div className="live-leaflet-shell" data-testid="live-leaflet-map"><MapContainer center={HCM_CENTER} zoom={12} scrollWheelZoom className="live-leaflet-map"><TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><FitBounds points={points} />{model.previousRoutes.map((route) => <Polyline key={route.id} positions={route.points.map(toLatLng)} pathOptions={{ color: '#64748b', weight: 4, opacity: .55, dashArray: '8 8' }} />)}{model.routes.map((route) => <Polyline key={route.id} positions={route.points.map(toLatLng)} pathOptions={{ color: route.mlTouched && showMlImpact ? '#a855f7' : routeColor(route.driverId), weight: route.mlTouched && showMlImpact ? 7 : 5, opacity: .88 }} />)}{points.map((point) => <CircleMarker key={point.id} center={toLatLng(point)} radius={radius(point)} pathOptions={{ color: border(point, showMlImpact), fillColor: fill(point), fillOpacity: .9, weight: point.frozen ? 5 : point.mlTouched && showMlImpact ? 4 : 2 }}><Tooltip direction="top" offset={[0, -8]} permanent className="irx-map-label">{point.kind === 'DRIVER' ? point.driverId : point.kind[0]}</Tooltip><Popup><PopupBody point={point} /></Popup></CircleMarker>)}</MapContainer></div>;
}

function FitBounds({ points }: { points: LiveMapPoint[] }) {
  const map = useMap();
  useEffect(() => { if (!points.length) return; map.fitBounds(L.latLngBounds(points.map(toLatLng)), { padding: [42, 42], maxZoom: 14 }); }, [map, points]);
  return null;
}

function PopupBody({ point }: { point: LiveMapPoint }) {
  return <div className="leaflet-popup-content-irx"><strong>{point.kind} · {point.label}</strong><span>Order: {point.orderId ?? '—'}</span><span>Driver: {point.driverId ?? '—'}</span><span>Status: {point.status ?? 'ACTIVE'}</span><span>Risk: {point.risk ?? 'LOW'}</span><span>Selected by: GreedRL + Tabular</span><span>RouteFinder candidate: {point.routefinderCandidate ? 'true' : 'false'}</span><span>Frozen: {point.frozen ? 'true' : 'false'}</span><span>Accepted: {point.accepted ? 'true' : 'false'}</span></div>;
}

function toLatLng(point: LiveMapPoint): [number, number] { return [point.lat, point.lng]; }
function radius(point: LiveMapPoint) { return point.kind === 'DRIVER' ? 10 : point.risk === 'HIGH' ? 9 : 7; }
function fill(point: LiveMapPoint) { if (point.kind === 'DRIVER') return '#22d3ee'; if (point.kind === 'PICKUP') return '#3b82f6'; return '#22c55e'; }
function border(point: LiveMapPoint, showMlImpact: boolean) { if (point.frozen) return '#94a3b8'; if (showMlImpact && point.mlTouched) return '#d8b4fe'; if (point.risk === 'HIGH') return '#fb7185'; return '#e5f5ff'; }
function routeColor(driverId: string) { return driverId.endsWith('2') ? '#34d399' : '#22d3ee'; }

