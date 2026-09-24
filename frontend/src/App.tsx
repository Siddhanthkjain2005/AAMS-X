import { Component, lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { MotionConfig } from 'framer-motion'
import { Activity, ArrowUpRight, AudioLines, Box, ChevronRight, Maximize2, Menu, Minimize2, Monitor, Radio, Search, Settings2, ShieldCheck, Sparkles, X } from 'lucide-react'
import type { Page } from './types'
import { navigation, pageTitles, tourSteps } from './navigation'
import { useMission } from './stores/mission'
import { useTransport } from './hooks/useTransport'
import { Command } from './pages/Command'
import { Duel } from './pages/Duel'
import { Knowledge } from './pages/Knowledge'
import { Periodic } from './pages/Periodic'
import { Benchmark } from './pages/Benchmark'
import { DataExplorer, Provenance } from './pages/Data'
import { Architecture } from './pages/Architecture'
import { Methodology } from './pages/Methodology'
import { TraceDialog } from './components/TraceDialog'
import { CommandPalette, DemoGuide } from './components/WorkspaceTools'

const SpectrumCube = lazy(() => import('./three/SpectrumCube'))
const Library = lazy(() => import('./pages/Library').then(module => ({ default: module.Library })))

class AppBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null }
  static getDerivedStateFromError(error: Error) { return { error: error.message } }
  render() { return this.state.error ? <div className="app-fallback"><Radio size={32} /><h1>The view could not render</h1><p>{this.state.error}</p><button className="button primary" onClick={() => { location.hash = 'command'; location.reload() }}>Reload Command Center</button></div> : this.props.children }
}

function Workspace() {
  useTransport()
  const s = useMission()
  const [mobile, setMobile] = useState(false)
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 780px)').matches)
  const [search, setSearch] = useState(false)
  const [presentation, setPresentation] = useState(false)
  const [tour, setTour] = useState<number | null>(null)
  const [tourLoading, setTourLoading] = useState(false)
  const sidebar = useRef<HTMLElement>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  const page = pageTitles[s.page] ? s.page : 'command'
  const navigate = (next: Page) => { s.navigate(next); setMobile(false) }
  const closeMobile = () => { setMobile(false); menuButton.current?.focus() }

  useEffect(() => {
    const query = window.matchMedia('(max-width: 780px)')
    const update = () => { setNarrow(query.matches); if (!query.matches) setMobile(false) }
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  useEffect(() => { document.title = `${pageTitles[page]} · AAMS-X` }, [page])
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && !useMission.getState().traceOpen) {
        event.preventDefault(); setSearch(open => !open); setMobile(false)
      }
    }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [])
  useEffect(() => {
    if (!mobile || !narrow) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    sidebar.current?.querySelector<HTMLButtonElement>('.mobile-nav-close')?.focus()
    return () => { document.body.style.overflow = previousOverflow }
  }, [mobile, narrow])

  const goToTourStep = (step: number) => { setTour(step); navigate(tourSteps[step].page) }
  const startTour = async () => {
    if (s.busy || tourLoading) return
    setTourLoading(true)
    try {
      await s.refreshHistory()
      const saved = useMission.getState().history.filter(run => run.step > 0 && ['completed', 'cancelled'].includes(run.state))
      const recording = saved.find(run => run.config.dataset_id === 'simulation' && run.config.scenario === 'sudden' && run.config.horizon === 360)
        ?? saved.find(run => run.config.dataset_id === 'simulation' && run.config.algorithms.includes('fixed') && run.config.algorithms.includes('magnts'))
      if (!recording) { useMission.setState({ error: 'No completed demo recording is available. Complete an experiment, then start the guided demo.' }); return }
      await s.loadReplay(recording.id)
      const current = useMission.getState()
      if (current.error || current.run?.id !== recording.id || current.mode !== 'REPLAY') return
      useMission.setState({ cursor: Math.max(0, Math.floor((current.frames.length - 1) * 0.65)), playing: false, inspectedStep: null })
      goToTourStep(0)
    } finally { setTourLoading(false) }
  }

  return <div className={`app-shell ${presentation ? 'presentation-mode' : ''} ${tour !== null ? 'has-demo-guide' : ''}`}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to content</a>
    {mobile && narrow && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={closeMobile} />}
    <aside ref={sidebar} className={`app-sidebar ${mobile ? 'mobile-open' : ''}`} inert={(narrow && !mobile) || (presentation && !mobile)} role={mobile && narrow ? 'dialog' : undefined} aria-modal={mobile && narrow ? true : undefined} aria-label={mobile && narrow ? 'Navigation' : undefined} onKeyDown={event => {
      if (!mobile || !narrow) return
      if (event.key === 'Escape') { event.preventDefault(); closeMobile() }
      if (event.key === 'Tab') {
        const items = Array.from(sidebar.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []).filter(item => item.offsetParent !== null)
        const first = items[0], last = items[items.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }}>
      <button className="icon-button mobile-nav-close" aria-label="Close navigation panel" onClick={closeMobile}><X size={19} /></button>
      <button className="brand" onClick={() => navigate('command')} aria-label="AAMS-X home"><div className="brand-mark"><AudioLines size={27} strokeWidth={1.4} /></div><span><strong>AAMS<span>-X</span></strong><small>RESEARCH WORKSPACE</small></span></button>
      <div className="workspace-switch"><div className="workspace-symbol"><LayersIcon /></div><span>Spectrum research<small>Local · reproducible · explainable</small></span><span className={`tiny-dot ${s.engine ? 'green' : ''}`} /></div>
      <button className="sidebar-search" onClick={() => { setMobile(false); setSearch(true) }}><Search size={15} /><span>Find a page</span><kbd>⌘ K</kbd></button>
      <nav aria-label="Main navigation">{navigation.map(group => <div className="nav-group" key={group.group}><span className="nav-group-label">{group.group}</span>{group.pages.map(item => <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><item.icon size={17} strokeWidth={1.6} /><span>{item.title}</span>{item.tag && <small>{item.tag}</small>}{page === item.id && <i />}</button>)}</div>)}</nav>
      <div className="sidebar-bottom"><div className="boundary-card"><ShieldCheck size={18} /><strong>Evidence you can inspect.</strong><p>Follow every observation from source to stored result.</p><button onClick={() => navigate('architecture')}>Inspect architecture <ArrowUpRight size={13} /></button></div><div className="local-node"><Monitor size={15} /><span>LOCAL RESEARCH NODE<small><i className={`tiny-dot ${s.engine ? 'green' : ''}`} />{s.engine ? 'Engine connected' : 'Connecting to engine'}</small></span></div><div className="sidebar-version"><span>AAMS-X / v0.1.0</span><span>SOFTWARE PROTOTYPE</span></div></div>
    </aside>
    <div className="app-workspace" inert={mobile && narrow}>
      <header className="topbar"><div className="breadcrumb"><button ref={menuButton} className="icon-button mobile-menu" aria-label="Open navigation" aria-expanded={mobile} onClick={() => setMobile(true)}><Menu size={19} /></button><span>WORKSPACE</span><ChevronRight size={13} /><strong>{pageTitles[page]}</strong></div><div className="topbar-right"><span className="engine-status"><span className={`tiny-dot ${s.engine ? 'green' : ''}`} />{s.engine ? 'LOCAL ENGINE ONLINE' : 'ENGINE DISCONNECTED'}</span><span className="topbar-divider" /><button className="tour-launch" disabled={!s.engine || s.busy || tourLoading} onClick={() => void startTour()}><Sparkles size={14} /><span>{tourLoading ? 'Preparing…' : 'Guided demo'}</span></button><button className="icon-button topbar-search" aria-label="Search workspace" aria-keyshortcuts="Control+k Meta+k" onClick={() => setSearch(true)}><Search size={17} /></button><button className="icon-button presentation-toggle" aria-label={presentation ? 'Exit focus view' : 'Enter focus view'} title={presentation ? 'Exit focus view' : 'Focus view for presentations'} aria-pressed={presentation} onClick={() => { setPresentation(!presentation); setMobile(false) }}>{presentation ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button><button className="research-toggle" aria-label={s.research ? 'Switch to demo mode' : 'Switch to research mode'} aria-pressed={s.research} onClick={() => { useMission.setState({ research: !s.research }); if (!['command', 'duel'].includes(page)) navigate('command') }}><Settings2 size={15} /><span>{s.research ? 'Research mode' : 'Demo mode'}</span></button></div></header>
      <main className="main-content" id="main-content" tabIndex={-1}>
        {s.error && <div className="error-banner" role="alert"><Activity size={16} /><span>{s.error}</span>{!s.engine && <button className="text-button" onClick={() => void s.bootstrap()}>Retry connection</button>}<button className="icon-button" aria-label="Dismiss notification" onClick={() => useMission.setState({ error: null })}><X size={15} /></button></div>}
        <AppBoundary key={page}><Suspense fallback={<div className="loading-view" role="status"><Box size={26} /><span>Preparing {pageTitles[page]}…</span></div>}>
          {page === 'command' && <Command />}{page === 'duel' && <Duel />}{page === 'knowledge' && <Knowledge />}{page === 'periodic' && <Periodic />}{page === 'cube' && <SpectrumCube />}{page === 'library' && <Library />}{page === 'benchmark' && <Benchmark />}{page === 'explorer' && <DataExplorer />}{page === 'provenance' && <Provenance />}{page === 'architecture' && <Architecture />}{page === 'methodology' && <Methodology />}
        </Suspense></AppBoundary>
        <footer className="workspace-footer"><span><AudioLines size={12} /> AAMS-X · OBSERVATION-DRIVEN RESEARCH</span><span>Explore. Inspect. Reproduce.</span></footer>
      </main>
    </div>
    {tour !== null && <DemoGuide step={tour} onStep={goToTourStep} onClose={() => setTour(null)} />}
    {search && <CommandPalette onClose={() => setSearch(false)} onNavigate={navigate} />}
    {s.traceOpen && <TraceDialog />}
  </div>
}

function LayersIcon() { return <span className="workspace-layer-icon"><i /><i /><i /></span> }

export default function App() {
  return <AppBoundary><MotionConfig reducedMotion="user"><Workspace /></MotionConfig></AppBoundary>
}
