import L from 'leaflet';
import { MapContainer, Marker, Polyline, Popup, TileLayer } from 'react-leaflet';
import type { DriverDto, OrderDto, RouteVisualizationDto } from '../types/dispatch';

const hcm: [number, number] = [10.7769, 106.7009];

function icon(className: string, label: string) {
  return L.divIcon({ className: '', html: `<div class="${className}">${label}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] });
}

interface Props {
  orders: OrderDto[];
  drivers: DriverDto[];
  routes: RouteVisualizationDto[];
  selectedRouteId?: string;
  splitRoutes?: RouteVisualizationDto[];
  mode?: 'single' | 'split' | 'overlay';
}

export function ControlMap({ orders, drivers, routes, selectedRouteId, splitRoutes = [], mode = 'single' }: Props) {
  const visibleOrders = orders.length > 140 ? orders.slice(0, 140) : orders;
  const visibleRoutes = selectedRouteId ? routes.filter((route) => route.routeId === selectedRouteId) : routes.slice(0, mode === 'overlay' ? 3 : 8);
  const routeSet = mode === 'split' ? [...visibleRoutes, ...splitRoutes.slice(0, 3)] : visibleRoutes;

  return (
    <MapContainer center={hcm} zoom={12} zoomControl={false}>
      <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {visibleOrders.map((order) => (
        <Marker key={`${order.orderId}-p`} position={[order.pickupLat, order.pickupLng]} icon={icon('marker-pickup', 'P')}>
          <Popup>{order.orderId} pickup • deadline {order.deadlineMinutes}m</Popup>
        </Marker>
      ))}
      {visibleOrders.slice(0, 80).map((order) => (
        <Marker key={`${order.orderId}-d`} position={[order.dropoffLat, order.dropoffLng]} icon={icon('marker-drop', 'D')}>
          <Popup>{order.orderId} dropoff</Popup>
        </Marker>
      ))}
      {drivers.map((driver) => (
        <Marker key={driver.driverId} position={[driver.lat, driver.lng]} icon={icon('marker-driver', 'M')}>
          <Popup>{driver.driverId} • load {driver.currentLoad}/{driver.capacity}</Popup>
        </Marker>
      ))}
      {routeSet.map((route, index) => (
        <Polyline
          key={`${route.routeId}-${index}`}
          positions={route.polyline.map((point) => [point.lat, point.lng])}
          pathOptions={{
            color: ['#22d3ee', '#34d399', '#f59e0b', '#f472b6'][index % 4],
            weight: route.routeId === selectedRouteId ? 7 : 4,
            opacity: route.routeId === selectedRouteId ? 0.95 : 0.5,
            dashArray: route.oldRouteId ? '8 8' : undefined
          }}
        />
      ))}
    </MapContainer>
  );
}
