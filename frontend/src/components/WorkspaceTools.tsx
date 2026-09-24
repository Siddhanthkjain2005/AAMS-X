import { useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, CornerDownLeft, Search, Sparkles, X } from 'lucide-react'
import { allPages, tourSteps } from '../navigation'
import type { Page } from '../types'

export function CommandPalette({ onClose, onNavigate }: { onClose: () => void; onNavigate: (page: Page) => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const matches = allPages.filter(item => `${item.title} ${item.description}`.toLowerCase().includes(query.toLowerCase().trim()))
  const active = Math.min(selected, Math.max(0, matches.length - 1))
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])
  useEffect(() => { dialog.current?.querySelector(`#command-option-${active}`)?.scrollIntoView({ block: 'nearest' }) }, [active])
  const choose = (page: Page) => { onClose(); onNavigate(page) }
  return <dialog ref={dialog} className="command-dialog" aria-label="Search workspace" onCancel={onClose} onClick={event => { if (event.target === dialog.current) onClose() }}>
    <div className="command-dialog-inner">
      <div className="command-search"><Search size={21} /><input autoFocus role="combobox" aria-label="Search pages" aria-controls="workspace-results" aria-expanded="true" aria-autocomplete="list" aria-activedescendant={matches.length ? `command-option-${active}` : undefined} placeholder="Where would you like to go?" value={query} onChange={event => { setQuery(event.target.value); setSelected(0) }} onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setSelected((active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % Math.max(1, matches.length)) }
        if (event.key === 'Enter' && matches[active]) { event.preventDefault(); choose(matches[active].id) }
      }} /><button className="icon-button" aria-label="Close search" onClick={onClose}><X size={18} /></button></div>
      <div className="command-results" id="workspace-results" role="listbox" aria-label="Workspace pages">
        <span className="command-group-label">{query ? `${matches.length} matching pages` : 'EXPLORE YOUR WORKSPACE'}</span>
        {matches.map((item, index) => <button key={item.id} id={`command-option-${index}`} role="option" aria-selected={active === index} tabIndex={-1} className={`command-result ${active === index ? 'selected' : ''}`} onMouseMove={() => setSelected(index)} onClick={() => choose(item.id)}><span className="command-result-icon"><item.icon size={19} /></span><span><strong>{item.title}</strong><small>{item.description}</small></span><CornerDownLeft size={15} /></button>)}
        {!matches.length && <div className="command-empty"><Search size={26} /><strong>No matching pages</strong><p>Try “replay”, “data”, or “benchmark”.</p></div>}
      </div>
      <div className="command-footer"><span><kbd><ArrowUp size={11} /></kbd><kbd><ArrowDown size={11} /></kbd> navigate</span><span><kbd>↵</kbd> open</span><span><kbd>esc</kbd> close</span></div>
    </div>
  </dialog>
}


export function DemoGuide({ step, onStep, onClose }: { step: number; onStep: (step: number) => void; onClose: () => void }) {
  const current = tourSteps[step]
  return <section className="demo-guide" aria-label="Guided demo">
    <div className="guide-progress" aria-label={`Step ${step + 1} of ${tourSteps.length}`}>{tourSteps.map((item, index) => <button key={item.page} className={index <= step ? 'complete' : ''} aria-label={`Go to demo step ${index + 1}: ${item.title}`} aria-current={step === index ? 'step' : undefined} onClick={() => onStep(index)} />)}</div>
    <div className="guide-content"><div className="guide-symbol"><Sparkles size={21} /></div><div className="guide-copy" aria-live="polite"><span className="eyebrow">GUIDED DEMO · {String(step + 1).padStart(2, '0')} / 05</span><h2>{current.title}</h2><p>{current.description}</p><small>{current.focus}</small></div><div className="guide-actions"><button className="icon-button" aria-label="Previous demo step" disabled={step === 0} onClick={() => onStep(step - 1)}><ArrowLeft size={18} /></button><button className="button primary" onClick={() => step === tourSteps.length - 1 ? onClose() : onStep(step + 1)}>{step === tourSteps.length - 1 ? 'Finish tour' : 'Next chapter'}<ArrowRight size={15} /></button></div><button className="icon-button guide-close" aria-label="End guided demo" onClick={onClose}><X size={16} /></button></div>
  </section>
}
