interface ApiOptions { signal?: AbortSignal; timeoutMs?: number }

function errorDetail(value: unknown): string | undefined {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(item => {
    if (item && typeof item === 'object' && 'msg' in item) {
      const location = 'loc' in item && Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== 'body').join('.') : ''
      return `${location ? `${location}: ` : ''}${String(item.msg)}`
    }
    return errorDetail(item)
  }).filter(Boolean).join('; ')
  return undefined
}

export async function api<T>(path: string, body?: unknown, options: ApiOptions = {}): Promise<T> {
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? 30000
  let timedOut = false
  const abort = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) abort()
  else options.signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
  try {
    const response = await fetch(path, {
      signal: controller.signal,
      ...(body === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }),
    })
    const text = await response.text()
    let result: unknown
    try { result = text ? JSON.parse(text) : undefined }
    catch {
      if (response.ok) throw new Error('The local engine returned an invalid JSON response. Please retry.')
    }
    if (!response.ok) {
      const detail = result && typeof result === 'object' && 'detail' in result ? errorDetail(result.detail) : undefined
      throw new Error(detail || `Request failed (${response.status}${response.statusText ? ` ${response.statusText}` : ''}). Please retry.`)
    }
    return result as T
  } catch (error) {
    if (options.signal?.aborted) throw options.signal.reason ?? new DOMException('Request cancelled', 'AbortError')
    if (timedOut) throw new Error(`The local engine did not respond within ${Math.ceil(timeoutMs / 1000)} seconds. Check the connection and retry.`)
    if (error instanceof TypeError) throw new Error('Unable to reach the local engine. Check that it is running and retry.')
    throw error
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}

export function formatNumber(value: unknown, digits = 0): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—'
}
export function percent(value: unknown, digits = 1): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : '—'
}
export function metricNumber(metrics: Record<string, unknown> | undefined, key: string): number | null {
  const value = metrics?.[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
export const names: Record<string, string> = {
  magnts: 'MAG-NTS', fixed: 'Fixed Sweep', random: 'Random', thompson: 'Vanilla Thompson', ucb: 'UCB',
  no_memory: 'No Memory', no_information: 'No Information Gain', no_change: 'No Change Detection',
}
export const componentNames: Record<string, string> = {
  opportunity: 'Learned opportunity', information: 'Information gain', uncertainty: 'Uncertainty',
  memory: 'Associative memory', periodicity: 'Periodic opportunity', recency: 'Revisit priority',
  change: 'Change response', exploration: 'Directed exploration', retune: 'Retuning cost', wasted: 'Empty-scan penalty',
}
