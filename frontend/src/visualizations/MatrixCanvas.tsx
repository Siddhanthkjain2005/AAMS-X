import { useEffect, useRef, useState } from 'react'
import { energyColor } from '../services/colors'

export function MatrixCanvas({ data, frequencies, times, range, height = 340 }: { data: (number | null)[][]; frequencies: number[]; times: number[]; range: number[]; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [width, setWidth] = useState(700)
  useEffect(() => { if (!ref.current) return; const ro = new ResizeObserver(e => setWidth(e[0].contentRect.width)); ro.observe(ref.current); return () => ro.disconnect() }, [])
  useEffect(() => {
    const canvas = ref.current
    if (!canvas || !data.length || !frequencies.length) return
    const dpr = Math.min(devicePixelRatio, 2); canvas.width = width * dpr; canvas.height = height * dpr
    const ctx = canvas.getContext('2d'); if (!ctx) return
    ctx.scale(dpr, dpr); ctx.fillStyle = '#0c1018'; ctx.fillRect(0, 0, width, height)
    const left = 56, top = 18, w = width - 72, h = height - 45
    const medianGap = (axis: number[]) => {
      const gaps = axis.slice(1).map((v, i) => v - axis[i]).sort((a, b) => a - b)
      return gaps[Math.floor(gaps.length / 2)] || 1
    }
    const dt = medianGap(times), df = medianGap(frequencies)
    const t0 = times[0], t1 = times[times.length - 1] + dt
    const f0 = frequencies[0] - df / 2, f1 = frequencies[frequencies.length - 1] + df / 2
    const cw = dt / (t1 - t0) * w, bh = df / (f1 - f0) * h
    data.forEach((row, ti) => row.forEach((v, fi) => {
      if (v === null) return
      ctx.fillStyle = energyColor(v, range[0], range[1])
      ctx.fillRect(left + (times[ti] - t0) / (t1 - t0) * w, top + (f1 - frequencies[fi] - df / 2) / (f1 - f0) * h, Math.max(1, cw), Math.max(1, bh))
    }))
    ctx.font = '10px ui-monospace, monospace'; ctx.fillStyle = '#8290a5'; ctx.textAlign = 'right'
    for (let i = 0; i <= 4; i++) {
      ctx.fillText(`${(f1 - (f1 - f0) * i / 4).toFixed(1)}M`, left - 8, top + i / 4 * h + 3)
    }
    ctx.textAlign = 'left'; ctx.fillText(`${(times[0] / 1000).toFixed(0)} s`, left, height - 8)
    ctx.textAlign = 'right'; ctx.fillText(`${(times[times.length - 1] / 1000).toFixed(0)} s`, left + w, height - 8)
  }, [width, height, data, frequencies, times, range])
  return <canvas className="matrix-canvas" ref={ref} style={{ width: '100%', height }} role="img" aria-label="Time-frequency preview positioned on physical time and frequency coordinates. Intensity is color coded; missing values and irregular channel gaps are blank." />
}
