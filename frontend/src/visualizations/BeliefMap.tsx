import { useState } from 'react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { percent } from '../services/api'
import type { Belief } from '../types'

export function BeliefMap({ belief: supplied, expanded = false }: { belief?: Belief; expanded?: boolean }) {
  const frame = useCurrentFrame()
  const n = useMission(s => s.run?.config.receiver.bands ?? s.config.receiver.bands)
  const belief = supplied ?? frame?.policies.magnts?.belief
  const [selected, setSelected] = useState<number | null>(null)
  const [mode, setMode] = useState<'probability' | 'uncertainty' | 'information_gain'>('probability')
  const values = belief?.[mode]
  return <div className={`belief-map ${expanded ? 'expanded' : ''}`}>
    <div className="belief-toolbar"><div className="segmented"><button className={mode === 'probability' ? 'active' : ''} onClick={() => setMode('probability')}>Probability</button><button className={mode === 'uncertainty' ? 'active violet-text' : ''} onClick={() => setMode('uncertainty')}>Uncertainty</button>{expanded && <button className={mode === 'information_gain' ? 'active' : ''} onClick={() => setMode('information_gain')}>Information gain</button>}</div><span className="small-copy muted">{mode === 'probability' ? 'Likely active' : mode === 'uncertainty' ? 'Unknown · worth exploring' : 'Expected uncertainty reduction'}</span></div>
    <div className={`band-grid ${expanded ? 'large' : ''}`} style={{ '--bands': n } as React.CSSProperties}>
      {Array.from({ length: n }, (_, band) => {
        const value = values?.[band] ?? 0.5
        const intensity = mode === 'information_gain' ? Math.min(1, value / 0.193147) : value
        const known = !!belief && belief.observations[band] > 0
        return <button aria-label={`Band ${band}: ${belief ? `${mode} ${value.toFixed(3)}, ${belief.observations[band]} observations` : 'no run available'}`} className={`${selected === band ? 'selected' : ''} ${known ? '' : 'unknown-band'}`} key={band} onClick={() => setSelected(band)} style={{ backgroundColor: belief ? (mode === 'probability' ? `rgba(175,213,134,${0.045 + intensity * 0.72})` : `rgba(160,144,212,${0.06 + intensity * 0.75})`) : '#181e29' }}><span>{band.toString().padStart(2, '0')}</span>{expanded && <strong>{belief ? mode === 'information_gain' ? value.toFixed(3) : percent(value, 0) : '—'}</strong>}{expanded && <small>{known ? `${belief?.observations[band]} obs` : 'unobserved'}</small>}</button>
      })}
    </div>
    <div className="belief-scale"><span>LOW</span><div className={mode === 'probability' ? 'probability-scale' : 'uncertainty-scale'} /><span>HIGH</span><span className="legend-hint">Dashed = never observed</span></div>
    {selected !== null && belief && <div className="band-detail"><strong>BAND {selected.toString().padStart(2, '0')}</strong><span>p(active) <b>{percent(belief.probability[selected])}</b></span><span>uncertainty <b className="violet-text">{percent(belief.uncertainty[selected])}</b></span><span>{belief.observations[selected]} observations</span><span>{belief.last_visit[selected] < 0 ? 'Never visited' : `Last visit: slot ${belief.last_visit[selected]}`}</span></div>}
  </div>
}
