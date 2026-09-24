import { useState } from 'react'
import { ChevronDown, Download, Eye, FlaskConical, Pause, Play, RotateCcw, ScanLine, Settings2, Swords } from 'lucide-react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { formatNumber } from '../services/api'
import type { EmitterSpec, ReceiverConfig } from '../types'
import { SourceBadge, Toggle } from './ui'

export function ExperimentControls({ compact = false }: { compact?: boolean }) {
  const { config, setConfig, scenarios, datasets, start, busy, engine, research } = useMission()
  const [custom, setCustom] = useState('')
  const [customError, setCustomError] = useState('')
  const setReceiver = (key: keyof ReceiverConfig, value: number) => setConfig({ receiver: { ...config.receiver, [key]: value } })
  const advanced: { key: keyof ReceiverConfig; label: string; step: number; min: number; max: number }[] = [
    { key: 'bands', label: 'Logical bands', step: 1, min: 8, max: 128 },
    { key: 'slot_ms', label: 'Time slot (ms)', step: 1, min: 1, max: 60000 },
    { key: 'min_dwell_ms', label: 'Minimum dwell (ms)', step: 1, min: 1, max: 1000 },
    { key: 'retune_ms', label: 'Retune delay (ms)', step: 1, min: 0, max: 1000 },
    { key: 'scan_latency_ms', label: 'Scan latency (ms)', step: 1, min: 0, max: 100 },
    { key: 'threshold_db', label: 'Energy threshold', step: 0.5, min: 0.1, max: 30 },
    { key: 'noise_floor_db', label: 'Reference floor', step: 1, min: -180, max: 100 },
    { key: 'snr_db', label: 'Signal / noise (dB)', step: 1, min: -5, max: 40 },
    { key: 'false_alarm_probability', label: 'Spurious alarm probability', step: 0.001, min: 0, max: 0.5 },
    { key: 'miss_probability', label: 'Additional miss probability', step: 0.01, min: 0, max: 0.9 },
    { key: 'switching_cost', label: 'Switching cost weight', step: 0.05, min: 0, max: 5 },
    { key: 'frequency_min_mhz', label: 'Spectrum minimum (MHz)', step: 100, min: 0, max: 100000 },
    { key: 'frequency_max_mhz', label: 'Spectrum maximum (MHz)', step: 100, min: 1, max: 100000 },
  ]
  return <section className={`experiment-controls ${compact ? 'compact' : ''}`}>
    <div className="control-section-title"><span className="eyebrow"><Settings2 size={13} /> EXPERIMENT CONFIGURATION</span><button className="text-button" onClick={() => useMission.setState({ research: !research })}><FlaskConical size={13} /> {research ? 'Research mode' : 'Demo mode'} <ChevronDown size={13} /></button></div>
    <div className="control-grid">
      <label className="field scenario-field"><span>Scenario</span><select aria-label="Scenario" value={config.scenario} disabled={config.dataset_id !== 'simulation'} onChange={e => setConfig({ scenario: e.target.value, emitters: null })}>{scenarios.length ? scenarios.map(s => <option value={s.id} key={s.id}>{s.name}</option>) : <option value="sudden">Sudden Appearance</option>}</select></label>
      <label className="field source-field"><span>Data source</span><select aria-label="Data source" value={config.dataset_id} onChange={e => setConfig({ dataset_id: e.target.value })}>{datasets.length ? datasets.map(d => <option value={d.id} disabled={d.status !== 'available'} key={d.id}>{d.name}{d.status !== 'available' ? ' · not installed' : ''}</option>) : <option value="simulation">Controlled simulation</option>}</select></label>
      <label className="field bandwidth-field"><span>Receiver bandwidth <strong>{config.receiver.window_width}/{config.receiver.bands}</strong></span><input aria-label="Receiver bandwidth" type="range" min="1" max={Math.min(16, config.receiver.bands)} value={config.receiver.window_width} onChange={e => setReceiver('window_width', +e.target.value)} /></label>
      <label className="field"><span>Seed</span><input aria-label="Experiment seed" type="number" min="0" max="4294967295" value={config.seed} onChange={e => setConfig({ seed: Math.max(0, +e.target.value) })} /></label>
      <label className="field"><span>Horizon / slots</span><select aria-label="Horizon" value={config.horizon} onChange={e => setConfig({ horizon: +e.target.value })}>{[96, 240, 360, 420, 720, 1000, ...( [96, 240, 360, 420, 720, 1000].includes(config.horizon) ? [] : [config.horizon])].sort((a, b) => a - b).map(h => <option key={h} value={h}>{h}</option>)}</select></label>
      <label className="field noise-field"><span>Noise variation <strong>{config.receiver.noise_std_db.toFixed(1)}</strong></span><input aria-label="Noise variation" type="range" min="0.2" max="6" step="0.2" value={config.receiver.noise_std_db} onChange={e => setReceiver('noise_std_db', +e.target.value)} /></label>
    </div>
    {research && <div className="advanced-controls"><div className="advanced-grid">{advanced.map(f => <label className="field" key={f.key}><span>{f.label}</span><input type="number" min={f.min} max={f.max} step={f.step} value={config.receiver[f.key]} onChange={e => setReceiver(f.key, +e.target.value)} /></label>)}</div><details><summary>Custom activity sources (JSON)</summary><p className="muted small-copy">Explicit simulator sources: kind, band, width, start/stop, period, duration, duty, snr_offset. These parameters are hidden from policies.</p><textarea aria-label="Custom activity source JSON" rows={4} value={custom} placeholder={'[{"kind":"periodic","band":12,"period":18,"duration":4}]'} onChange={e => setCustom(e.target.value)} /><div className="button-row"><button className="button secondary small" onClick={() => { try { const emitters = JSON.parse(custom) as EmitterSpec[]; if (!Array.isArray(emitters)) throw new Error('Expected an array'); setConfig({ emitters, dataset_id: 'simulation' }); setCustomError('Custom sources applied to the next run.') } catch { setCustomError('Enter a valid JSON array of source configurations.') } }}>Apply sources</button><button className="text-button" onClick={() => { setConfig({ emitters: null }); setCustom(''); setCustomError('Scenario preset restored.') }}>Use preset</button><span className="small-copy">{customError}</span></div></details></div>}
    {!compact && <div className="control-footer"><span className="muted small-copy">Identical truth, receiver, detector noise & time horizon. Independent policy states.</span><button className="button primary" disabled={busy || !engine} onClick={() => void start({ ...config, algorithms: ['fixed', 'magnts'] })}><Swords size={16} />{busy ? 'Preparing environment…' : 'RUN FAIR DUEL'}<span className="button-key">↗</span></button></div>}
  </section>
}

export function TransportBar() {
  const s = useMission()
  const current = useCurrentFrame()
  const available = s.history.filter(r => r.step > 0 && ['completed', 'cancelled'].includes(r.state))
  if (s.run && s.mode === 'REPLAY' && !available.some(r => r.id === s.run?.id)) available.unshift(s.run)
  const openReplay = async () => {
    await s.refreshHistory()
    const history = useMission.getState().history.filter(r => r.step > 0 && ['completed', 'cancelled'].includes(r.state))
    const recorded = history.find(r => r.id === s.run?.id)
      ?? history.find(r => r.config.scenario === 'sudden' && r.config.horizon === 360 && r.config.dataset_id === 'simulation')
      ?? history[0]
    if (recorded) await s.loadReplay(recorded.id)
    else useMission.setState({ error: 'No recorded run available yet. Finish a live experiment to save its replay.' })
  }
  return <>
    <div className="transport-bar">
      <div className="segmented mode-switch"><button disabled={s.busy} className={s.mode === 'LIVE' ? 'active' : ''} onClick={() => { if (s.mode !== 'LIVE') void s.start() }}><span className={`tiny-dot ${s.mode === 'LIVE' ? 'green' : ''}`} /> LIVE</button><button disabled={s.busy} className={s.mode === 'REPLAY' ? 'active' : ''} onClick={() => void openReplay()}>REPLAY</button></div>
      <div className="transport-buttons"><button className="icon-button" aria-label={s.playing ? 'Pause experiment' : 'Resume experiment'} title={s.playing ? 'Pause' : 'Resume'} disabled={s.busy || !s.run || (s.mode === 'LIVE' && s.run.state === 'completed')} onClick={() => void (s.playing ? s.pause() : s.resume())}>{s.playing ? <Pause size={16} /> : <Play size={16} />}</button><button className="icon-button" aria-label="Reset experiment" title="Reset to cold start" disabled={s.busy || !s.run} onClick={() => void s.reset()}><RotateCcw size={15} /></button></div>
      <div className="segmented speed-switch">{([1, 2, 4] as const).map(n => <button aria-label={`Playback speed ${n}x`} key={n} className={s.speed === n ? 'active' : ''} onClick={() => void s.setSpeed(n)}>{n}×</button>)}</div>
      <span className="transport-time mono">{s.run ? `${formatNumber((current?.timestamp_ms ?? 0) / 1000, 2)} s` : 'STANDBY'}<span> / {s.run ? `${formatNumber(s.run.config.horizon * s.run.config.receiver.slot_ms / 1000, 1)} s` : 'NO RUN'}</span></span>
      <div className="transport-spacer" />
      <button className="button secondary small trace-button" disabled={s.busy || !s.engine} onClick={() => void s.openTrace()}><ScanLine size={15} />Trace one decision</button>
      <Toggle label="Ground truth" checked={s.judge} onChange={value => void s.setJudge(value)} />
      {s.run && <a className="icon-button" href={`/api/experiment/${s.run.id}/export?format=json`} aria-label="Export experiment JSON" title="Export JSON"><Download size={15} /></a>}
    </div>
    {s.mode === 'REPLAY' && <div className="replay-bar" aria-busy={s.busy}><span className="badge violet">{s.busy ? 'LOADING RECORDED EXPERIMENT' : 'RECORDED REPRODUCIBLE EXPERIMENT REPLAY'}</span><select aria-label="Recorded experiment" disabled={s.busy} value={s.run?.id ?? ''} onChange={e => void s.loadReplay(e.target.value)}>{available.map(r => <option value={r.id} key={r.id}>{r.config.dataset_id === 'simulation' ? r.config.scenario : r.dataset.name} · {r.config.horizon} slots · seed {r.config.seed} · {r.id}</option>)}</select><input aria-label="Replay timeline" disabled={s.busy} type="range" min="0" max={Math.max(0, s.frames.length - 1)} value={s.cursor} onChange={e => useMission.setState({ cursor: +e.target.value, playing: false, inspectedStep: null })} /></div>}
    {s.judge && <div className="judge-banner"><Eye size={15} /><strong>EVALUATION / JUDGE VIEW</strong><span>{s.run?.dataset.ground_truth === false ? 'Full recording visualization. No labelled emitter ground truth exists.' : 'Hidden activity is visible to you. Policy inputs remain observation-only.'}</span></div>}
    {s.run?.dataset.category === 'REAL_MEASURED_RF' && <div className="measured-banner"><SourceBadge category="REAL_MEASURED_RF" compact /><span>{s.run.dataset.note}</span></div>}
    {s.inspectedStep !== null && <div className="inspection-banner">Inspecting stored decision at slot {s.inspectedStep}.<button className="text-button" onClick={() => { void s.inspect(null); void s.resume() }}>Return to {s.mode === 'LIVE' ? 'live stream' : 'replay'} →</button></div>}
  </>
}
