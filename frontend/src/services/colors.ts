export function energyColor(value: number, low: number, high: number, alpha = 1) {
  const t = Math.max(0, Math.min(1, (value - low) / Math.max(1, high - low)))
  const r = Math.round(24 + 130 * t + 28 * t * t)
  const g = Math.round(28 + 72 * t + 80 * t * t * t)
  const b = Math.round(43 + 156 * t - 54 * t * t * t)
  return `rgba(${r},${g},${b},${alpha})`
}
