import type { ReactNode } from 'react'
import { ArrowUpRight, Radio, ShieldCheck } from 'lucide-react'
import type { Category } from '../types'
import { useMission } from '../stores/mission'

export function Panel({ title, eyebrow, action, children, className = '' }: { title?: string; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>
    {(title || eyebrow) && <div className="panel-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}{title && <h3>{title}</h3>}</div>{action}</div>}
    {children}
  </section>
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow accent">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>
}

export function SourceBadge({ category, compact = false }: { category?: Category; compact?: boolean }) {
  const labels = { CONTROLLED_SIMULATION: compact ? 'SIMULATION' : 'CONTROLLED SIMULATION', OFFICIAL_SYNTHETIC_RADAR: compact ? 'OFFICIAL SYNTHETIC' : 'OFFICIAL SYNTHETIC DATA', REAL_MEASURED_RF: compact ? 'MEASURED RF' : 'REAL MEASURED RF DATA' }
  return <span className={`badge source-${category ?? 'none'}`}><span className="tiny-dot" />{category ? labels[category] : 'NO SOURCE SELECTED'}</span>
}

export function Metric({ label, value, unit, detail, accent = false }: { label: string; value: ReactNode; unit?: string; detail?: ReactNode; accent?: boolean }) {
  return <div className={`metric ${accent ? 'metric-accent' : ''}`}><span className="metric-label">{label}</span><div className="metric-value">{value}{unit && <small>{unit}</small>}</div>{detail && <div className="metric-detail">{detail}</div>}</div>
}

export function EmptyState({ title = 'No run available', description = 'Start a reproducible experiment to see observations and measured results.', action = true }: { title?: string; description?: string; action?: boolean }) {
  const start = useMission(s => s.start)
  const busy = useMission(s => s.busy)
  const engine = useMission(s => s.engine)
  return <div className="empty-state"><div className="empty-icon"><Radio size={25} strokeWidth={1.4} /></div><h3>{title}</h3><p>{description}</p>{action && <button className="button secondary small" disabled={busy || !engine} onClick={() => void start()}>Start live experiment <ArrowUpRight size={15} /></button>}</div>
}

export function TruthBoundary({ short = false }: { short?: boolean }) {
  return <div className="truth-boundary"><ShieldCheck size={16} /><span>{short ? 'Observation-only policy · evaluation truth isolated' : 'Scheduler input: observations only. Hidden truth unavailable to policy.'}</span><span className="boundary-label">ENFORCED CONTRACT</span></div>
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return <label className="toggle-label"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} /><span className="toggle-track" /><span>{label}</span></label>
}
