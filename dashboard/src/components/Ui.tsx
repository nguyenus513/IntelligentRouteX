import type { ReactNode } from 'react';

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function Kpi({ label, value, trend }: { label: string; value: string | number; trend?: string }) {
  return (
    <Card className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      {trend ? <em>{trend}</em> : null}
    </Card>
  );
}

export function Badge({ children, tone = '' }: { children: ReactNode; tone?: 'warn' | 'win' | 'danger' | '' }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <Card className="empty-state">
      <div className="eyebrow">Empty state</div>
      <h2>{title}</h2>
      <p className="muted">{detail}</p>
    </Card>
  );
}
