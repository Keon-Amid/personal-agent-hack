// Re-run a fit verdict against a measurement the person just took with a tape.
// Every FitResult from fit/ carries need_in (what the piece needs), so the verdict is the same comparison
// fit/checks.py makes (_verdict): need <= value - error -> fits, need > value + error -> no_fit, else unsure.
import type { FitResult, MeasureKey, Measurement, Option, PlanRoom, Verdict } from '../types'

export type Overrides = Partial<Record<MeasureKey, number>>

const KEY_OF: Record<string, MeasureKey> = {
  wall: 'wall',
  floor: 'depth',
  doorway_width: 'door_width',
  doorway_height: 'door_height',
  rug_width: 'wall',
  rug_depth: 'depth',
}

const g = (v: number) => String(Math.round(v * 1000) / 1000)

export const effective = (room: PlanRoom, overrides: Overrides, k: MeasureKey): Measurement => {
  const o = overrides[k]
  return o !== undefined ? { value_in: o, error_in: 0, source: 'you measured' } : room[k]
}

export const overall = (rs: FitResult[]): Verdict =>
  rs.some((r) => r.verdict === 'no_fit') ? 'no_fit' : rs.some((r) => r.verdict === 'unsure') ? 'unsure' : 'fits'

export function refit(results: FitResult[], room: PlanRoom, overrides: Overrides): FitResult[] {
  return results.map((r) => {
    const k = KEY_OF[r.check]
    if (!k || r.need_in === undefined) return r
    const m = effective(room, overrides, k)
    const same = r.available && r.available.value_in === m.value_in && r.available.error_in === m.error_in
    if (same) return r
    const verdict: Verdict = r.need_in <= m.value_in - m.error_in ? 'fits' : r.need_in > m.value_in + m.error_in ? 'no_fit' : 'unsure'
    const sym = { fits: '≤', no_fit: '>', unsure: '≈' }[verdict]
    const lhs = r.math.split(/\s[≤>≈]\s/)[0]
    const avail = `${g(m.value_in)} in${m.error_in ? ` ±${g(m.error_in)}` : ''} (${m.source})`
    return { ...r, verdict, math: `${lhs} ${sym} ${avail}`, available: m, margin_in: Math.round((m.value_in - r.need_in) * 100) / 100 }
  })
}

export function refitOption(o: Option, room: PlanRoom, overrides: Overrides): Option {
  if (!Object.keys(overrides).length) return o
  const fit_results = refit(o.fit_results, room, overrides)
  const fit = overall(fit_results)
  if (fit === o.fit) return { ...o, fit_results }
  const bad = fit_results.find((r) => r.verdict === fit)
  return { ...o, fit, fit_results, best_value: fit === 'fits' && o.best_value, why: fit === 'fits' ? 'fits with your measurement' : `${fit}: ${bad?.math ?? ''}` }
}
