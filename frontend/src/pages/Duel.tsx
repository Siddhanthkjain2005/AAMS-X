import { useState } from 'react'
import { ArrowRight, Check, ChevronDown, Download, Equal, Info, Radio, Swords } from 'lucide-react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { formatNumber, metricNumber, percent } from '../services/api'
import type { Algorithm } from '../types'
import { ExperimentControls, TransportBar } from '../components/Controls'
import { DecisionPanel } from '../components/DecisionPanel'
import { Metric, PageHeader, Panel, SourceBadge, TruthBoundary } from '../components/ui'
import { SpectrumStrip, Waterfall, WaterfallLegend } from '../visualizations/Waterfall'
import { InterceptTrend } from '../charts/Trends'
import { BeliefMap } from '../visualizations/BeliefMap'

function ReceiverCard({ algorithm }: { algorithm: Algorithm }) {
  const frame = useCurrentFrame()
  const run = useMission(s => s.run)
  const p = frame?.policies[algorithm]
  const baseline = algorithm === 'fixed'
  const r = run?.config.receiver
  const min = r && p ? r.frequency_min_mhz + p.selected_window.start / r.bands * (r.frequency_max_mhz - r.frequency_min_mhz) : null
  const max = r && p ? r.frequency_min_mhz + (p.selected_window.end + 1) / r.bands * (r.frequency_max_mhz - r.frequency_min_mhz) : null
  return <Panel className={`receiver-card ${baseline ? 'fixed-receiver' : 'adaptive-receiver'}`}>
    <div className="receiver-title"><div className={`receiver-icon ${baseline ? 'baseline' : ''}`}><Radio size={21} strokeWidth={1.5} /></div><div><span className="eyebrow">{baseline ? 'OPEN-LOOP BASELINE' : 'OBSERVATION-DRIVEN POLICY'}</span><h2>{baseline ? 'Fixed Sweep' : 'AAMS-X'}{!baseline && <span className="policy-tag">MAG-NTS</span>}</h2></div><span className={`badge ${baseline ? 'neutral' : 'green'}`}>{baseline ? 'SEQUENTIAL' : p?.decision.exploration ? 'EXPLORING' : 'ADAPTIVE'}</span></div>
    <div className="receiver-window"><div><span className="eyebrow">CURRENT WINDOW</span><strong className="mono">{p ? `B${p.selected_window.start.toString().padStart(2, '0')} — B${p.selected_window.end.toString().padStart(2, '0')}` : '— — —'}</strong></div><span>{min !== null && max !== null ? `${min.toFixed(0)}–${max.toFixed(0)} MHz` : 'Waiting for acquisition'}</span></div>
    <SpectrumStrip algorithm={algorithm} /><Waterfall algorithm={algorithm} height={275} /><WaterfallLegend />
    <div className="receiver-metrics"><Metric label="Cumulative true detections" value={formatNumber(p?.metrics.true_positives)} accent={!baseline} /><Metric label="Global interception share" value={percent(p?.metrics.recall)} accent={!baseline} /><Metric label="Missed active cells" value={formatNumber(p?.metrics.missed_active_cells)} /><Metric label="Average intercept delay" value={formatNumber(p?.metrics.avg_intercept_time_ms, 0)} unit="ms" detail="Conditional on intercepted episodes" /><Metric label="Retunes" value={formatNumber(p?.metrics.retune_count)} /><Metric label="Reward / cost" value={formatNumber(p?.metrics.reward_cost, 3)} /></div>
    <div className="receiver-caption"><span className={`tiny-dot ${baseline ? '' : 'green'}`} />{p ? baseline ? 'Predetermined path · observations do not alter the next window' : p.decision.reasons[0] : 'No result has been computed yet'}</div>
  </Panel>
}

export function Duel() {
  const s = useMission()
  const frame = useCurrentFrame()
  const [setup, setSetup] = useState(!s.run)
  const [metric, setMetric] = useState('recall')
  const fixed = frame?.policies.fixed?.metrics, adaptive = frame?.policies.magnts?.metrics
  const simulated = (s.run?.config ?? s.config).dataset_id === 'simulation'
  const scenarioLabel = simulated
    ? s.scenarios.find(v => v.id === (s.run?.config.scenario ?? s.config.scenario))?.name ?? 'Sudden Appearance'
    : s.run?.dataset.name ?? s.datasets.find(d => d.id === s.config.dataset_id)?.name ?? 'Recorded spectrum'
  const comparisons = [
    { key: 'recall', label: 'Interception share', fraction: true, lower: false },
    { key: 'pd', label: 'Detection probability', fraction: true, lower: false },
    { key: 'avg_intercept_time_ms', label: 'Intercept delay', fraction: false, lower: true },
    { key: 'reward_cost', label: 'Reward / cost', fraction: false, lower: false },
  ]
  return <>
    <PageHeader eyebrow="CONTROLLED COMPARISON" title="AAMS-X vs Open-Loop" description="Two receivers. The exact same hidden environment. Every advantage measured." action={<button className="button primary" disabled={s.busy || !s.engine} onClick={() => { setSetup(false); void s.start({ ...s.config, algorithms: ['fixed', 'magnts'] }) }}><Swords size={16} />{s.busy ? 'Preparing…' : 'RUN FAIR DUEL'}<ArrowRight size={15} /></button>} />
    <div className="fairness-bar"><div><Equal size={17} /><strong>FAIR BY CONSTRUCTION</strong></div><span><Check size={13} />{s.run?.dataset.ground_truth === false ? 'Same recording' : 'Same truth'}</span><span><Check size={13} />Same receiver</span><span><Check size={13} />Same noise</span><span><Check size={13} />Same horizon</span><button className="text-button" onClick={() => setSetup(!setup)}>Configure <ChevronDown size={14} /></button></div>
    {setup && <ExperimentControls compact />}
    <div className="run-identity"><div><span className="eyebrow">{simulated ? 'SCENARIO' : 'RECORDING'}</span><strong>{scenarioLabel}</strong></div><div><span className="eyebrow">SEED</span><strong className="mono">{s.run?.config.seed ?? s.config.seed}</strong></div><div><span className="eyebrow">ENVIRONMENT</span><span className="mono">{s.run?.environment_hash.slice(0, 16) ?? 'Created on start'}</span></div><div><span className="eyebrow">DATA SOURCE</span><SourceBadge category={s.run?.dataset.category ?? s.datasets.find(d => d.id === s.config.dataset_id)?.category} compact /></div><span className="reproducible-tag"><span className="tiny-dot green" />REPRODUCIBLE EXPERIMENT</span></div>
    <TransportBar />
    <div className="duel-grid"><ReceiverCard algorithm="fixed" /><div className="duel-divider"><span>VS</span></div><ReceiverCard algorithm="magnts" /></div>
    <div className="duel-analysis-grid"><Panel title="Performance, as it happens" eyebrow="CUMULATIVE COMPARISON" action={<select aria-label="Comparison chart metric" className="compact-select" value={metric} onChange={e => setMetric(e.target.value)}><option value="recall">Interception share</option><option value="pd">Detection probability</option><option value="reward_cost">Reward / cost</option></select>}><div className="chart-legend trend-legend"><span><i className="legend-dot green" />AAMS-X / MAG-NTS</span><span><i className="legend-dot slate" />Fixed Sweep</span></div><InterceptTrend metric={metric} height={220} /></Panel><Panel title="Measured deltas" eyebrow="AAMS-X MINUS FIXED SWEEP" action={<button className="icon-button" aria-label="Read metric methodology" onClick={() => s.navigate('methodology')}><Info size={16} /></button>}><div className="delta-table"><div className="delta-table-head"><span>METRIC</span><span>FIXED</span><span>AAMS-X</span><span>DELTA</span></div>{comparisons.map(item => { const a = metricNumber(adaptive, item.key), f = metricNumber(fixed, item.key); const delta = a !== null && f !== null ? a - f : null; const positive = delta !== null && (item.lower ? delta < 0 : delta > 0); return <div className="delta-row" key={item.key}><span>{item.label}</span><span className="mono">{item.fraction ? percent(f) : formatNumber(f, item.lower ? 0 : 2)}</span><span className="mono">{item.fraction ? percent(a) : formatNumber(a, item.lower ? 0 : 2)}</span><strong className={`mono ${delta === null || delta === 0 ? 'muted' : positive ? 'accent' : 'orange-text'}`}>{delta === null ? '—' : `${delta > 0 ? '+' : ''}${(delta * (item.fraction ? 100 : 1)).toFixed(item.lower ? 0 : 1)}${item.fraction ? ' pp' : item.lower ? ' ms' : ''}`}</strong></div> })}</div><p className="delta-note">Results are generated from this run. Adaptive scheduling can improve allocation; no policy is guaranteed to win every scenario.</p><div className="experiment-export"><span className="mono">{s.run?.id ?? 'NO RUN AVAILABLE'}</span>{s.run && <a href={`/api/experiment/${s.run.id}/export?format=csv`} className="text-button"><Download size={13} />Export CSV</a>}</div></Panel></div>
    <div className="command-main-grid"><Panel title="Where the adaptive policy sees value" eyebrow="LEARNED BELIEFS"><BeliefMap expanded /></Panel><DecisionPanel compact /></div>
    {s.run?.dataset.ground_truth === false && <p className="note-box">N/A — no labelled emitter ground truth in this measured dataset. Coverage and observed energy events remain available in AI Observability.</p>}
    <TruthBoundary />
  </>
}
