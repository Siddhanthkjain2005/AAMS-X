import { useState } from 'react'
import { Activity, ArrowRight, ArrowUpRight, AudioLines, Box, BrainCircuit, Check, ChevronRight, Database, Fingerprint, History, Play, Radio, ScanLine, ShieldCheck, Sparkles } from 'lucide-react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { formatNumber, percent } from '../services/api'
import { DecisionPanel } from '../components/DecisionPanel'
import { ExperimentControls, TransportBar } from '../components/Controls'
import { ProblemVisual } from '../components/ProblemVisual'
import { Metric, PageHeader, Panel, SourceBadge, TruthBoundary } from '../components/ui'
import { BeliefMap } from '../visualizations/BeliefMap'
import { SpectrumStrip, Waterfall, WaterfallLegend } from '../visualizations/Waterfall'
import { InterceptTrend } from '../charts/Trends'
import './command-upgrade.css'

function showBriefing() {
  try { return localStorage.getItem('aams-briefing-seen') !== 'yes' }
  catch { return true }
}

export function Command() {
  const s = useMission()
  const frame = useCurrentFrame()
  const policy = frame?.policies.magnts
  const receiver = s.run?.config.receiver ?? s.config.receiver
  const [briefing, setBriefing] = useState(showBriefing)
  const source = s.datasets.find(d => d.id === s.config.dataset_id)
  const recordings = s.history.filter(run => run.step > 0 && ['completed', 'cancelled'].includes(run.state)).slice(0, 3)
  const scenarioName = (id: string) => s.scenarios.find(scenario => scenario.id === id)?.name ?? id.replaceAll('_', ' ')
  const completedSlots = s.run ? s.mode === 'REPLAY' ? (frame?.step ?? -1) + 1 : s.run.step : 0
  const progress = s.run ? Math.min(100, completedSlots / s.run.config.horizon * 100) : 0
  const dismissBriefing = () => {
    setBriefing(false)
    try { localStorage.setItem('aams-briefing-seen', 'yes') } catch { /* The briefing also works without browser storage. */ }
  }
  const openRecording = async (id: string) => {
    await s.loadReplay(id)
    if (useMission.getState().run?.id === id && useMission.getState().mode === 'REPLAY') s.navigate('duel')
  }

  return <div className="command-page">
    <PageHeader eyebrow="MISSION CONTROL" title="Command Center" description="A live workspace for understanding how adaptive sensing makes its next decision." action={<span className="badge neutral"><span className={`tiny-dot ${s.engine ? 'green' : ''}`} />{s.run ? `${s.mode} · ${s.run.state.toUpperCase()}` : s.engine ? 'READY TO EXPLORE' : 'ENGINE OFFLINE'}</span>} />

    {!s.run ? <section className="mission-hero command-hero">
      <div className="hero-copy">
        <span className="hero-tag"><span className="tiny-dot green" /> AAMS-X RESEARCH WORKSPACE <span className="hero-tag-rule" /> OBSERVE. LEARN. ADAPT.</span>
        <h2>A wider spectrum.<br />A smarter <em>next move.</em></h2>
        <p>One receiver. A limited view. Watch an adaptive policy learn from every observation, then follow the evidence behind its next move.</p>
        <div className="button-row">
          <button className="button primary hero-cta" disabled={s.busy || !s.engine} onClick={() => void s.start()}><Play size={15} fill="currentColor" /> {s.busy ? 'PREPARING DEMO…' : 'START LIVE DEMO'} <ArrowUpRight size={16} /></button>
          <button className="text-button hero-secondary" onClick={() => s.navigate('architecture')}>How it works <ArrowRight size={15} /></button>
        </div>
        <div className="hero-footnote"><ShieldCheck size={14} />Observation-only decisions. Every step inspectable.</div>
      </div>
      <ProblemVisual expanded={briefing} />
      <div className="hero-source-line"><div><span className="eyebrow">NEXT EXPERIMENT</span><strong>{source?.name ?? (s.config.dataset_id === 'simulation' ? 'Controlled RF environment' : 'Waiting for source catalog')}</strong></div><SourceBadge category={source?.category} compact /><span className="mono">SEED {s.config.seed} <span>·</span> {s.config.horizon} SLOTS</span></div>
    </section> : <section className="command-session" aria-label="Current experiment overview">
      <div className="session-mark"><Activity size={23} /></div>
      <div className="session-copy"><span className="eyebrow">{s.mode === 'REPLAY' ? 'EXPLORING A RECORDING' : 'CURRENT EXPERIMENT'}</span><h2>{s.run.config.dataset_id === 'simulation' ? scenarioName(s.run.config.scenario) : s.run.dataset.name}</h2><p><SourceBadge category={s.run.dataset.category} compact /><span className="mono">Seed {s.run.config.seed} · {s.run.id}</span></p></div>
      <div className="session-progress"><div><span>{s.mode === 'REPLAY' ? 'Replay position' : 'Experiment progress'}</span><strong>{completedSlots} <span>/ {s.run.config.horizon} slots</span></strong></div><div className="session-progress-track" role="progressbar" aria-label="Experiment progress" aria-valuemin={0} aria-valuemax={s.run.config.horizon} aria-valuenow={Math.min(completedSlots, s.run.config.horizon)}><span style={{ width: `${progress}%` }} /></div></div>
      <button className="button secondary small" onClick={() => s.navigate('duel')}>Open Fair Duel <ArrowUpRight size={14} /></button>
    </section>}

    {!s.run && briefing && <section className="command-onboarding" aria-label="Demo guide">
      <div className="onboarding-intro"><Sparkles size={16} /><span>A first look,<br /><strong>in three steps.</strong></span></div>
      <div className="onboarding-step"><span className="step-number">01</span><div><strong>Start a fair comparison</strong><p>Two policies observe the same world.</p></div></div>
      <ChevronRight size={15} className="onboarding-chevron" />
      <div className="onboarding-step"><span className="step-number">02</span><div><strong>Pause at an interesting moment</strong><p>Inspect the evidence for any decision.</p></div></div>
      <ChevronRight size={15} className="onboarding-chevron" />
      <div className="onboarding-step"><span className="step-number">03</span><div><strong>Follow the learning</strong><p>Explore beliefs, memory, and outcomes.</p></div></div>
      <button className="onboarding-dismiss" aria-label="Dismiss demo guide" title="Dismiss demo guide" onClick={dismissBriefing}><Check size={15} /></button>
    </section>}

    <div className="mission-stat-grid">
      <Panel className="mission-stat"><div className="stat-icon"><Radio size={19} /></div><div><span className="eyebrow">RECEIVER BANDWIDTH</span><strong>{receiver.window_width}<span> / {receiver.bands} bands</span></strong><p>{percent(receiver.window_width / receiver.bands)} of the spectrum in each scan</p></div><div className="micro-bandwidth"><i style={{ width: percent(receiver.window_width / receiver.bands) }} /></div></Panel>
      <Panel className="mission-stat"><div className="stat-icon violet-text"><BrainCircuit size={19} /></div><div><span className="eyebrow">ADAPTIVE POLICY</span><strong>MAG-NTS</strong><p>Learns online from partial observations</p></div><span className="stat-corner-label">EXPLAINABLE</span></Panel>
      <Panel className="mission-stat"><div className="stat-icon"><Database size={19} /></div><div><span className="eyebrow">DATA CATALOG</span><strong>{s.engine ? s.datasets.filter(d => d.status === 'available').length : '—'}<span> sources ready</span></strong><p>Inspect source details and transformations</p></div><button className="stat-link" aria-label="Open data provenance" onClick={() => s.navigate('provenance')}><ArrowUpRight size={17} /></button></Panel>
    </div>

    {!s.run && recordings.length > 0 && <section className="command-recordings" aria-label="Saved demo recordings">
      <div className="recordings-heading"><History size={17} /><div><h3>Pick up a recorded experiment</h3><p>Saved observations. Ready to pause, replay, and inspect.</p></div><span className="recordings-count">{recordings.length} READY TO EXPLORE</span></div>
      <div className="recording-cards">{recordings.map(run => <button className="recording-card" key={run.id} disabled={s.busy} onClick={() => void openRecording(run.id)} aria-label={`Open recorded ${run.config.dataset_id === 'simulation' ? scenarioName(run.config.scenario) : run.dataset.name} experiment, seed ${run.config.seed}`}><span className="recording-play"><Play size={13} fill="currentColor" /></span><span className="recording-copy"><strong>{run.config.dataset_id === 'simulation' ? scenarioName(run.config.scenario) : run.dataset.name}</strong><span className="recording-detail">{run.step} slots <i /> Seed {run.config.seed} <i /> {run.state === 'completed' ? 'Complete' : 'Partial'}</span></span><ArrowUpRight size={15} /><SourceBadge category={run.dataset.category} compact /></button>)}</div>
    </section>}

    <div className="command-section-heading"><div><span className="eyebrow">THE WORKSPACE</span><h2>{s.run ? 'Observe. Inspect. Understand.' : 'Set the scene. Follow the signal.'}</h2></div><span><ScanLine size={14} /> {s.run ? 'Results from the current experiment' : 'Your observations will appear here'}</span></div>
    <ExperimentControls compact />
    <TransportBar />
    <div className="command-main-grid"><Panel title="Spectrum surveillance" eyebrow="RECEIVER OBSERVATIONS" action={<SourceBadge category={s.run?.dataset.category ?? source?.category} compact />}>
      <div className="spectrum-status"><span><span className={`tiny-dot ${s.playing ? 'green' : ''}`} />{s.run ? s.playing ? s.mode === 'REPLAY' ? 'REPLAYING' : 'ACQUIRING' : s.run.state === 'completed' && s.mode === 'LIVE' ? 'COMPLETE' : 'HOLD' : 'AWAITING FIRST SCAN'}</span><span className="mono">{policy ? `B${policy.selected_window.start.toString().padStart(2, '0')}—B${policy.selected_window.end.toString().padStart(2, '0')}` : 'WINDOW —'}<span className="muted"> · {receiver.slot_ms.toFixed(0)} ms / slot</span></span></div>
      <SpectrumStrip /><Waterfall height={280} /><WaterfallLegend />
      <div className="inline-metrics"><Metric label="Detected active cells" value={formatNumber(policy?.metrics.true_positives)} accent /><Metric label="Global interception" value={percent(policy?.metrics.recall)} /><Metric label="Scan efficiency" value={percent(policy?.metrics.scan_efficiency)} /><Metric label="Directed exploration" value={percent(policy?.metrics.exploration_fraction, 0)} /></div>
    </Panel><DecisionPanel /></div>
    <div className="two-column"><Panel title="An evolving belief of the spectrum" eyebrow="MODEL STATE ≠ ENVIRONMENT TRUTH" action={<button className="icon-button" aria-label="Open AI observability" onClick={() => s.navigate('knowledge')}><ArrowUpRight size={16} /></button>}><BeliefMap /></Panel><Panel title="Cumulative interception" eyebrow="SAME WORLD · MEASURED OUTCOMES" action={<div className="chart-legend compact"><span><i className="legend-dot green" />AAMS-X</span><span><i className="legend-dot slate" />Fixed</span></div>}><InterceptTrend height={175} /></Panel></div>
    <div className="command-section-heading command-explore-heading"><div><span className="eyebrow">GO A LEVEL DEEPER</span><h2>Follow your curiosity.</h2></div></div>
    <div className="quick-links command-quick-links">{[{ page: 'duel' as const, icon: Activity, title: 'Fair Duel', note: 'Compare two policies in the same hidden world.', label: 'COMPARE' }, { page: 'cube' as const, icon: Box, title: 'Spectrum Intelligence Cube', note: 'See time, frequency, and belief in three dimensions.', label: 'EXPLORE' }, { page: 'provenance' as const, icon: Fingerprint, title: 'Data Provenance', note: 'Follow each source from origin to observation.', label: 'VERIFY' }, { page: 'benchmark' as const, icon: AudioLines, title: 'Benchmark Lab', note: 'Review evidence across seeds and scenarios.', label: 'MEASURE' }].map(item => <button key={item.page} onClick={() => s.navigate(item.page)}><span className="quick-link-icon"><item.icon size={20} /></span><span className="quick-link-copy"><span className="eyebrow">{item.label}</span><strong>{item.title}</strong><small>{item.note}</small></span><ArrowUpRight size={16} /></button>)}</div>
    <TruthBoundary />
  </div>
}
