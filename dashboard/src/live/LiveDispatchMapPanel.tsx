import { useMemo, useState } from 'react';
import { MapPinned } from 'lucide-react';
import { LiveLeafletMap } from './LiveLeafletMap';
import { LiveSyntheticMap } from './LiveSyntheticMap';
import { toLiveMapModel } from './liveMapModel';
import type { LiveCycleResponse, LiveState } from './LiveDispatchDemoPage';

export function LiveDispatchMapPanel({ state, previousState, lastCycle }: { state: LiveState; previousState: LiveState | null; lastCycle: LiveCycleResponse | null }) {
  const [mode, setMode] = useState<'hcm' | 'synthetic'>('synthetic');
  const [showMlImpact, setShowMlImpact] = useState(true);
  const model = useMemo(() => toLiveMapModel(state, previousState, lastCycle), [state, previousState, lastCycle]);

  return <section className="live-panel live-map-panel" data-testid="live-dispatch-map-panel"><div className="panel-title"><h3><MapPinned size={16} />Live Dispatch Map</h3><span className="mini-badge">{model.summary.drivers} drivers · {model.summary.orders} orders · {model.summary.routes} routes</span></div><div className="live-map-toolbar"><button className={mode === 'hcm' ? 'active' : ''} type="button" onClick={() => setMode('hcm')}>HCM Map</button><button className={mode === 'synthetic' ? 'active' : ''} type="button" onClick={() => setMode('synthetic')}>Synthetic</button><button className={showMlImpact ? 'active' : ''} type="button" onClick={() => setShowMlImpact((value) => !value)}>Show ML Impact</button><span>Frozen {model.summary.frozenStops}</span><span>High risk {model.summary.highRiskOrders}</span></div>{model.warnings.map((warning) => <div className="map-warning" key={warning}>{warning}</div>)}<div className="live-map-canvas">{mode === 'hcm' ? <LiveLeafletMap model={model} showMlImpact={showMlImpact} /> : <LiveSyntheticMap model={model} showMlImpact={showMlImpact} />}<LiveMapLegend action={lastCycle?.greedRlAction ?? 'WAITING'} /></div></section>;
}

function LiveMapLegend({ action }: { action: string }) {
  return <div className="live-map-legend" data-testid="live-map-legend"><strong>ML Impact</strong><span>Driver: cyan</span><span>Pickup: blue P</span><span>Dropoff: green D</span><span>Frozen: gray lock border</span><span>High risk: red ring</span><span>RouteFinder: dashed candidate</span><span>Accepted ML top-K: purple glow</span><em>GreedRL: {action}</em></div>;
}

