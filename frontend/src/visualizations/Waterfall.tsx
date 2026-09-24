import { useEffect, useRef, useState } from 'react'
import type { Algorithm, ExperimentConfig, Frame } from '../types'
import { useCurrentFrame, useMission } from '../stores/mission'
import { formatNumber } from '../services/api'
import { energyColor } from '../services/colors'
import { useVisibleFrames } from '../hooks/useVisibleFrames'

export function Waterfall({ algorithm = 'magnts', height = 260, frames: supplied, config: suppliedConfig, judge: suppliedJudge }: { algorithm?: Algorithm; height?: number; frames?: Frame[]; config?: ExperimentConfig; judge?: boolean }) {
  const visible = useVisibleFrames()
  const config = useMission(s => s.run?.config ?? s.config)
  const judge = useMission(s => s.judge)
  const inspect = useMission(s => s.inspect)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState(700)
  const [hover, setHover] = useState<{ index: number; band: number } | null>(null)
  const usedConfig = suppliedConfig ?? config
  const usedJudge = suppliedJudge ?? judge
  const frames = (supplied ?? visible).slice(-128)
  const framesRef = useRef(frames)
  framesRef.current = frames

  useEffect(() => {
    if (!canvas.current) return
    const observer = new ResizeObserver(entries => setSize(entries[0].contentRect.width))
    observer.observe(canvas.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const element = canvas.current
    if (!element) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    element.width = size * dpr; element.height = height * dpr
    const ctx = element.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.fillStyle = '#0c1018'; ctx.fillRect(0, 0, size, height)
    const left = 52, top = 16, w = Math.max(1, size - left - 16), h = height - 43
    const bands = usedConfig.receiver.bands
    const data = framesRef.current
    const cols = Math.max(64, data.length), cw = w / cols, bh = h / bands
    const y = (b: number) => top + (bands - b - 1) * bh
    ctx.strokeStyle = '#202633'; ctx.lineWidth = 0.5
    for (let i = 0; i <= 4; i++) {
      const yy = top + i * h / 4
      ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + w, yy); ctx.stroke()
      ctx.font = '9px ui-monospace, monospace'; ctx.fillStyle = '#768297'; ctx.textAlign = 'right'
      const frequency = usedConfig.receiver.frequency_max_mhz - i / 4 * (usedConfig.receiver.frequency_max_mhz - usedConfig.receiver.frequency_min_mhz)
      ctx.fillText(frequency >= 1000 ? `${(frequency / 1000).toFixed(1)}G` : `${frequency.toFixed(0)}M`, left - 9, yy + 3)
    }
    for (let i = 0; i <= 8; i++) {
      const xx = left + i * w / 8
      ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, top + h); ctx.stroke()
    }
    const low = usedConfig.receiver.noise_floor_db - 2, high = low + Math.max(16, usedConfig.receiver.snr_db + 4)
    const path: [number, number][] = []
    data.forEach((frame, index) => {
      const p = frame.policies[algorithm]
      if (!p) return
      const x = left + index * cw
      if (usedJudge && frame.evaluation) frame.evaluation.energy.forEach((energy, b) => {
        if (energy !== null) { ctx.fillStyle = energyColor(energy, low, high, 0.86); ctx.fillRect(x, y(b), Math.ceil(cw), Math.ceil(bh)) }
      })
      else p.observations.values.forEach(v => {
        if (v.energy !== null) { ctx.fillStyle = energyColor(v.energy, low, high); ctx.fillRect(x, y(v.band), Math.ceil(cw), Math.ceil(bh)) }
      })
      path.push([x + cw / 2, y(p.selected_window.start + p.selected_window.width / 2) + bh / 2])
      if (usedJudge) p.evaluation?.missed_bands.forEach(b => {
        ctx.fillStyle = '#d89570'; ctx.fillRect(x + cw * 0.25, y(b) + bh * 0.35, Math.max(1, cw * 0.35), Math.max(1, bh * 0.3))
      })
      p.observations.values.filter(v => v.detected).forEach(v => {
        ctx.fillStyle = usedJudge && p.evaluation?.false_alarms.includes(v.band) ? '#e48f8f' : algorithm === 'fixed' ? '#b6c5df' : '#c0e88c'
        ctx.beginPath(); ctx.arc(x + cw / 2, y(v.band) + bh / 2, Math.min(2.5, Math.max(1.3, cw / 2)), 0, Math.PI * 2); ctx.fill()
      })
      p.belief.change_events.forEach(event => { ctx.strokeStyle = '#e3b778'; ctx.strokeRect(x - 2, y(event.band) - 1, cw + 4, bh + 2) })
    })
    ctx.strokeStyle = algorithm === 'fixed' ? 'rgba(159,177,206,.2)' : 'rgba(192,232,140,.28)'; ctx.lineWidth = 1
    ctx.beginPath(); path.forEach(([x, yy], i) => { if (i) ctx.lineTo(x, yy); else ctx.moveTo(x, yy) }); ctx.stroke()
    const last = data[data.length - 1]?.policies[algorithm]
    if (last) {
      const x = left + (data.length - 1) * cw
      ctx.fillStyle = algorithm === 'fixed' ? 'rgba(167,185,217,.12)' : 'rgba(192,232,140,.13)'
      const yy = y(last.selected_window.end)
      ctx.fillRect(x - 1, yy, cw + 2, last.selected_window.width * bh)
      ctx.strokeStyle = algorithm === 'fixed' ? '#9daccc' : '#c0e88c'; ctx.lineWidth = 1.5
      ctx.strokeRect(x - 1, yy, cw + 2, last.selected_window.width * bh)
      ctx.setLineDash([2, 4]); ctx.strokeStyle = '#4c596b'; ctx.lineWidth = 0.5
      ctx.beginPath(); ctx.moveTo(x + cw, top); ctx.lineTo(x + cw, top + h); ctx.stroke(); ctx.setLineDash([])
    }
    ctx.fillStyle = '#6f7c91'; ctx.font = '9px ui-monospace, monospace'; ctx.textAlign = 'left'
    ctx.fillText(data.length ? `${(data[0].timestamp_ms / 1000).toFixed(1)} s` : '0.0 s', left, height - 8)
    ctx.textAlign = 'right'; ctx.fillText(data.length ? `${(data[data.length - 1].timestamp_ms / 1000).toFixed(1)} s` : 'TIME →', left + w, height - 8)
    if (!data.length) {
      ctx.textAlign = 'center'; ctx.fillStyle = '#637087'; ctx.font = '11px ui-monospace, monospace'
      ctx.fillText('AWAITING RECEIVER OBSERVATIONS', left + w / 2, top + h / 2)
    }
  }, [size, height, visible, supplied, algorithm, usedConfig, usedJudge])

  const hovered = hover ? frames[hover.index] : null
  const value = hovered?.policies[algorithm]?.observations.values.find(v => v.band === hover?.band)
  return <div className="waterfall-wrap"><canvas ref={canvas} style={{ width: '100%', height }} role="img" aria-label={`${algorithm === 'fixed' ? 'Fixed Sweep' : 'Adaptive'} time-frequency waterfall. ${usedJudge ? 'Evaluation truth visible' : 'Only observed cells visible'}. Click a time slot to inspect the recorded decision.`}
    onMouseMove={e => { const box = e.currentTarget.getBoundingClientRect(); const index = Math.floor((e.clientX - box.left - 52) / Math.max(1, size - 68) * Math.max(64, frames.length)); const band = usedConfig.receiver.bands - 1 - Math.floor((e.clientY - box.top - 16) / (height - 43) * usedConfig.receiver.bands); setHover(index >= 0 && index < frames.length && band >= 0 && band < usedConfig.receiver.bands ? { index, band } : null) }}
    onMouseLeave={() => setHover(null)} onClick={() => { if (hovered && !supplied) void inspect(hovered.step) }} />
    {hover && hovered && <div className="canvas-tooltip">SLOT {hovered.step} · BAND {hover.band}<br /><strong>{value ? `${value.detected ? 'HIT' : 'MISS'} · ${formatNumber(value.energy, 1)}` : 'Unobserved — unknown to policy'}</strong></div>}
  </div>
}

export function WaterfallLegend() {
  const judge = useMission(s => s.judge)
  return <div className="chart-legend"><span><i className="legend-dot violet" />Observed energy</span><span><i className="legend-dot green" />Detection</span><span><i className="legend-dot dark" />Unobserved</span>{judge && <span><i className="legend-dot orange" />Missed activity</span>}<span className="legend-hint">Time → · Frequency ↑</span></div>
}

export function SpectrumStrip({ algorithm = 'magnts' }: { algorithm?: Algorithm }) {
  const current = useCurrentFrame()
  const n = useMission(s => s.run?.config.receiver.bands ?? s.config.receiver.bands)
  const p = current?.policies[algorithm]
  return <div className="spectrum-strip" aria-label="Current receiver position in the full spectrum">
    {Array.from({ length: n }, (_, band) => <span key={band} style={{ opacity: p ? 0.25 + (p.belief.probability[band] ?? 0) * 0.75 : 0.2, background: p && p.belief.observations[band] ? 'var(--violet)' : '#536074' }} />)}
    {p && <div className={`receiver-bracket ${algorithm === 'fixed' ? 'baseline' : ''}`} style={{ left: `${p.selected_window.start / n * 100}%`, width: `${p.selected_window.width / n * 100}%` }} />}
  </div>
}
