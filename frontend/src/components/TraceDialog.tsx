import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, ArrowRight, Check, Play, ScanLine, X } from 'lucide-react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { formatNumber, percent } from '../services/api'
import { ScoreBreakdown } from './DecisionPanel'
import { TruthBoundary } from './ui'
import type { BandObservation } from '../types'

const stages = ['Previous observations', 'Activity probability', 'Model uncertainty', 'Memory & recurrence', 'Candidate windows', 'Decision scores', 'Selected bandwidth', 'Receiver retunes', 'Observation returned', 'Belief updated']
const descriptions = [
  'The policy begins with the observations returned by its previous scan. Everything outside that window remained unknown.',
  'The Beta-Bernoulli posterior estimates activity probability. It was captured before this decision received any new data.',
  'High uncertainty means the model has limited or stale evidence. A likely active band and an uncertain band are different things.',
  'Recurring observation patterns provide bounded soft evidence. Period estimates require at least four separated observed episodes.',
  'All legal actions are contiguous windows with exactly the receiver’s instantaneous bandwidth.',
  'Each contribution comes from observed evidence or known sensing costs. The composite score is an explainable research heuristic.',
  'The policy commits to this one window. It still has no access to the full environment.',
  'Changing windows consumes retune time and incurs a normalized switching cost. Both duel receivers obey this model.',
  'Only the selected bands return energy, a detector decision, and confidence. HIT is a detector output, not privileged truth.',
  'The returned observations update the model. Change detection can soften stale beliefs. The next decision uses this updated state.',
]

function ObservationTable({ values }: { values?: BandObservation[] }) {
  if (!values?.length) return <div className="note-box">Cold start. No prior observations. Every band begins with Beta(1, 1).</div>
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>Band</th><th>Energy</th><th>Detector output</th><th>Confidence</th></tr></thead><tbody>{values.map(v => <tr key={v.band}><td className="mono">B{v.band.toString().padStart(2, '0')}</td><td>{formatNumber(v.energy, 2)}</td><td><span className={`badge ${v.detected ? 'green' : 'neutral'}`}>{v.valid ? v.detected ? 'HIT' : 'MISS' : 'MISSING'}</span></td><td>{percent(v.confidence)}</td></tr>)}</tbody></table></div>
}

export function TraceDialog() {
  const current = useCurrentFrame()
  const [frame] = useState(current)
  const [stage, setStage] = useState(0)
  const s = useMission()
  const dialog = useRef<HTMLDialogElement>(null)
  const p = frame?.policies.magnts ?? Object.values(frame?.policies ?? {})[0]
  const previous = frame ? s.frames[frame.step - 1]?.policies[p?.algorithm ?? 'magnts'] : undefined
  useEffect(() => { const element = dialog.current; element?.showModal(); return () => element?.close() }, [])
  if (!p || !frame) return null
  return <dialog className="trace-dialog" ref={dialog} onCancel={s.closeTrace} onClose={s.closeTrace} aria-labelledby="trace-title">
    <div className="trace-heading"><div><span className="eyebrow accent"><ScanLine size={13} /> OBSERVATION → DECISION → LEARNING</span><h2 id="trace-title">Trace one decision</h2><p className="mono">{s.run?.id} · SLOT {frame.step} · POLICY {p.algorithm.toUpperCase()}</p></div><button className="icon-button" aria-label="Close decision trace" onClick={s.closeTrace}><X size={18} /></button></div>
    <div className="trace-progress">{stages.map((name, i) => <button aria-label={`Step ${i + 1}: ${name}`} className={i === stage ? 'active' : i < stage ? 'complete' : ''} key={name} onClick={() => setStage(i)}>{i < stage ? <Check size={12} /> : String(i + 1).padStart(2, '0')}</button>)}</div>
    <AnimatePresence mode="wait"><motion.div key={stage} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }} className="trace-content"><div className="trace-stage-title"><span>{String(stage + 1).padStart(2, '0')}</span><h3>{stages[stage]}</h3></div><p className="trace-description">{descriptions[stage]}</p>
      {stage === 0 && <ObservationTable values={previous?.observations.values} />}
      {(stage === 1 || stage === 2) && <div className="trace-band-grid">{(stage === 1 ? p.decision.pre_probability : p.decision.pre_uncertainty).map((value, band) => <div key={band} style={{ background: `rgba(${stage === 1 ? '175,213,134' : '160,144,212'},${0.08 + value * 0.65})` }}><small>B{band.toString().padStart(2, '0')}</small><strong>{percent(value, 0)}</strong></div>)}</div>}
      {stage === 3 && <div className="trace-evidence"><h4>Associative memory</h4>{p.decision.memory_matches.length ? p.decision.memory_matches.slice(0, 3).map(m => <div className="evidence-row" key={m.band}><strong>B{m.band}</strong><span>{percent(m.similarity, 0)} similarity · previous {m.previous_outcome} at slot {m.previous_step}</span><span className="accent">+{m.contribution.toFixed(3)}</span></div>) : <p className="muted">No sufficiently supported memory match at this step.</p>}<h4>Periodicity evidence</h4>{p.decision.periodic_candidates.length ? p.decision.periodic_candidates.slice(0, 3).map(e => <div className="evidence-row" key={e.band}><strong>B{e.band}</strong><span>{e.evidence_count} observed episodes · {e.period_slots}-slot estimate</span><span>{percent(e.confidence)} confidence</span></div>) : <p className="muted">Insufficient separated events to estimate a recurrence interval.</p>}</div>}
      {stage === 4 && <table className="data-table"><thead><tr><th>Window</th><th>p(active)</th><th>Uncertainty</th><th>Score</th></tr></thead><tbody>{p.decision.candidates.map(c => <tr key={c.start} className={c.selected ? 'selected-row' : ''}><td>B{c.start}–B{c.end}{c.selected && <Check size={13} />}</td><td>{percent(c.probability)}</td><td>{percent(c.uncertainty)}</td><td className="mono">{c.score.toFixed(4)}</td></tr>)}</tbody></table>}
      {stage === 5 && <ScoreBreakdown components={p.decision.components} />}
      {(stage === 6 || stage === 7) && <div className="trace-receiver"><div className="trace-window-label">B{p.selected_window.start} — B{p.selected_window.end}</div><div className="trace-spectrum"><motion.div initial={stage === 7 ? { left: `${(p.previous_window ?? 0) / p.belief.probability.length * 100}%` } : false} animate={{ left: `${p.selected_window.start / p.belief.probability.length * 100}%` }} transition={{ duration: 0.9 }} style={{ width: `${p.selected_window.width / p.belief.probability.length * 100}%` }} /></div><div className="trace-receiver-stats"><span>{p.selected_window.width} observable bands</span><span>Effective dwell <b>{p.observations.effective_dwell_ms.toFixed(1)} ms</b></span><span>Retune cost <b>{p.retune_cost.toFixed(3)}</b></span></div></div>}
      {stage === 8 && <ObservationTable values={p.observations.values} />}
      {stage === 9 && <div><table className="data-table"><thead><tr><th>Band</th><th>Prior probability</th><th>Evidence</th><th>Updated probability</th></tr></thead><tbody>{p.observations.values.map(v => <tr key={v.band}><td>B{v.band}</td><td>{percent(p.decision.pre_probability[v.band])}</td><td className={v.detected ? 'accent' : 'muted'}>{v.valid ? v.detected ? 'HIT' : 'MISS' : 'MISSING'}</td><td className="accent">{percent(p.belief.probability[v.band])}</td></tr>)}</tbody></table><div className="note-box">{p.belief.change_events.length ? `${p.belief.change_events.length} observation-driven change event(s) softened stale evidence.` : 'No distribution shift was flagged at this step.'}</div></div>}
    </motion.div></AnimatePresence>
    <TruthBoundary short />
    <div className="trace-footer"><button className="button secondary" disabled={stage === 0} onClick={() => setStage(stage - 1)}><ArrowLeft size={15} />Previous</button><span>{stage + 1} / {stages.length}</span>{stage < 9 ? <button className="button primary" onClick={() => setStage(stage + 1)}>Next step <ArrowRight size={15} /></button> : <button className="button primary" onClick={() => { s.closeTrace(); void s.resume() }}><Play size={15} />Continue simulation</button>}</div>
  </dialog>
}
