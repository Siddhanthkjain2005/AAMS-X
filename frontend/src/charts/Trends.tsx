import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useVisibleFrames } from '../hooks/useVisibleFrames'
import { metricNumber } from '../services/api'
import { EmptyState } from '../components/ui'

export function InterceptTrend({ height = 210, metric = 'recall' }: { height?: number; metric?: string }) {
  const frames = useVisibleFrames()
  const step = Math.max(1, Math.floor(frames.length / 180))
  const fraction = metric === 'recall' || metric === 'pd'
  const data = frames.filter((_, i) => i % step === 0 || i === frames.length - 1).map(f => ({
    time: +(f.timestamp_ms / 1000).toFixed(2),
    magnts: metricNumber(f.policies.magnts?.metrics, metric) === null ? null : metricNumber(f.policies.magnts?.metrics, metric)! * (fraction ? 100 : 1),
    fixed: metricNumber(f.policies.fixed?.metrics, metric) === null ? null : metricNumber(f.policies.fixed?.metrics, metric)! * (fraction ? 100 : 1),
  }))
  if (!data.length) return <EmptyState description="Cumulative performance appears as the experiment runs." action={false} />
  if (!data.some(d => d.magnts !== null || d.fixed !== null)) return <EmptyState title="N/A — no labelled emitter ground truth" description="Measured recordings support coverage and observed energy metrics instead." action={false} />
  return <div className="trend-chart"><ResponsiveContainer width="100%" height={height} minWidth={1}><LineChart data={data} margin={{ top: 12, right: 18, left: -17, bottom: 4 }}><CartesianGrid stroke="#242b36" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="time" tick={{ fill: '#77849a', fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={40} tickFormatter={v => `${v}s`} /><YAxis domain={fraction ? [0, 100] : ['auto', 'auto']} tick={{ fill: '#77849a', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `${v}${fraction ? '%' : ''}`} /><Tooltip contentStyle={{ background: '#171d28', border: '1px solid #303a49', borderRadius: 8, fontSize: 12, color: '#e7ebf1' }} formatter={value => `${Number(value).toFixed(2)}${fraction ? '%' : ''}`} labelFormatter={label => `${label} seconds`} /><Line type="monotone" name="AAMS-X" dataKey="magnts" stroke="#c0e88c" strokeWidth={2} dot={false} isAnimationActive={false} /><Line type="monotone" name="Fixed Sweep" dataKey="fixed" stroke="#8495b0" strokeWidth={1.6} dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
}
