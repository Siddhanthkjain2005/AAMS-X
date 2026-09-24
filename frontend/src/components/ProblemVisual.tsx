import { useId } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { ArrowRight, MoveHorizontal } from 'lucide-react'
import { useMission } from '../stores/mission'

export function ProblemVisual({ expanded = false }: { expanded?: boolean }) {
  const receiver = useMission(s => s.config.receiver)
  const reduceMotion = useReducedMotion()
  const uniqueId = useId()
  const fillId = `${uniqueId}-concept-fill`
  const glowId = `${uniqueId}-concept-glow`
  const windowWidth = Math.min(500, Math.max(8, receiver.window_width / receiver.bands * 500))
  const travel = 500 - windowWidth
  const positions = expanded ? [travel * .15, travel * .38, travel * .79, travel * .79, travel * .15] : [travel * .25, travel * .72, travel * .72, travel * .25]
  return <div className={`problem-visual ${expanded ? 'expanded' : ''}`}>
    <div className="schematic-topline"><span><span className="tiny-dot green" /> THE BANDWIDTH CONSTRAINT</span><span>CONCEPT ILLUSTRATION</span></div>
    <svg viewBox="0 0 560 250" role="img" aria-label="Concept illustration: a narrow receiver window scans a wide spectrum. This diagram is illustrative, not measured experiment data.">
      <defs>
        <linearGradient id={fillId} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#bdacd9" stopOpacity=".9" /><stop offset="100%" stopColor="#8b85ab" stopOpacity=".14" /></linearGradient>
        <linearGradient id={glowId} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#c0e88c" stopOpacity=".02" /><stop offset="100%" stopColor="#c0e88c" stopOpacity=".2" /></linearGradient>
      </defs>
      <text x="30" y="25" fill="#667580" fontSize="8" letterSpacing="1.4">ILLUSTRATIVE ENERGY</text>
      {[55, 90, 125, 160, 195].map((y, i) => <g key={y}><line x1="30" y1={y} x2="530" y2={y} stroke="#3a454b" strokeOpacity=".55" strokeDasharray="2 5" /><text x="17" y={y + 3} textAnchor="end" fill="#66717c" fontSize="7">{4 - i}</text></g>)}
      {[30, 155, 280, 405, 530].map(x => <line key={x} x1={x} x2={x} y1="43" y2="198" stroke="#34414a" strokeOpacity=".38" />)}
      {Array.from({ length: 80 }, (_, i) => {
        const height = 9 + 90 * Math.exp(-(((i - 17) / 4) ** 2)) + 120 * Math.exp(-(((i - 48) / 3.4) ** 2)) + 62 * Math.exp(-(((i - 65) / 4.6) ** 2)) + Math.abs(Math.sin(i * 4.3)) * 11
        return <rect key={i} x={31 + i * 6.25} y={195 - height} width="3.5" height={height} rx="1.5" fill={`url(#${fillId})`} />
      })}
      <line x1="30" y1="198" x2="530" y2="198" stroke="#506059" />
      <motion.g initial={false} animate={{ x: reduceMotion ? travel * .38 : positions }} transition={reduceMotion ? { duration: 0 } : { duration: expanded ? 16 : 13, repeat: Infinity, ease: 'easeInOut' }}>
        <rect x="30" y="43" width={windowWidth} height="155" fill={`url(#${glowId})`} />
        <line x1="30" x2="30" y1="43" y2="198" stroke="#c0e88c" strokeOpacity=".8" />
        <line x1={30 + windowWidth} x2={30 + windowWidth} y1="43" y2="198" stroke="#c0e88c" strokeOpacity=".8" />
        <path d={`M30 51V43H${30 + windowWidth}V51M30 190V198H${30 + windowWidth}V190`} stroke="#d1f3a8" strokeWidth="1.5" fill="none" />
        <circle cx={30 + windowWidth / 2} cy="207" r="2.5" fill="#c0e88c" />
      </motion.g>
      <text x="30" y="231" fill="#8a989f" fontSize="9">{receiver.frequency_min_mhz.toLocaleString()} MHz</text>
      <text x="530" y="231" textAnchor="end" fill="#8a989f" fontSize="9">{receiver.frequency_max_mhz.toLocaleString()} MHz</text>
      <text x="280" y="231" textAnchor="middle" fill="#69787b" fontSize="7" letterSpacing="2">FREQUENCY</text>
    </svg>
    <div className="schematic-bottom"><span><MoveHorizontal size={14} /> {receiver.bands} logical bands</span><ArrowRight size={13} /><strong>{receiver.window_width} observed at a time</strong><span className="fraction-pill">{(100 * receiver.window_width / receiver.bands).toFixed(1)}%</span></div>
    <div className="schematic-legend"><span><i />Illustrative activity</span><span><i />Receiver window</span></div>
  </div>
}
