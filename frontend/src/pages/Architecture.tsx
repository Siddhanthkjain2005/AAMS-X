import { useEffect, useState } from 'react'
import { Activity, ArrowDown, ArrowRight, BrainCircuit, Database, Fingerprint, HardDrive, History, Layers3, Radio, ScanLine, ShieldCheck, Sparkles, Timer, Workflow } from 'lucide-react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { formatNumber } from '../services/api'
import { PageHeader, Panel, TruthBoundary } from '../components/ui'

const nodes = [
  { title: 'Data sources', icon: Database, description: 'Controlled seeded scenarios, authorized official radar PDWs, and public measured RF recordings carry explicit source categories.', file: 'backend/datasets/catalog.py' },
  { title: 'Ingest & normalize', icon: Layers3, description: 'Validate units and axes, retain missing data, preserve source features in Parquet, and produce a compact checksummed artifact.', file: 'backend/datasets/ingest.py' },
  { title: 'Spectrum environment', icon: Activity, description: 'An immutable, evaluation-owned time-frequency world. Independent receiver cursors share the identical energy and detector random fields.', file: 'backend/environment/spectrum.py' },
  { title: 'Receiver digital twin', icon: Radio, description: 'The contiguous bandwidth constraint is checked before sampling. Retuning and latency reduce usable dwell; energy drives detector output.', file: 'backend/receiver.py' },
  { title: 'Observation stream', icon: ScanLine, description: 'Only selected-band energy, detector output, confidence, noise estimate, and timing cross this boundary as frozen values.', file: 'backend/contracts.py · Observation' },
  { title: 'Bayesian belief engine', icon: BrainCircuit, description: 'Discounted Beta-Bernoulli evidence estimates occupancy and uncertainty. Unobserved bands age toward the weak prior rather than becoming misses.', file: 'backend/scheduler/belief.py' },
  { title: 'MAG-NTS scheduler', icon: Sparkles, description: 'Score legal windows using Thompson opportunity, information, uncertainty, memory, recurrence, change priority, and sensing costs.', file: 'backend/scheduler/policies.py' },
  { title: 'Selected window', icon: Radio, description: 'Commit to one contiguous window. The policy has not received the next observation or any out-of-window truth.', file: 'backend/contracts.py · Action' },
  { title: 'HIT / MISS observation', icon: Activity, description: 'The receiver samples the chosen bands from the shared energy realization. A HIT is a detector decision and may be a false alarm.', file: 'backend/environment/spectrum.py · step' },
  { title: 'Online update', icon: BrainCircuit, description: 'New evidence updates beliefs, records episodes, tests for change, and updates recurrence estimates. Then the sensing loop repeats.', file: 'backend/scheduler/policies.py · update' },
]
const modules = [
  { icon: History, title: 'Associative memory', text: 'Observed four-event contexts → subsequent outcomes. Similarity-weighted, bounded evidence.' },
  { icon: Activity, title: 'Change detector', text: 'Two-sided observation-time CUSUM softens stale confidence after a supported shift.' },
  { icon: Timer, title: 'Periodicity estimator', text: 'Four or more separated events, integer-multiple interval fit, phase and miss consistency.' },
  { icon: Sparkles, title: 'Information gain', text: 'Expected one-observation mutual information for the Beta-Bernoulli model.' },
]

export function Architecture() {
  const s = useMission()
  const frame = useCurrentFrame()
  const [selected, setSelected] = useState(4), [flow, setFlow] = useState<number | null>(null)
  useEffect(() => {
    if (flow === null) return
    setSelected(flow)
    if (flow >= nodes.length - 1) { const timer = setTimeout(() => setFlow(null), 1400); return () => clearTimeout(timer) }
    const timer = setTimeout(() => setFlow(flow + 1), 850)
    return () => clearTimeout(timer)
  }, [flow])
  const trace = async () => { await s.openTrace(); useMission.getState().closeTrace(); setFlow(0) }
  const p = frame?.policies.magnts
  const node = nodes[selected]
  const values = [s.run?.dataset.category, s.run?.dataset.artifact_sha256?.slice(0, 16) ?? 'Seeded world generation', s.run?.environment_hash.slice(0, 20), p ? `${p.selected_window.width} bands · ${p.observations.effective_dwell_ms.toFixed(1)} ms usable dwell` : undefined, p ? `${p.observations.values.length} selected-band values` : undefined, p ? `${p.belief.observations.reduce((a, b) => a + b, 0)} observations accumulated` : undefined, p ? `Decision score ${p.decision.score.toFixed(4)}` : undefined, p ? `B${p.selected_window.start}–B${p.selected_window.end}` : undefined, p ? `${p.hit_count} HIT · ${p.observations.values.filter(v => v.valid && !v.detected).length} MISS` : undefined, p ? `${p.belief.change_events.length} changes · ${p.belief.memory_size} memory episodes` : undefined]
  return <>
    <PageHeader eyebrow="SYSTEM DESIGN" title="The intelligence loop" description="A small, local architecture with a strict observation boundary and a fully auditable feedback loop." action={<button className="button primary" disabled={s.busy || flow !== null || !s.engine} onClick={() => void trace()}><Workflow size={16} />{flow !== null ? 'TRACING OBSERVATION…' : 'TRACE ONE DECISION'}</button>} />
    <TruthBoundary />
    <div className="architecture-layout"><Panel className="architecture-flow" title="From a wide spectrum to one next action" eyebrow="CLICK A BLOCK TO INSPECT ITS ROLE">
      <div className="flow-chain">{nodes.map((n, i) => <div key={n.title} className="flow-node-wrap"><button onClick={() => setSelected(i)} className={`flow-node ${selected === i ? 'selected' : ''} ${flow === i ? 'flow-active' : ''} ${i === 4 ? 'boundary-node' : ''}`}><span className="flow-number mono">{String(i + 1).padStart(2, '0')}</span><n.icon size={18} /><div><strong>{n.title}</strong><span>{i === 4 ? 'OBSERVATION-ONLY BOUNDARY' : i === 6 ? 'MEMORY + INFORMATION + CHANGE + RECURRENCE' : i === 2 ? 'TRUTH OWNED BY EVALUATION' : n.file.split('/').slice(-1)[0]}</span></div>{flow === i && <span className="flow-pulse" />}</button>{i < nodes.length - 1 && <div className={`flow-connector ${flow !== null && flow > i ? 'travelled' : ''}`}><ArrowDown size={14} /></div>}</div>)}</div><div className="loop-back"><ArrowRight size={16} /><span>Repeat with updated beliefs · one action at a time</span></div>
    </Panel><div className="architecture-side stack"><Panel title={node.title} eyebrow={`BLOCK ${String(selected + 1).padStart(2, '0')} · INSPECTOR`} action={<node.icon size={20} className="accent" />}><div className="architecture-inspector"><p>{node.description}</p><code>{node.file}</code><div className="live-evidence"><span className="eyebrow">CURRENT EXPERIMENT EVIDENCE</span><strong>{values[selected] ?? 'No run available'}</strong><span className="mono">{s.run?.id ?? 'Start a trace to observe a real decision'}{frame ? ` · SLOT ${frame.step}` : ''}</span></div><button className="button secondary small" disabled={!frame} onClick={() => void s.openTrace()}><ScanLine size={14} />Inspect the ten-step decision</button></div></Panel>
      <Panel title="Parallel intelligence modules" eyebrow="OBSERVATIONS IN · SOFT EVIDENCE OUT"><div className="module-list">{modules.map(m => <div key={m.title}><m.icon size={18} className="violet-text" /><div><h4>{m.title}</h4><p>{m.text}</p></div></div>)}</div></Panel>
      <Panel title="Independent evaluation path" eyebrow="PRIVILEGED · NEVER PASSED TO POLICY"><div className="evaluation-path"><ShieldCheck size={22} className="orange-text" /><span>Hidden truth</span><ArrowRight size={15} /><span>Metric engine<br /><small>Judge visualization</small></span></div><div className="registry-path"><HardDrive size={18} /><span>Experiment registry<br /><small>Config + seed + trace + checksums</small></span><Fingerprint size={19} /></div></Panel>
    </div></div>
    <Panel title="Memory-Augmented, Information-Guided, Non-Stationary Thompson Sampling" eyebrow="MAG-NTS · THE COMPOSITE DECISION"><div className="formula-strip"><span>Learned opportunity</span><b>+</b><span>Information & uncertainty</span><b>+</b><span>Memory & recurrence</span><b>+</b><span>Recency & change</span><b>−</b><span className="orange-text">Retuning & wasted scans</span></div><p className="method-note">Every component is observation-derived or a public receiver cost. Composite score weights are explicit research hyperparameters. There is no hardcoded threat score or performance guarantee. {p ? `Current chosen score: ${formatNumber(p.decision.score, 4)}.` : ''}</p></Panel>
  </>
}
