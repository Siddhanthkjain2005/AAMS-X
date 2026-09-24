import { expect, test } from '@playwright/test'
import type { Run } from '../src/types'

test('library filters real runs, keeps browser favorites, and exports the selected record', async ({ page, request }) => {
  const runs = await (await request.get('/api/experiments')).json() as Run[]
  const run = runs.find(item => item.state === 'completed' && item.step > 0)
  expect(run, 'The demo catalog contains a recorded experiment').toBeTruthy()
  await page.goto('/#library')
  await expect(page.getByRole('heading', { name: 'Experiment Library', exact: true })).toBeVisible()
  await expect(page.locator('.library-run')).toHaveCount(runs.length)

  await page.getByLabel('Filter by source', { exact: true }).selectOption(run!.dataset.category)
  await page.getByLabel('Filter by scenario', { exact: true }).selectOption(run!.config.scenario)
  await page.getByLabel('Filter by state', { exact: true }).selectOption('completed')
  await expect(page.locator('.library-run')).toHaveCount(runs.filter(item => item.dataset.category === run!.dataset.category && item.config.scenario === run!.config.scenario && item.state === 'completed').length)
  await page.getByLabel('Search experiments', { exact: true }).fill(run!.id)
  await expect(page.locator('.library-run')).toHaveCount(1)
  await page.getByRole('button', { name: `Star experiment ${run!.id}`, exact: true }).click()
  await expect(page.getByRole('button', { name: `Unstar experiment ${run!.id}`, exact: true })).toHaveAttribute('aria-pressed', 'true')
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('link', { name: `Download JSON for ${run!.id}`, exact: true }).click()
  expect((await downloadPromise).suggestedFilename()).toBe(`${run!.id}.json`)

  await page.reload()
  await page.getByRole('group', { name: 'Experiment collection', exact: true }).getByRole('button', { name: /^Starred/ }).click()
  await expect(page.locator('.library-run')).toHaveCount(1)
  await expect(page.getByRole('button', { name: `Unstar experiment ${run!.id}`, exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'List view', exact: true }).click()
  await expect(page.locator('.library-list')).toBeVisible()
  await page.getByLabel('Search experiments', { exact: true }).fill('no-such-experiment-321')
  await expect(page.getByRole('heading', { name: 'No experiments match these filters', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters', exact: true }).first().click()
  await expect(page.locator('.library-run')).toHaveCount(1)
})

test('library stays in place after a failed replay and opens the requested successful replay', async ({ page, request }) => {
  const runs = await (await request.get('/api/experiments')).json() as Run[]
  const run = runs.find(item => item.state === 'completed' && item.step > 0)
  expect(run).toBeTruthy()
  await page.goto('/#library')
  await page.getByLabel('Search experiments', { exact: true }).fill(run!.id)
  await expect(page.locator('.library-run')).toHaveCount(1)
  const replayPath = `**/api/experiment/${run!.id}`
  await page.route(replayPath, route => route.fulfill({ status: 503, json: { detail: 'Recorded experiment temporarily unavailable' } }))
  await page.getByRole('button', { name: 'Open replay', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Recorded experiment temporarily unavailable')
  await expect(page.getByRole('heading', { name: 'Experiment Library', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/#library$/)
  await page.unroute(replayPath)
  await page.getByRole('button', { name: 'Open replay', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'AAMS-X vs Open-Loop', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/#duel$/)
  await expect(page.getByLabel('Recorded experiment', { exact: true })).toHaveValue(run!.id)
})
