import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { api } from '../src/services/api'
import type { ExperimentConfig, Frame, Run } from '../src/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function fixtureRun(id: string, config: ExperimentConfig, state: Run['state'] = 'running'): Run {
  return { id, config, state, step: 0, created_at: '2026-01-01T00:00:00Z', dataset: { id: 'simulation', name: 'Simulation', category: 'CONTROLLED_SIMULATION', ground_truth: true, note: '' },
    environment_hash: 'environment', receiver_hash: 'receiver', frequencies_mhz: [], metrics: {}, engine_version: 'test', policy_input: 'observations_only' }
}

const frame = (label = 'evaluation'): Frame => ({ step: 0, timestamp_ms: 0, policies: {}, evaluation: { label, active_bands: [], energy: [] } })

test.describe('request and mission ordering', () => {
  let mission: typeof import('../src/stores/mission')
  let originalFetch: typeof fetch

  test.beforeEach(async () => {
    originalFetch = globalThis.fetch
    Object.defineProperty(globalThis, 'location', { configurable: true, value: { hash: '' } })
    Object.defineProperty(globalThis, 'window', { configurable: true, value: { scrollTo() {} } })
    mission = await import('../src/stores/mission')
    mission.useMission.setState(mission.useMission.getInitialState(), true)
  })

  test.afterEach(() => {
    globalThis.fetch = originalFetch
    Reflect.deleteProperty(globalThis, 'location')
    Reflect.deleteProperty(globalThis, 'window')
  })

  test('requests have readable validation errors, a deadline, and explicit cancellation', async () => {
    globalThis.fetch = async () => Response.json({ detail: [{ loc: ['body', 'seed'], msg: 'Must be non-negative' }] }, { status: 422 })
    await expect(api('/invalid')).rejects.toThrow('seed: Must be non-negative')
    globalThis.fetch = async () => new Response('<html>Unavailable</html>', { status: 503, statusText: 'Service Unavailable' })
    await expect(api('/unavailable')).rejects.toThrow('503 Service Unavailable')
    globalThis.fetch = async () => new Response('not JSON')
    await expect(api('/malformed')).rejects.toThrow('invalid JSON')
    globalThis.fetch = async (_url, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    })
    await expect(api('/slow', undefined, { timeoutMs: 10 })).rejects.toThrow('did not respond')
    const controller = new AbortController()
    const pending = api('/cancel', undefined, { signal: controller.signal })
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  })

  test('duplicate pauses share one request and a queued reset cannot be overwritten', async () => {
    const store = mission.useMission
    const old = fixtureRun('old', mission.initialConfig)
    const next = fixtureRun('reset', mission.initialConfig, 'paused')
    store.setState({ run: old, playing: true })
    const paused = deferred<Response>()
    const calls: string[] = []
    globalThis.fetch = async url => {
      const path = String(url)
      calls.push(path)
      if (path.endsWith('/pause')) return paused.promise
      if (path.includes('/trace')) return Response.json({ frames: [frame()] })
      if (path.endsWith('/reset')) return Response.json(next)
      throw new Error(`Unexpected request: ${path}`)
    }
    const first = store.getState().pause()
    const duplicate = store.getState().pause()
    const reset = store.getState().reset()
    expect(duplicate).toBe(first)
    await expect.poll(() => calls.length).toBe(1)
    store.getState().ingest([frame()], 'running', 1, { runId: old.id, judge: false })
    expect(store.getState().frames).toEqual([])
    paused.resolve(Response.json({ ...old, state: 'paused' }))
    await Promise.all([first, duplicate, reset])
    expect(calls.filter(path => path.endsWith('/pause'))).toHaveLength(1)
    expect(store.getState()).toMatchObject({ run: next, frames: [], busy: false, playing: false, speed: 1 })
    store.getState().ingest([frame()], 'running', 1, { runId: old.id, judge: false })
    expect(store.getState().run?.id).toBe(next.id)
    expect(store.getState().frames).toEqual([])
  })

  test('duplicate starts create one run and replay waits for the new live run to stop', async () => {
    const store = mission.useMission
    const live = fixtureRun('new-live', mission.initialConfig)
    const replay = fixtureRun('recorded', mission.initialConfig, 'completed')
    const started = deferred<Response>()
    const stoppedIds: string[] = []
    let starts = 0
    globalThis.fetch = async (url, options) => {
      const path = String(url)
      if (path.endsWith('/start')) { starts++; return started.promise }
      if (path.endsWith('/stop')) { stoppedIds.push(JSON.parse(String(options?.body)).experiment_id); return Response.json({ ...live, state: 'cancelled' }) }
      if (path.endsWith('/experiments')) return Response.json([])
      if (path.includes('/trace')) return Response.json({ frames: [frame()] })
      if (path.endsWith('/recorded')) return Response.json(replay)
      throw new Error(`Unexpected request: ${path}`)
    }
    const first = store.getState().start()
    const duplicate = store.getState().start()
    const replaying = store.getState().loadReplay(replay.id)
    expect(duplicate).toBe(first)
    started.resolve(Response.json(live))
    await Promise.all([first, duplicate, replaying])
    expect(starts).toBe(1)
    expect(stoppedIds).toEqual([live.id])
    expect(store.getState()).toMatchObject({ run: replay, mode: 'REPLAY', busy: false, playing: false })
  })

  test('turning off evaluation removes it immediately and ignores a stale trace response', async () => {
    const store = mission.useMission
    store.setState({ run: fixtureRun('run', mission.initialConfig), frames: [frame()], judge: true })
    const stale = deferred<Response>()
    globalThis.fetch = async url => String(url).includes('judge=true') ? stale.promise : Response.json({ frames: [frame('public-response')] })
    const oldRequest = store.getState().setJudge(true)
    const currentRequest = store.getState().setJudge(false)
    expect(store.getState().frames[0].evaluation).toBeUndefined()
    await currentRequest
    stale.resolve(Response.json({ frames: [frame('stale')] }))
    await oldRequest
    expect(store.getState().judge).toBe(false)
    expect(store.getState().frames[0].evaluation).toBeUndefined()
    expect(store.getState().error).toBeNull()
  })

  test('bootstrap is deduplicated and preserves a configuration edited while loading', async () => {
    const store = mission.useMission
    const status = deferred<Response>()
    const paths: string[] = []
    globalThis.fetch = async url => {
      const path = String(url)
      paths.push(path)
      return path.endsWith('/status') ? status.promise : Response.json(path.endsWith('/methodology') ? { metrics: [] } : [])
    }
    const first = store.getState().bootstrap()
    const duplicate = store.getState().bootstrap()
    store.getState().setConfig({ dataset_id: 'user-selected' })
    status.resolve(Response.json({ default_dataset: 'server-default' }))
    await Promise.all([first, duplicate])
    expect(paths).toHaveLength(5)
    expect(store.getState().config.dataset_id).toBe('user-selected')
    expect(store.getState().engine).toBe(true)
  })
})

interface TestSocket {
  readyState: number
  onopen: (() => void) | null
  onmessage: ((event: { data: string }) => void) | null
  onclose: (() => void) | null
  onerror: (() => void) | null
  open: () => void
  close: () => void
  send: (payload: string) => void
}

declare global { interface Window { transportTestSockets: TestSocket[] } }

async function prepareTransport(page: Page, request: APIRequestContext) {
  const runs = await (await request.get('/api/experiments')).json() as Run[]
  const recorded = runs.find(run => run.step > 0)!
  expect(recorded).toBeTruthy()
  const trace = await (await request.get(`/api/experiment/${recorded.id}/trace?limit=2`)).json() as { frames: Frame[] }
  const live = { ...recorded, id: 'TRANSPORT-TEST', state: 'running', step: 0 }
  await page.addInitScript(() => {
    window.transportTestSockets = []
    class FakeSocket implements TestSocket {
      static OPEN = 1
      readyState = 0
      onopen: (() => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null
      onclose: (() => void) | null = null
      onerror: (() => void) | null = null
      constructor() { window.transportTestSockets.push(this) }
      open() { this.readyState = 1; this.onopen?.() }
      close() { this.readyState = 3; this.onclose?.() }
      send(payload: string) { this.onmessage?.({ data: payload }) }
    }
    window.WebSocket = FakeSocket as unknown as typeof WebSocket
  })
  await page.route('**/api/experiment/start', route => route.fulfill({ json: live }))
  await page.goto('/')
  await expect(page.getByText('LOCAL ENGINE ONLINE')).toBeVisible()
  await page.getByRole('button', { name: /START LIVE DEMO/ }).click()
  await expect.poll(() => page.evaluate(() => window.transportTestSockets.length)).toBe(1)
  return { live, trace }
}

test('malformed stream messages recover through HTTP without a page exception', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const { trace } = await prepareTransport(page, request)
  let polls = 0
  await page.route('**/api/experiment/TRANSPORT-TEST/trace?*', route => {
    polls++
    return route.fulfill({ json: { frames: trace.frames, total: trace.frames.length, state: 'running' } })
  })
  await page.evaluate(() => {
    const socket = window.transportTestSockets[0]
    socket.open()
    socket.send('{ malformed JSON')
  })
  await expect.poll(() => polls).toBeGreaterThan(0)
  await expect(page.getByText('The local engine sent an unreadable update. Reconnecting…')).toBeVisible()
  expect(errors).toEqual([])
  await page.evaluate(() => { location.hash = 'library' })
  await expect(page.getByRole('heading', { name: 'Experiment Library', exact: true })).toBeVisible()
})

test('repeated failed reconnects keep one poll in flight and discard it after reset', async ({ page, request }) => {
  const { live, trace } = await prepareTransport(page, request)
  const pendingPoll = deferred<void>()
  let polls = 0
  await page.route('**/api/experiment/TRANSPORT-TEST/trace?*', async route => {
    polls++
    await pendingPoll.promise
    await route.fulfill({ json: { frames: trace.frames, total: trace.frames.length, state: 'running' } }).catch(() => {})
  })
  await page.route('**/api/experiment/reset', route => route.fulfill({ json: { ...live, id: 'RESET-TEST', state: 'paused', step: 0 } }))
  await page.clock.install()
  await page.evaluate(() => window.transportTestSockets[0].close())
  await expect.poll(() => polls).toBe(1)
  await page.clock.fastForward(3100)
  await expect.poll(() => page.evaluate(() => window.transportTestSockets.length)).toBe(2)
  await page.evaluate(() => window.transportTestSockets[1].close())
  await page.clock.fastForward(3100)
  await expect.poll(() => page.evaluate(() => window.transportTestSockets.length)).toBe(3)
  await page.evaluate(() => window.transportTestSockets[2].close())
  await page.clock.fastForward(1200)
  expect(polls).toBe(1)
  await page.getByRole('button', { name: 'Reset experiment', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Resume experiment', exact: true })).toBeEnabled()
  pendingPoll.resolve()
  await page.clock.fastForward(1200)
  await expect(page.getByRole('button', { name: 'Resume experiment', exact: true })).toBeVisible()
  expect(polls).toBe(1)
})
