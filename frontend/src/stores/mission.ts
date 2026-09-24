import { create } from 'zustand'
import type { Dataset, ExperimentConfig, Frame, MetricDefinition, Page, Run, RunState, Scenario } from '../types'
import { api } from '../services/api'

export const initialConfig: ExperimentConfig = {
  seed: 42, scenario: 'sudden', horizon: 360, dataset_id: 'simulation', algorithms: ['fixed', 'magnts'],
  receiver: { bands: 48, window_width: 4, frequency_min_mhz: 2000, frequency_max_mhz: 6000, slot_ms: 100,
    min_dwell_ms: 10, retune_ms: 8, scan_latency_ms: 1, noise_floor_db: -96, noise_std_db: 1.4,
    threshold_db: 5, snr_db: 12, false_alarm_probability: 0.003, miss_probability: 0.03, switching_cost: 0.3 },
}

interface MissionStore {
  page: Page; config: ExperimentConfig; run: Run | null; frames: Frame[]; datasets: Dataset[]; scenarios: Scenario[]
  history: Run[]; methodology: MetricDefinition[]; engine: boolean; connected: boolean; error: string | null
  busy: boolean; judge: boolean; mode: 'LIVE' | 'REPLAY'; speed: 1 | 2 | 4; playing: boolean; cursor: number
  inspectedStep: number | null; traceOpen: boolean; research: boolean
  navigate: (page: Page) => void; bootstrap: () => Promise<void>; setConfig: (config: Partial<ExperimentConfig>) => void
  start: (config?: ExperimentConfig, page?: Page) => Promise<void>; pause: () => Promise<void>; resume: () => Promise<void>
  reset: () => Promise<void>; setSpeed: (speed: 1 | 2 | 4) => Promise<void>; setJudge: (judge: boolean) => Promise<void>
  loadReplay: (id: string) => Promise<void>; refreshHistory: () => Promise<void>
  ingest: (frames: Frame[], state: RunState, total: number, source?: { runId: string; judge: boolean }) => void
  inspect: (step: number | null) => Promise<void>; openTrace: () => Promise<void>; closeTrace: () => void; advanceReplay: () => void
}

function message(error: unknown) { return error instanceof Error ? error.message : String(error) }

// Removing evaluation data immediately also covers a failed or superseded trace request.
function publicFrame(frame: Frame): Frame {
  const visible = { ...frame }
  delete visible.evaluation
  visible.policies = Object.fromEntries(Object.entries(frame.policies).map(([name, policy]) => {
    if (!policy) return [name, policy]
    const publicPolicy = { ...policy }
    delete publicPolicy.evaluation
    return [name, publicPolicy]
  }))
  return visible
}

function mergeFrames(current: Frame[], incoming: Frame[], judge: boolean): Frame[] {
  const frames = current.slice()
  for (const frame of incoming) frames[frame.step] = judge ? frame : publicFrame(frame)
  return frames
}

export const useMission = create<MissionStore>((set, get) => {
  let pendingControl: { key: string; promise: Promise<void> } | null = null
  let bootstrapRequest: Promise<void> | null = null
  let historyRequest: Promise<void> | null = null
  let traceRequest: Promise<void> | null = null
  let judgeController: AbortController | null = null
  let inspectionVersion = 0
  let configVersion = 0
  let speedRequest: Promise<void> | null = null

  // Serialize server mutations so an older response cannot restore a replaced run.
  // Repeated clicks on the same pending action share its request.
  const control = (key: string, action: () => Promise<void>): Promise<void> => {
    if (pendingControl?.key === key) return pendingControl.promise
    const previous = pendingControl?.promise ?? Promise.resolve()
    set({ busy: true, error: null, connected: false })
    const promise = previous.then(action).catch(error => set({ error: message(error) })).finally(() => {
      if (pendingControl?.promise === promise) {
        pendingControl = null
        set({ busy: false })
      }
    })
    pendingControl = { key, promise }
    return promise
  }

  const stopLive = async () => {
    const { run, mode } = get()
    if (run && mode === 'LIVE' && ['running', 'paused'].includes(run.state)) {
      const stopped = await api<Run>('/api/experiment/stop', { experiment_id: run.id })
      set({ run: stopped, playing: false })
    }
  }

  const trace = async (id: string): Promise<Frame[]> => {
    // A view toggle can arrive while loading a replay or pausing. Only commit
    // the response corresponding to the current view.
    for (;;) {
      const judge = get().judge
      const result = await api<{ frames: Frame[] }>(`/api/experiment/${encodeURIComponent(id)}/trace?limit=2000&judge=${judge}`)
      if (get().judge === judge) return result.frames
    }
  }

  return {
    page: (location.hash.slice(1) || 'command') as Page, config: initialConfig, run: null, frames: [],
    datasets: [], scenarios: [], history: [], methodology: [], engine: false, connected: false,
    error: null, busy: false, judge: false, mode: 'LIVE', speed: 1, playing: false, cursor: 0,
    inspectedStep: null, traceOpen: false, research: false,
    navigate: (page) => { location.hash = page; set({ page }); window.scrollTo({ top: 0, behavior: 'instant' }) },
    bootstrap: () => {
      if (bootstrapRequest) return bootstrapRequest
      const version = configVersion
      bootstrapRequest = (async () => {
        try {
          const [status, datasets, scenarios, history, methodology] = await Promise.all([
            api<{ default_dataset: string }>('/api/status'), api<Dataset[]>('/api/datasets'),
            api<Scenario[]>('/api/scenarios'), api<Run[]>('/api/experiments'),
            api<{ metrics: MetricDefinition[] }>('/api/methodology'),
          ])
          set({ engine: true, datasets, scenarios, history, methodology: methodology.metrics,
            ...(!get().run && version === configVersion ? { config: { ...get().config, dataset_id: status.default_dataset } } : {}),
            ...(!get().engine ? { error: null } : {}),
          })
        } catch (error) { set({ engine: false, error: `Local engine unavailable. Start ./start_demo.sh, then retry. ${message(error)}` }) }
        finally { bootstrapRequest = null }
      })()
      return bootstrapRequest
    },
    setConfig: (config) => { configVersion++; set({ config: { ...get().config, ...config } }) },
    start: (config, page = 'duel') => {
      const requested = config ?? get().config
      return control(`start:${JSON.stringify(requested)}:${page}`, async () => {
        await stopLive()
        const run = await api<Run>('/api/experiment/start', requested)
        inspectionVersion++
        judgeController?.abort()
        set({ run, config: run.config, frames: [], mode: 'LIVE', playing: run.state === 'running', cursor: 0,
          inspectedStep: null, traceOpen: false, speed: 1 })
        get().navigate(page)
        await get().refreshHistory()
      })
    },
    pause: () => control('pause', async () => {
      const { run, mode } = get()
      set({ playing: false })
      if (!run || mode === 'REPLAY' || run.state !== 'running') return
      const paused = await api<Run>('/api/experiment/pause', { experiment_id: run.id })
      // Keep the acknowledged state even if the subsequent trace refresh fails.
      set({ run: paused })
      const frames = await trace(run.id)
      set({ frames: mergeFrames([], frames, get().judge) })
    }),
    resume: () => control('resume', async () => {
      const { run, mode, speed, frames, cursor } = get()
      if (!run) return
      inspectionVersion++
      if (mode === 'REPLAY') {
        set({ playing: frames.length > 0, inspectedStep: null, cursor: cursor >= frames.length - 1 ? 0 : cursor })
        return
      }
      if (!['running', 'paused'].includes(run.state)) return
      const next = await api<Run>('/api/experiment/resume', { experiment_id: run.id, speed })
      set({ run: next, playing: next.state === 'running', inspectedStep: null })
    }),
    reset: () => control('reset', async () => {
      const { run, mode } = get()
      if (!run) return
      inspectionVersion++
      if (mode === 'REPLAY') { set({ cursor: 0, playing: false, inspectedStep: null }); return }
      set({ playing: false })
      const next = await api<Run>('/api/experiment/reset', { experiment_id: run.id })
      judgeController?.abort()
      set({ run: next, frames: [], playing: false, cursor: 0, inspectedStep: null, traceOpen: false, speed: 1 })
    }),
    setSpeed: (speed) => {
      set({ speed })
      if (speedRequest) return speedRequest
      speedRequest = (async () => {
        // Keep one speed request in flight; a rapid change sends the latest
        // value next instead of allowing responses to reorder server state.
        for (;;) {
          if (pendingControl) await pendingControl.promise
          const { run, mode, speed: requested } = get()
          if (!run || mode !== 'LIVE') return
          try { await api('/api/experiment/speed', { experiment_id: run.id, speed: requested }) }
          catch (error) {
            if (get().run?.id === run.id && get().mode === mode && get().speed === requested) set({ error: message(error) })
          }
          if (get().run?.id === run.id && get().speed === requested) return
        }
      })().finally(() => { speedRequest = null })
      return speedRequest
    },
    setJudge: async (judge) => {
      judgeController?.abort()
      const controller = new AbortController()
      judgeController = controller
      set(state => ({ judge, ...(!judge ? { frames: state.frames.map(publicFrame) } : {}) }))
      const run = get().run
      if (!run) return
      try {
        const result = await api<{ frames: Frame[] }>(`/api/experiment/${encodeURIComponent(run.id)}/trace?limit=2000&judge=${judge}`, undefined, { signal: controller.signal })
        if (!controller.signal.aborted && get().run?.id === run.id && get().judge === judge) {
          set(state => ({ frames: mergeFrames(state.frames, result.frames, judge) }))
        }
      } catch (error) {
        if (!controller.signal.aborted && get().run?.id === run.id && get().judge === judge) set({ error: message(error) })
      }
    },
    loadReplay: (id) => control(`replay:${id}`, async () => {
      await stopLive()
      const [run, frames] = await Promise.all([api<Run>(`/api/experiment/${encodeURIComponent(id)}`), trace(id)])
      inspectionVersion++
      judgeController?.abort()
      set({ run, config: run.config, frames: mergeFrames([], frames, get().judge), cursor: 0, mode: 'REPLAY',
        playing: false, inspectedStep: null, traceOpen: false })
    }),
    refreshHistory: () => {
      if (historyRequest) return historyRequest
      historyRequest = api<Run[]>('/api/experiments').then(history => set({ history }))
        .catch(error => set({ error: message(error) })).finally(() => { historyRequest = null })
      return historyRequest
    },
    ingest: (batch, state, total, source) => {
      set(s => {
        if (!s.run || s.mode !== 'LIVE' || s.busy || (source && (s.run.id !== source.runId || s.judge !== source.judge))) return s
        if (!batch.length && s.run.state === state && s.run.step === total) return s
        // The first socket batch can contain only eight frames even when total
        // is much larger. Merge it, but never move the reported progress back.
        const frames = mergeFrames(s.frames, batch, s.judge)
        const last = frames[frames.length - 1]
        const metrics = last ? Object.fromEntries(Object.entries(last.policies).map(([name, value]) => [name, value?.metrics])) : s.run.metrics
        const nextState = total < s.run.step ? s.run.state : state
        return { frames, run: { ...s.run, step: Math.max(total, s.run.step), state: nextState, metrics },
          playing: nextState === 'running' && s.inspectedStep === null }
      })
    },
    inspect: async (step) => {
      const version = ++inspectionVersion
      const runId = get().run?.id
      if (step !== null) await get().pause()
      if (version === inspectionVersion && runId === get().run?.id) set({ inspectedStep: step })
    },
    openTrace: () => {
      if (traceRequest) return traceRequest
      traceRequest = (async () => {
        await get().pause()
        if (!get().run) {
          await get().start(undefined, get().page)
          await get().pause()
        }
        await control('trace', async () => {
          const { run, frames, judge, mode } = get()
          if (!run) return
          if (frames.length === 0 && mode === 'LIVE' && run.state === 'paused') {
            const frame = await api<Frame>(`/api/experiment/${encodeURIComponent(run.id)}/step?judge=${judge}`, {})
            const visible = get().judge === judge ? [frame] : await trace(run.id)
            set({ frames: mergeFrames([], visible, get().judge), run: { ...run, step: frame.step + 1 } })
          }
          set({ traceOpen: true })
        })
      })().finally(() => { traceRequest = null })
      return traceRequest
    },
    closeTrace: () => set({ traceOpen: false }),
    advanceReplay: () => set(s => s.mode !== 'REPLAY' || !s.playing || s.busy ? s
      : s.cursor < s.frames.length - 1 ? { cursor: s.cursor + 1 } : { playing: false }),
  }
})

export function useCurrentFrame(): Frame | undefined {
  return useMission(s => s.frames[s.inspectedStep ?? (s.mode === 'REPLAY' ? s.cursor : s.frames.length - 1)])
}
