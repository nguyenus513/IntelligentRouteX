import { AlertTriangle, CheckCircle2, Loader2, Server } from 'lucide-react';
import type { ApiHealthSnapshot } from './playgroundTypes';

export function ApiHealthBadge({ health, onRefresh }: { health: ApiHealthSnapshot; onRefresh: () => void }) {
  const icon = health.state === 'checking' ? <Loader2 size={15} className="spin" /> : health.state === 'online' ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />;
  return <button className={`api-health-badge ${health.state}`} onClick={onRefresh} type="button" aria-label="Refresh API health">
    {icon}
    <span><strong>API</strong>{health.message}</span>
    <small><Server size={12} />{health.apiBase}</small>
  </button>;
}
