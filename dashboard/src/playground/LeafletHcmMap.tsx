import 'leaflet/dist/leaflet.css';
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';
import { useEffect } from 'react';
import L from 'leaflet';
import { HCM_CENTER, HCM_ZOOM } from './hcmDemoCoordinates';
import { routeColor, type MapModel, type MapPoint } from './playgroundMapModel';

export function LeafletHcmMap({ model, onSelectPoint }: { model: MapModel; onSelectPoint: (point: MapPoint) => void }) {
  return <div className="hcm-map-shell" data-testid="hcm-leaflet-map">
    <MapContainer center={HCM_CENTER} zoom={HCM_ZOOM} scrollWheelZoom className="hcm-map">
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <FitBounds points={model.points} />
      {model.routes.map((route) => <Polyline key={route.driverId} positions={route.points.map((point) => [point.lat, point.lng] as [number, number])} pathOptions={{ color: routeColor(route.driverId), weight: route.source.includes('RESCUE') ? 6 : 5, opacity: .86, dashArray: route.source.includes('LIVE') ? '10 10' : undefined }} />)}
      {model.points.map((point) => <CircleMarker key={point.id} center={[point.lat, point.lng]} radius={point.kind === 'DRIVER' || point.kind === 'DEPOT' ? 10 : 8} pathOptions={{ color: borderColor(point), fillColor: fillColor(point), fillOpacity: .92, weight: point.kind === 'RESCUE' ? 4 : 2 }} eventHandlers={{ click: () => onSelectPoint(point) }}>
        <Popup><MapPopup point={point} /></Popup>
      </CircleMarker>)}
    </MapContainer>
    <div className="hcm-route-note">Route geometry: straight-line visualization over Ho Chi Minh City demo coordinates.</div>
  </div>;
}

function FitBounds({ points }: { points: MapPoint[] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    const bounds = L.latLngBounds(points.map((point) => [point.lat, point.lng] as [number, number]));
    map.fitBounds(bounds, { padding: [42, 42], maxZoom: 13 });
  }, [map, points]);
  return null;
}

function MapPopup({ point }: { point: MapPoint }) {
  return <div className="leaflet-popup-content-irx">
    <strong>{point.kind} · {point.label}</strong>
    <span>{point.area ?? 'Ho Chi Minh City demo point'}</span>
    <span>Order: {point.orderId ?? '—'}</span>
    <span>Driver: {point.driverId ?? '—'}</span>
    <span>Source: {point.source ?? '—'}</span>
    <span>Status: {point.status ?? 'ASSIGNED'}</span>
  </div>;
}

function fillColor(point: MapPoint) {
  if (point.kind === 'RESCUE') return '#f97316';
  if (point.kind === 'DROPOFF') return '#020617';
  return routeColor(point.driverId ?? point.id);
}

function borderColor(point: MapPoint) {
  if (point.kind === 'RESCUE') return '#ef4444';
  if (point.source?.includes('Adaptive')) return '#c084fc';
  return routeColor(point.driverId ?? point.id);
}
