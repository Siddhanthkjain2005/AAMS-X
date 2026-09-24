import { useEffect } from 'react'
import { useMission } from '../stores/mission'
import { api } from '../services/api'
import type { Frame, Page, RunState } from '../types'

const runStates = new Set<RunState>(['running', 'paused', 'completed', 'cancelled', 'failed'])
const pages = new Set<Page>(['command', 'duel', 'cube', 'knowledge', 'periodic', 'benchmark', 'explorer', 'provenance', 'architecture', 'methodology', 'library'])
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value)
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

function validFrame(value: unknown): value is Frame {
  if (!record(value) || !Number.isSafeInteger(value.step) || (value.step as number) < 0 || !finite(value.timestamp_ms) || !record(value.policies)) return false
  return Object.values(value.policies).every(policy => {
    if (!record(policy) || !record(policy.metrics) || !record(policy.selected_window) || !record(policy.observations)
      || !record(policy.decision) || !record(policy.belief)) return false
    const { decision, belief, observations, selected_window: window } = policy
    return [window.start, window.end, window.width].every(finite)
      && Array.isArray(observations.values) && observations.values.every(record)
      && ['candidates', 'reasons', 'pre_probability', 'pre_uncertainty', 'periodic_candidates', 'memory_matches'].every(key => Array.isArray(decision[key]))
      && record(decision.components) && record(decision.action)
      && ['probability', 'uncertainty', 'information_gain', 'observations', 'last_visit', 'age', 'change_scores', 'change_events', 'periodicity'].every(key => Array.isArray(belief[key]))
  })
}

function validBatch(value: unknown, horizon: number): value is { frames: Frame[]; state: RunState; total: number } {
  return record(value) && runStates.has(value.state as RunState)
    && Number.isSafeInteger(value.total) && (value.total as number) >= 0 && (value.total as number) <= horizon
    && Array.isArray(value.frames) && value.frames.every(frame => validFrame(frame) && frame.step < (value.total as number))
}

export function useTransport() {
  const runId = useMission(s => s.run?.id)
  const mode = useMission(s => s.mode)
  const judge = useMission(s => s.judge)
  const playing = useMission(s => s.playing)
  const speed = useMission(s => s.speed)
  const busy = useMission(s => s.busy)

  useEffect(() => {
    void useMission.getState().bootstrap()
    const navigate = () => {
      const page = location.hash.slice(1) as Page
      useMission.setState({ page: pages.has(page) ? page : 'command' })
    }
    navigate()
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])

  useEffect(() => {
    if (!runId || mode !== 'LIVE' || busy) return
    let stopped = false
    let socket: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let pollTimer: ReturnType<typeof setTimeout> | undefined
    let handshakeTimer: ReturnType<typeof setTimeout> | undefined
    let pollController: AbortController | null = null
    let polling = false
    const current = () => {
      const state = useMission.getState()
      return !stopped && state.run?.id === runId && state.mode === 'LIVE' && state.judge === judge && !state.busy
    }
    const accept = (payload: unknown) => {
      if (!current()) return
      if (!validBatch(payload, useMission.getState().run!.config.horizon)) throw new Error('The local engine sent an invalid update. Reconnecting…')
      useMission.getState().ingest(payload.frames, payload.state, payload.total, { runId, judge })
    }
    const stopPolling = () => {
      polling = false
      clearTimeout(pollTimer)
      pollTimer = undefined
      pollController?.abort()
      pollController = null
    }
    const poll = async () => {
      if (!current() || !polling) return
      const controller = new AbortController()
      pollController = controller
      try {
        const offset = useMission.getState().frames.length
        const payload = await api<unknown>(`/api/experiment/${encodeURIComponent(runId)}/trace?offset=${offset}&judge=${judge}`, undefined, { signal: controller.signal })
        if (!controller.signal.aborted && polling) accept(payload)
      } catch (error) {
        if (!controller.signal.aborted && current()) useMission.setState({ connected: false, error: error instanceof Error ? error.message : String(error) })
      } finally {
        if (pollController === controller) {
          pollController = null
          if (polling && current()) pollTimer = setTimeout(() => { void poll() }, 1000)
        }
      }
    }
    const reconnect = () => {
      if (!current()) return
      useMission.setState({ connected: false })
      if (!polling) { polling = true; void poll() }
      if (!retry) retry = setTimeout(connect, 3000)
    }
    const connect = () => {
      retry = undefined
      if (!current()) return
      const since = useMission.getState().frames.length
      let next: WebSocket
      try {
        next = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/experiment/${encodeURIComponent(runId)}?since=${since}&judge=${judge}`)
      } catch { reconnect(); return }
      socket = next
      // A connection that never opens still gets HTTP fallback and a retry.
      handshakeTimer = setTimeout(() => { if (socket === next && next.readyState !== WebSocket.OPEN) next.close() }, 8000)
      next.onopen = () => {
        if (!current() || socket !== next) { next.close(); return }
        clearTimeout(handshakeTimer)
        stopPolling()
        useMission.setState({ connected: true })
      }
      next.onmessage = event => {
        if (!current() || socket !== next) return
        try {
          const payload: unknown = JSON.parse(event.data)
          if (record(payload) && payload.type === 'error') {
            useMission.setState({ error: typeof payload.message === 'string' ? payload.message : 'The local engine could not stream this experiment.' })
            next.close()
            return
          }
          accept(payload)
        } catch (error) {
          useMission.setState({ error: error instanceof SyntaxError ? 'The local engine sent an unreadable update. Reconnecting…' : error instanceof Error ? error.message : String(error) })
          next.close()
        }
      }
      next.onclose = () => {
        if (!current() || socket !== next) return
        clearTimeout(handshakeTimer)
        socket = null
        reconnect()
      }
      next.onerror = () => next.close()
    }
    connect()
    return () => {
      stopped = true
      clearTimeout(retry)
      clearTimeout(handshakeTimer)
      stopPolling()
      if (socket) {
        socket.onopen = socket.onmessage = socket.onclose = socket.onerror = null
        socket.close()
      }
      useMission.setState({ connected: false })
    }
  }, [runId, mode, judge, busy])

  useEffect(() => {
    if (mode !== 'REPLAY' || !playing || busy) return
    const timer = setInterval(() => useMission.getState().advanceReplay(), 100 / speed)
    return () => clearInterval(timer)
  }, [mode, playing, speed, busy])
}
