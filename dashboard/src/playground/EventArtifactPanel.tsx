import type { PlaygroundSnapshot } from './playgroundTypes';

export function EventArtifactPanel({ snapshot }: { snapshot: PlaygroundSnapshot }) {
  return <section className="playground-card event-artifact-panel" aria-label="Events and artifacts">
    <div className="playground-card-title"><span>Events & Artifacts</span><strong>{snapshot.events.length} events</strong></div>
    <div className="event-artifact-grid">
      <div>
        <h3>Event stream</h3>
        <div className="event-feed">
          {snapshot.events.slice(0, 8).map((event) => <div className="event-item" key={event.eventId}><span>{event.type}</span><small>{event.timestamp}</small></div>)}
          {snapshot.events.length === 0 && <p>No events yet.</p>}
        </div>
      </div>
      <div>
        <h3>Artifacts</h3>
        <div className="artifact-list">
          {snapshot.artifacts.slice(0, 6).map((artifact) => <a href={artifact.downloadUrl ?? `/api/v1/artifacts/${artifact.artifactId}/download`} key={artifact.artifactId}>{artifact.type ?? 'artifact'} · {artifact.artifactId}</a>)}
          {snapshot.artifacts.length === 0 && <p>No artifacts yet.</p>}
        </div>
      </div>
    </div>
  </section>;
}

