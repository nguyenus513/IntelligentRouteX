import type { PlaygroundSnapshot } from './playgroundTypes';

export function RawJsonPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  return <section className="playground-card raw-json-panel" aria-label="Raw JSON">
    <div className="playground-card-title"><span>Raw JSON</span><strong>Last response</strong></div>
    <pre>{JSON.stringify(snapshot.raw.result ?? snapshot.raw.lastResponse ?? snapshot, null, 2)}</pre>
  </section>;
}

