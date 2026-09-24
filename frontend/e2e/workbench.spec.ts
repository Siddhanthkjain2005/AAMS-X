import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { BenchmarkResult, Frame, Run } from '../src/types'

const screenshotDirectory = '../docs/screenshots'

function captureErrors(page: Page) {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  return errors
}

async function ready(page: Page) {
  await page.goto('/')
  await expect(page.getByText('LOCAL ENGINE ONLINE')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Command Center', exact: true })).toBeVisible()
}

test('live fair duel, trace, metrics export, cold reset, and deterministic replay controls', async ({ page, request }) => {
  const errors = captureErrors(page)
  await ready(page)
  await expect(page.getByRole('checkbox', { name: 'Ground truth', exact: true })).not.toBeChecked()
  await page.screenshot({ path: `${screenshotDirectory}/command-center.png`, fullPage: true })
  await page.getByLabel('Horizon', { exact: true }).selectOption('96')
  await page.getByRole('button', { name: /START LIVE DEMO/ }).click()
  await expect(page.getByRole('heading', { name: 'AAMS-X vs Open-Loop', exact: true })).toBeVisible()
  let run: Run | undefined
  await expect.poll(async () => {
    const runs: Run[] = await (await request.get('/api/experiments')).json()
    run = runs.find(r => r.config.horizon === 96 && r.state === 'running')
    return run?.step ?? 0
  }).toBeGreaterThan(6)
  const runId = run!.id
  await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/api/experiment/pause')),
    page.getByRole('button', { name: 'Pause experiment', exact: true }).click(),
  ])
  const paused = await (await request.get(`/api/experiment/${runId}`)).json() as Run
  expect(paused.state).toBe('paused')
  await page.waitForTimeout(250)
  expect((await (await request.get(`/api/experiment/${runId}`)).json()).step).toBe(paused.step)
  const trace = await (await request.get(`/api/experiment/${runId}/trace`)).json() as { frames: Frame[] }
  expect(trace.frames[0].evaluation).toBeUndefined()
  expect(trace.frames.every(f => f.policies.magnts!.observations.values.length === 4 && f.policies.fixed!.observations.values.length === 4)).toBe(true)
  const last = trace.frames.at(-1)!.policies.magnts!
  expect(Math.abs(Object.values(last.decision.components).reduce((a, b) => a + b, 0) - last.decision.score)).toBeLessThan(0.0001)
  await page.getByRole('button', { name: 'Trace one decision', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: 'Step 6: Decision scores', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Decision scores', exact: true })).toBeVisible()
  await page.screenshot({ path: `${screenshotDirectory}/decision-trace.png` })
  await page.getByRole('button', { name: 'Step 10: Belief updated', exact: true }).click()
  await expect(page.getByText('Updated probability', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close decision trace', exact: true }).click()
  await page.getByRole('button', { name: 'Playback speed 4x', exact: true }).click()
  await page.getByRole('button', { name: 'Resume experiment', exact: true }).click()
  await expect.poll(async () => (await (await request.get(`/api/experiment/${runId}`)).json()).state, { timeout: 30000 }).toBe('completed')
  await page.getByRole('checkbox', { name: 'Ground truth', exact: true }).check()
  await expect(page.getByText('EVALUATION / JUDGE VIEW', { exact: true })).toBeVisible()
  await page.waitForTimeout(250)
  await page.screenshot({ path: `${screenshotDirectory}/fair-duel.png`, fullPage: true })
  const downloaded = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Export experiment JSON', exact: true }).click()
  const download = await downloaded
  expect(download.suggestedFilename()).toBe(`${runId}.json`)
  const exported = JSON.parse(await readFile((await download.path())!, 'utf-8')) as Run & { frames: Frame[] }
  expect(exported.frames).toHaveLength(96)
  expect(exported.environment_hash).toBe(paused.environment_hash)
  expect(exported.trace_hash).toMatch(/^[a-f0-9]{64}$/)
  await page.getByRole('button', { name: 'Reset experiment', exact: true }).click()
  await expect.poll(async () => {
    const runs = await (await request.get('/api/experiments')).json() as Run[]
    const cold = runs.find(r => r.id !== runId && r.state === 'paused' && r.config.horizon === 96)
    return cold ? { step: cold.step, hash: cold.environment_hash } : null
  }).toEqual({ step: 0, hash: paused.environment_hash })
  expect((await (await request.get(`/api/experiment/${runId}`)).json()).state).toBe('completed')
  await page.getByRole('button', { name: 'REPLAY', exact: true }).click()
  await expect(page.getByText('RECORDED REPRODUCIBLE EXPERIMENT REPLAY', { exact: true })).toBeVisible()
  await page.getByLabel('Recorded experiment', { exact: true }).selectOption(runId)
  await expect(page.getByLabel('Recorded experiment', { exact: true })).toHaveValue(runId)
  await page.getByRole('slider', { name: 'Replay timeline', exact: true }).focus()
  await page.getByRole('slider', { name: 'Replay timeline', exact: true }).press('End')
  await expect(page.getByRole('slider', { name: 'Replay timeline', exact: true })).toHaveValue('95')
  await page.getByRole('button', { name: 'Reset experiment', exact: true }).click()
  await expect(page.getByRole('slider', { name: 'Replay timeline', exact: true })).toHaveValue('0')
  expect(errors).toEqual([])
})

test('all navigation, authentic dataset inspection, periodic evidence, and genuine WebGL scene', async ({ page, request }) => {
  const errors = captureErrors(page)
  await ready(page)
  const runs = await (await request.get('/api/experiments')).json() as Run[]
  const periodic = runs.find(r => r.config.scenario === 'periodic' && r.config.horizon === 420 && r.state === 'completed')!
  expect(periodic).toBeTruthy()
  await page.getByRole('button', { name: /Live Duel/ }).click()
  await page.getByRole('button', { name: 'REPLAY', exact: true }).click()
  await page.getByLabel('Recorded experiment', { exact: true }).selectOption(periodic.id)
  await expect(page.getByLabel('Recorded experiment', { exact: true })).toHaveValue(periodic.id)
  await expect(page.getByRole('slider', { name: 'Replay timeline', exact: true })).toHaveAttribute('max', '419')
  await page.getByRole('slider', { name: 'Replay timeline', exact: true }).focus()
  await page.getByRole('slider', { name: 'Replay timeline', exact: true }).press('End')
  await page.getByRole('button', { name: 'Periodic Challenge', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Periodic Intercept Challenge', exact: true })).toBeVisible()
  await expect(page.getByText('SUPPORTED', { exact: true }).first()).toBeVisible()
  await page.getByRole('checkbox', { name: 'Ground truth', exact: true }).check()
  await expect(page.locator('.data-table tbody tr')).toHaveCount(8)
  await page.screenshot({ path: `${screenshotDirectory}/periodic-challenge.png`, fullPage: true })
  await page.getByRole('button', { name: /Spectrum Cube/ }).click()
  await expect(page.getByRole('heading', { name: 'Spectrum Intelligence Cube', exact: true })).toBeVisible()
  await expect(page.locator('.cube-scene canvas[data-engine]')).toBeVisible()
  await page.waitForTimeout(800)
  const webgl = await page.locator('.cube-scene canvas[data-engine]').evaluate(canvas => {
    const gl = (canvas as HTMLCanvasElement).getContext('webgl2')
    return gl ? gl.getParameter(gl.VERSION) : null
  })
  expect(webgl).toContain('WebGL 2')
  await page.getByRole('checkbox', { name: 'Belief surface', exact: true }).check()
  await page.getByRole('button', { name: 'Top', exact: true }).click()
  await page.getByRole('button', { name: 'Side', exact: true }).click()
  await page.getByRole('button', { name: 'Follow receiver', exact: true }).click()
  await page.getByRole('button', { name: 'Orbit', exact: true }).click()
  await page.getByRole('button', { name: 'Reset', exact: true }).click()
  await page.screenshot({ path: `${screenshotDirectory}/spectrum-cube.png`, fullPage: true })
  for (const [nav, title] of [['AI Observability', 'What the AI knows'], ['Data Provenance', 'Data Integrity & Provenance'], ['Architecture', 'The intelligence loop'], ['Methodology', 'Methodology & limitations'], ['Benchmark Lab', 'Benchmark Lab']] as const) {
    await page.getByRole('button', { name: nav, exact: true }).click()
    await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible()
  }
  await page.getByRole('button', { name: 'Data Provenance', exact: true }).click()
  await expect(page.getByText('ACCESS REQUIRED', { exact: true })).toBeVisible()
  await page.screenshot({ path: `${screenshotDirectory}/data-provenance.png`, fullPage: true })
  await page.getByRole('button', { name: 'Dataset Explorer', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Measured RF spectrum', exact: true })).toBeVisible()
  await expect(page.getByText('ALASKA-ANCHORAGE', { exact: true }).first()).toBeVisible()
  await page.screenshot({ path: `${screenshotDirectory}/measured-rf.png`, fullPage: true })
  await page.getByRole('button', { name: 'RUN RECEIVER REPLAY', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'AAMS-X vs Open-Loop', exact: true })).toBeVisible()
  await expect.poll(async () => {
    const runs = await (await request.get('/api/experiments')).json() as Run[]
    return runs.find(r => r.state === 'running' && r.dataset.category === 'REAL_MEASURED_RF')?.step ?? 0
  }).toBeGreaterThan(2)
  await page.getByRole('button', { name: 'Pause experiment', exact: true }).click()
  const measured = (await (await request.get('/api/experiments')).json() as Run[]).find(r => r.state === 'paused' && r.dataset.category === 'REAL_MEASURED_RF')!
  expect(measured.metrics.magnts!.pd).toBeNull()
  expect(measured.metrics.magnts!.reward_cost).toBeNull()
  expect(errors).toEqual([])
})

test('benchmark controls produce new real results and replayable runs', async ({ page, request }) => {
  const errors = captureErrors(page)
  await ready(page)
  await page.getByRole('button', { name: 'Benchmark Lab', exact: true }).click()
  await page.getByRole('button', { name: 'Periodic Intercept', exact: true }).click()
  await page.getByRole('button', { name: 'Frequency-Agile', exact: true }).click()
  await page.getByLabel('Number of benchmark runs', { exact: true }).fill('1')
  await page.getByLabel('Benchmark horizon', { exact: true }).fill('24')
  await page.getByRole('button', { name: 'RUN BENCHMARK', exact: true }).click()
  await expect.poll(async () => {
    const jobs = await (await request.get('/api/benchmarks')).json() as BenchmarkResult[]
    return jobs.find(j => j.config.horizon === 24)?.state
  }, { timeout: 45000 }).toBe('completed')
  await expect(page.getByText('N/A (n < 2)', { exact: true }).first()).toBeVisible()
  const reports = await (await request.get('/api/benchmarks')).json() as BenchmarkResult[]
  const multiSeed = reports.find(report => report.total === 30 && report.config.runs === 3)
  if (multiSeed) await page.getByLabel('Previous benchmark', { exact: true }).selectOption(multiSeed.id)
  await page.screenshot({ path: `${screenshotDirectory}/benchmark-lab.png`, fullPage: true })
  await page.getByRole('button', { name: 'Replay run', exact: true }).first().click()
  await expect(page.getByRole('heading', { name: 'AAMS-X vs Open-Loop', exact: true })).toBeVisible()
  await expect(page.getByText('RECORDED REPRODUCIBLE EXPERIMENT REPLAY', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('mobile layout, accessible navigation, and missing-dataset fallback', async ({ page, request }) => {
  const errors = captureErrors(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await ready(page)
  await expect(page.getByRole('button', { name: /START LIVE DEMO/ })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: `${screenshotDirectory}/mobile-command-center.png`, fullPage: true })
  await page.getByRole('button', { name: 'Open navigation', exact: true }).click()
  await page.getByRole('button', { name: /Live Duel/ }).click()
  await expect(page.getByRole('heading', { name: 'AAMS-X vs Open-Loop', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const datasets = await (await request.get('/api/datasets')).json()
  await page.route('**/api/datasets', route => route.fulfill({ json: datasets.map((d: { id: string }) => d.id === 'simulation' ? d : { ...d, status: 'not_downloaded' }) }))
  await page.goto('/#explorer')
  await page.reload()
  await expect(page.getByText('LOCAL ENGINE ONLINE')).toBeVisible()
  await expect(page.getByText('No public dataset artifact is installed', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
