import { useEffect, useState } from 'react'
import { BrainCircuit, History, Radio, RotateCcw, ShieldCheck, Sparkles, TrendingUp } from 'lucide-react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { api, formatNumber, percent } from '../services/api'
import { Metric, PageHeader, Panel, TruthBoundary } from '../components/ui'
import { BeliefMap } from '../visualizations/BeliefMap'
import { useVisibleFrames } from '../hooks/useVisibleFrames'
import { DecisionPanel } from '../components/DecisionPanel'
import { TransportBar } from '../components/Controls'

export function ActivityTimeline() {
  const { run, judge } = useMission()
  const frame = useCurrentFrame()
  const frames = useVisibleFrames()
  const [tracks, setTracks] = useState<{ id: string; kind: string; start: number; stop: number; cells: number[][] }[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    if (!judge || !run) return
    let active = true
    void api<{ tracks: typeof tracks }>(`/api/experiment/${run.id}/evaluation?judge=true`).then(r => { if (active) { setTracks(r.tracks); setError('') } }).catch(e => { if (active) setError(String(e)) })
    return () => { active = false }
  }, [judge, run?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  return <Panel title="Activity source timeline" eyebrow="EVALUATION-ONLY SOURCE TRACKS" action={<span className="badge orange">JUDGE VIEW</span>}>
    {!judge ? <div className="note-box"><ShieldCheck size={17} /><span>Source tracks are hidden. Enable Ground truth to inspect source activity and detection overlap.</span></div> : !tracks.length ? <div className="note-box">{error || 'This recording has no materialized labelled source tracks. Band-occupancy metrics and available PDW metadata are shown separately.'}</div> : <div className="activity-timeline">{tracks.map(track => {
      const data = track.cells.filter((_, i) => i % Math.max(1, Math.ceil(track.cells.length / 250)) === 0)
      return <div className="activity-track" key={track.id}><div><strong>{track.id}</strong><span>{track.kind}</span></div><svg viewBox="0 0 600 34" role="img" aria-label={`${track.id}, ${track.kind}, starts at slot ${track.start}, stops at ${track.stop}`}><line x1="0" y1="32" x2="600" y2="32" stroke="#2b3340" />{data.map(([time, band, width]) => { const hit = frames[time]?.policies.magnts?.evaluation?.true_hits.some(b => b >= band && b < band + width); return <rect key={`${time}-${band}`} x={time / (run?.config.horizon ?? 360) * 600} y={26 - band / (run?.config.receiver.bands ?? 48) * 22} width={Math.max(1.5, 600 / (run?.config.horizon ?? 360))} height="4" rx="1" fill={time > (frame?.step ?? -1) ? '#3a4252' : hit ? '#c0e88c' : '#cd946f'} /> })}<line x1={(frame?.step ?? 0) / (run?.config.horizon ?? 360) * 600} y1="0" x2={(frame?.step ?? 0) / (run?.config.horizon ?? 360) * 600} y2="34" stroke="#b7c0d1" strokeDasharray="2 3" /></svg><span className="mono">{track.start}–{track.stop}</span></div>})}<div className="chart-legend"><span><i className="legend-dot green" />Detected overlap</span><span><i className="legend-dot orange" />Missed activity</span><span><i className="legend-dot slate" />Future scenario activity</span></div></div>}
  </Panel>
}

export function Knowledge() {
  const s = useMission()
  const frame = useCurrentFrame()
  const frames = useVisibleFrames()
  const p = frame?.policies.magnts
  const changes = frames.flatMap(f => f.policies.magnts?.belief.change_events ?? []).slice(-8).reverse()
  return <>
    <PageHeader eyebrow="AI OBSERVABILITY" title="What the AI knows" description="Inspect learned probability, uncertainty, recalled patterns, and the evidence behind each action." action={<button className="button secondary" disabled={!s.run} onClick={() => void s.reset()}><RotateCcw size={15} />Reset to uninformative priors</button>} />
    <TruthBoundary /><TransportBar />
    <div className="metric-cards"><Panel><Metric label="Bands observed" value={p ? p.belief.observations.filter(n => n > 0).length : '—'} unit={`/ ${s.run?.config.receiver.bands ?? s.config.receiver.bands}`} detail="Unobserved bands retain uncertainty" /></Panel><Panel><Metric label="Band coverage" value={percent(p?.metrics.coverage)} detail="Valid receiver observations only" accent /></Panel><Panel><Metric label="Observed energy events" value={formatNumber(p?.metrics.observed_energy_events)} detail="Available even without truth labels" /></Panel><Panel><Metric label="Memory episodes" value={p ? p.belief.memory_size : '—'} detail="Bounded observation-pattern memory" /></Panel></div>
    <Panel title="Internal spectrum model" eyebrow="UPDATED FROM HITS AND MISSES"><BeliefMap expanded /></Panel>
    <div className="command-main-grid"><div className="stack"><Panel title="Similar patterns recalled" eyebrow="ASSOCIATIVE MEMORY" action={<History size={18} className="violet-text" />}>
      {p?.decision.memory_matches.length ? <div className="memory-list">{p.decision.memory_matches.map(m => <div className="memory-item" key={m.band}><div className="memory-region"><BrainCircuit size={16} /><strong>B{m.band.toString().padStart(2, '0')}</strong><span className="badge violet">{percent(m.similarity, 0)} MATCH</span></div><div className="memory-pattern">{m.pattern.map((hit, i) => <span key={i} className={hit ? 'hit' : ''}>{hit ? 'H' : 'M'}</span>)}<span className="pattern-arrow">→</span><span className={m.previous_outcome === 'HIT' ? 'hit' : ''}>{m.previous_outcome}</span></div><p>Recalled from slot {m.previous_step}. {m.support} similar past contexts; {percent(m.expected_hit, 0)} observed next-visit hit rate.</p><span className="memory-contribution">Soft score contribution <b>+{m.contribution.toFixed(3)}</b></span></div>)}</div> : <div className="note-box">No supported pattern recall yet. Episodes are formed from four past observations and a subsequent observed outcome.</div>}
    </Panel><Panel title="Distribution shifts" eyebrow="OBSERVATION-TIME CUSUM" action={<TrendingUp size={18} className="orange-text" />}><div className="change-list">{changes.length ? changes.map((e, i) => <div key={`${e.step}-${e.band}-${i}`}><span className="change-mark" /><div><strong>B{e.band.toString().padStart(2, '0')} · {e.direction}</strong><p>Slot {e.step} · CUSUM {e.score.toFixed(2)} · stale belief softened</p></div><Sparkles size={14} /></div>) : <p className="muted">No supported distribution shift has been flagged. Changes require observed evidence, not simulator announcements.</p>}</div></Panel></div><DecisionPanel /></div>
    <div className="two-column"><Panel title="Observed window history" eyebrow="THE ACTUAL SENSING BUDGET" action={<Radio size={17} />}><div className="window-history">{frames.slice(-80).map(f => { const window = f.policies.magnts?.selected_window; return window && <button key={f.step} title={`Slot ${f.step}: bands ${window.start}–${window.end}`} onClick={() => void s.inspect(f.step)} style={{ '--position': `${window.start / (s.run?.config.receiver.bands ?? 48) * 100}%`, '--width': `${window.width / (s.run?.config.receiver.bands ?? 48) * 100}%` } as React.CSSProperties}><span /><small>{f.step}</small></button> })}</div>{!frames.length && <p className="note-box">No observed windows yet.</p>}</Panel><Panel title="Policy input contract" eyebrow="FROZEN · WINDOW-BOUNDED"><div className="contract-code"><span className="code-comment">// Only this selected-window observation crosses the boundary</span><pre>{p ? JSON.stringify({ step: frame?.step, bands: p.observations.values.map(v => v.band), energy: p.observations.values.map(v => v.energy), detections: p.observations.values.map(v => v.detected), effective_dwell_ms: p.observations.effective_dwell_ms }, null, 2) : 'Observation {\n  step, selected_window,\n  values: [band, energy, detected, confidence],\n  effective_dwell_ms, retune_cost\n}'}</pre></div></Panel></div>
    <ActivityTimeline />
  </>
}
