import { useEffect, useMemo, useState } from 'react'
import { Archive, ArrowRight, ArrowUpRight, CheckCheck, Clock3, Database, Download, Fingerprint, FolderSearch, Grid2X2, List, LoaderCircle, Play, Plus, RefreshCw, Search, SlidersHorizontal, Star, X } from 'lucide-react'
import { PageHeader, SourceBadge } from '../components/ui'
import { formatNumber, names } from '../services/api'
import { useMission } from '../stores/mission'
import type { Category, Run, RunState } from '../types'
import './library.css'

const favoritesKey = 'aams-x:favorite-experiments:v1'
const sourceLabels: Record<Category, string> = {
  CONTROLLED_SIMULATION: 'Controlled simulation',
  OFFICIAL_SYNTHETIC_RADAR: 'Official synthetic data',
  REAL_MEASURED_RF: 'Measured RF',
}
const stateLabels: Record<RunState, string> = { running: 'Running', paused: 'Paused', completed: 'Completed', cancelled: 'Stopped', failed: 'Failed' }

function readFavorites(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(favoritesKey) ?? '[]')
    return Array.isArray(value) ? [...new Set(value.filter((id): id is string => typeof id === 'string'))].slice(0, 200) : []
  } catch { return [] }
}

function dateLabel(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function RunCard({ run, title, favorite, onFavorite, onReplay, busy, opening }: {
  run: Run; title: string; favorite: boolean; onFavorite: () => void; onReplay: () => void; busy: boolean; opening: boolean
}) {
  const progress = Math.min(100, Math.max(0, run.step / Math.max(1, run.config.horizon) * 100))
  return <article className={`library-run source-${run.dataset.category.toLowerCase()}`} aria-label={`${title}, ${run.id}`}>
    <div className="library-card-top"><SourceBadge category={run.dataset.category} compact /><button className={`icon-button library-star ${favorite ? 'is-starred' : ''}`} aria-label={`${favorite ? 'Unstar' : 'Star'} experiment ${run.id}`} aria-pressed={favorite} title={favorite ? 'Remove from starred' : 'Star experiment'} onClick={onFavorite}><Star size={16} fill={favorite ? 'currentColor' : 'none'} /></button></div>
    <div className="library-card-title"><span className={`library-run-symbol ${run.dataset.category === 'REAL_MEASURED_RF' ? 'measured' : ''}`}><Archive size={21} strokeWidth={1.4} /></span><div><h2>{title}</h2><p title={run.dataset.name}>{run.dataset.name}</p></div></div>
    <div className="library-run-identity"><span className="mono" title={run.id}>{run.id}</span><time dateTime={run.created_at} title={new Date(run.created_at).toString()}>{dateLabel(run.created_at)}</time></div>
    <dl className="library-run-facts"><div><dt>Seed</dt><dd className="mono">{run.config.seed}</dd></div><div><dt>Channels</dt><dd className="mono">{formatNumber(run.config.receiver.bands)}</dd></div><div><dt>Policies</dt><dd className="mono">{run.config.algorithms.length.toString().padStart(2, '0')}</dd></div></dl>
    <div className="library-run-progress"><div><span className={`library-state state-${run.state}`}><i />{stateLabels[run.state]}</span><span className="mono">{formatNumber(run.step)} <span>/ {formatNumber(run.config.horizon)} steps</span></span></div><div className="library-progress-track" role="progressbar" aria-label={`Recorded steps for ${run.id}`} aria-valuemin={0} aria-valuemax={run.config.horizon} aria-valuenow={Math.min(run.step, run.config.horizon)}><i style={{ width: `${progress}%` }} /></div></div>
    <div className="library-policy-list" title={run.config.algorithms.map(id => names[id] ?? id).join(' · ')}>{run.config.algorithms.slice(0, 3).map(id => <span key={id}>{names[id] ?? id}</span>)}{run.config.algorithms.length > 3 && <span>+{run.config.algorithms.length - 3} more</span>}</div>
    <div className="library-run-footer"><button className="button library-replay" disabled={busy || run.step === 0} title={run.step === 0 ? 'No recorded steps yet' : 'Open recorded observations'} onClick={onReplay}>{opening ? <LoaderCircle className="library-spin" size={13} /> : <Play size={13} />}{opening ? 'Opening…' : 'Open replay'}<ArrowUpRight size={13} /></button><div className="library-downloads"><a href={`/api/experiment/${encodeURIComponent(run.id)}/export?format=json`} aria-label={`Download JSON for ${run.id}`} title="Download full experiment JSON"><Download size={12} />JSON</a><a href={`/api/experiment/${encodeURIComponent(run.id)}/export?format=csv`} aria-label={`Download CSV for ${run.id}`} title="Download experiment CSV">CSV</a></div></div>
  </article>
}

export function Library() {
  const { history, scenarios, engine, busy, refreshHistory, loadReplay, navigate } = useMission()
  const [search, setSearch] = useState('')
  const [scenario, setScenario] = useState('all')
  const [source, setSource] = useState('all')
  const [state, setState] = useState('all')
  const [sort, setSort] = useState('newest')
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [starredOnly, setStarredOnly] = useState(false)
  const [favorites, setFavorites] = useState(readFavorites)
  const [storageNotice, setStorageNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [opening, setOpening] = useState<string | null>(null)

  useEffect(() => {
    if (!engine) return
    let active = true
    void refreshHistory().finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [engine, refreshHistory])

  const scenarioNames = useMemo(() => new Map(scenarios.map(item => [item.id, item.name])), [scenarios])
  const scenarioIds = useMemo(() => [...new Set(history.map(run => run.config.scenario))].sort((a, b) => (scenarioNames.get(a) ?? a).localeCompare(scenarioNames.get(b) ?? b)), [history, scenarioNames])
  const favoriteIds = useMemo(() => new Set(favorites), [favorites])
  const starredCount = history.filter(run => favoriteIds.has(run.id)).length
  const query = search.trim().toLowerCase()
  const filtered = useMemo(() => history.filter(run => {
    const searchable = [run.id, run.config.scenario, scenarioNames.get(run.config.scenario), run.dataset.name, run.dataset.id, run.config.seed, ...run.config.algorithms.map(id => names[id] ?? id)].join(' ').toLowerCase()
    return (!query || searchable.includes(query)) && (scenario === 'all' || run.config.scenario === scenario) && (source === 'all' || run.dataset.category === source) && (state === 'all' || run.state === state) && (!starredOnly || favoriteIds.has(run.id))
  }).sort((a, b) => sort === 'steps' ? b.step - a.step : (sort === 'oldest' ? 1 : -1) * a.created_at.localeCompare(b.created_at)), [history, query, scenario, source, state, starredOnly, favoriteIds, scenarioNames, sort])
  const hasFilters = Boolean(search || scenario !== 'all' || source !== 'all' || state !== 'all')

  async function refresh() {
    setRefreshing(true)
    try { await refreshHistory() } finally { setRefreshing(false) }
  }

  function toggleFavorite(id: string) {
    const next = favorites.includes(id) ? favorites.filter(value => value !== id) : [id, ...favorites].slice(0, 200)
    setFavorites(next)
    try { localStorage.setItem(favoritesKey, JSON.stringify(next)); setStorageNotice('') }
    catch { setStorageNotice('Starred for this visit. Browser storage is unavailable.') }
  }

  async function replay(id: string) {
    setOpening(id)
    try {
      await loadReplay(id)
      const current = useMission.getState()
      if (!current.error && current.mode === 'REPLAY' && current.run?.id === id) navigate('duel')
    } finally { setOpening(null) }
  }

  function clearFilters() { setSearch(''); setScenario('all'); setSource('all'); setState('all') }

  return <>
    <PageHeader eyebrow="YOUR RESEARCH, RECORDED" title="Experiment Library" description="Find a run, revisit every decision, and keep the evidence close." action={<div className="button-row"><button className="button secondary" disabled={!engine || refreshing} onClick={() => void refresh()}><RefreshCw size={14} className={refreshing ? 'library-spin' : ''} />{refreshing ? 'Refreshing…' : 'Refresh'}</button><button className="button primary" onClick={() => navigate('command')}><Plus size={14} />New experiment</button></div>} />
    <section className="library-overview" aria-label="Library overview"><div className="library-overview-copy"><span className="eyebrow"><Archive size={13} />LOCAL EXPERIMENT ARCHIVE</span><h2>Good research leaves a trail.</h2><p>Your recent experiments, together with their source, configuration, and recorded observations.</p><span className="library-retention"><Fingerprint size={12} />Source identity stays with every run</span></div><div className="library-stat-grid"><div><span><Archive size={14} />Recent runs</span><strong>{formatNumber(history.length)}</strong><small>In the local catalog</small></div><div><span><CheckCheck size={14} />Completed</span><strong>{formatNumber(history.filter(run => run.state === 'completed').length)}</strong><small>Full experiment horizon</small></div><div><span><Database size={14} />Data sources</span><strong>{formatNumber(new Set(history.map(run => run.dataset.id)).size)}</strong><small>Distinct datasets</small></div><div><span><Star size={14} />Starred</span><strong>{formatNumber(starredCount)}</strong><small>Saved in this browser</small></div></div></section>
    <section className="library-workspace" aria-label="Experiment catalog"><div className="library-toolbar"><div className="library-tabs" role="group" aria-label="Experiment collection"><button className={!starredOnly ? 'active' : ''} aria-pressed={!starredOnly} onClick={() => setStarredOnly(false)}>All experiments <span>{history.length}</span></button><button className={starredOnly ? 'active' : ''} aria-pressed={starredOnly} onClick={() => setStarredOnly(true)}><Star size={13} />Starred <span>{starredCount}</span></button></div><div className="library-display"><label className="library-sort"><span>Sort by</span><select aria-label="Sort experiments" value={sort} onChange={event => setSort(event.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="steps">Most recorded steps</option></select></label><div className="library-view-toggle" role="group" aria-label="Library layout"><button aria-label="Grid view" aria-pressed={view === 'grid'} className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')}><Grid2X2 size={15} /></button><button aria-label="List view" aria-pressed={view === 'list'} className={view === 'list' ? 'active' : ''} onClick={() => setView('list')}><List size={16} /></button></div></div></div>
      <div className="library-filters"><label className="library-search"><Search size={16} /><input type="search" aria-label="Search experiments" placeholder="Search runs, datasets, policies, or seeds…" value={search} onChange={event => setSearch(event.target.value)} />{search && <button className="icon-button" aria-label="Clear search" onClick={() => setSearch('')}><X size={13} /></button>}</label><div className="library-filter-select"><SlidersHorizontal size={13} /><select aria-label="Filter by scenario" value={scenario} onChange={event => setScenario(event.target.value)}><option value="all">All scenarios</option>{scenarioIds.map(id => <option key={id} value={id}>{scenarioNames.get(id) ?? id}</option>)}</select></div><select aria-label="Filter by source" value={source} onChange={event => setSource(event.target.value)}><option value="all">All sources</option>{Object.entries(sourceLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select><select aria-label="Filter by state" value={state} onChange={event => setState(event.target.value)}><option value="all">All states</option>{Object.entries(stateLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div>
      <div className="library-results-heading"><span aria-live="polite">{filtered.length} {filtered.length === 1 ? 'experiment' : 'experiments'}{starredOnly ? ' starred' : ''}{hasFilters ? ' match your filters' : ' in this collection'}</span>{hasFilters ? <button className="text-button" onClick={clearFilters}><X size={11} />Clear filters</button> : <span><Clock3 size={11} />Recorded locally</span>}</div>
      {storageNotice && <p className="library-storage-notice" role="status">{storageNotice}</p>}
      {!engine && !history.length ? <div className="library-empty"><span className="library-empty-icon"><Database size={29} strokeWidth={1.3} /></span><h2>Connect to your experiment archive</h2><p>The library will appear when the local research engine is available.</p><button className="button secondary" onClick={() => void useMission.getState().bootstrap()}><RefreshCw size={13} />Retry connection</button></div> : loading && !history.length ? <div className="library-empty" role="status"><LoaderCircle size={27} className="library-spin" /><h2>Opening your experiment archive</h2><p>Loading the latest local runs and their source details.</p></div> : !filtered.length ? <div className="library-empty"><span className="library-empty-icon">{starredOnly && !hasFilters ? <Star size={29} strokeWidth={1.3} /> : <FolderSearch size={29} strokeWidth={1.3} />}</span><h2>{hasFilters ? 'No experiments match these filters' : starredOnly ? 'Keep your best references close' : 'Your research starts here'}</h2><p>{hasFilters ? 'Try another scenario, source, or search term to find your run.' : starredOnly ? 'Star an experiment to build a collection for your next demo or review.' : 'Create an experiment to capture its configuration and replay recorded observations.'}</p>{hasFilters ? <button className="button secondary" onClick={clearFilters}>Clear filters <ArrowRight size={13} /></button> : <button className="button secondary" onClick={() => starredOnly ? setStarredOnly(false) : navigate('command')}>{starredOnly ? 'Browse experiments' : 'Create an experiment'}<ArrowRight size={13} /></button>}</div> : <div className={`library-runs library-${view}`}>{filtered.map(run => <RunCard key={run.id} run={run} title={scenarioNames.get(run.config.scenario) ?? run.config.scenario.replaceAll('_', ' ')} favorite={favoriteIds.has(run.id)} onFavorite={() => toggleFavorite(run.id)} onReplay={() => void replay(run.id)} busy={busy || opening !== null || !engine} opening={opening === run.id} />)}</div>}
      <div className="library-catalog-note"><Fingerprint size={13} /><p>{history.length >= 60 ? 'The catalog shows the 60 most recent local runs. ' : ''}JSON includes the experiment record. CSV includes step-by-step metrics. Stars are private to this browser.</p><button className="text-button" onClick={() => navigate('methodology')}>Read methodology <ArrowUpRight size={12} /></button></div>
    </section>
  </>
}
