// Replay of a recorded real run. The records, their order and their text are exactly what the agent wrote into
// contracts/plan.*.json. Only the waiting is compressed: a 3-minute run plays back in about 25 seconds.
import type { AuditRecord, Plan } from '../types'
import type { Api, RunHandle } from './api'

const SPEED = 0.11 // replay seconds per real second
const MIN_GAP = 150 // ms between records that share a timestamp
const MAX_GAP = 1500
const HOLD_AFTER_REJECT = 1900 // let a rejection be read before the next pick lands
const HOLD_AFTER_PICK = 500

export function replayDelays(audit: AuditRecord[]): number[] {
  return audit.map((r, i) => {
    if (i === 0) return 350
    const prev = audit[i - 1]
    const gap = (Date.parse(r.ts) - Date.parse(prev.ts)) * SPEED
    let d = Math.min(MAX_GAP, Math.max(MIN_GAP, gap))
    if (prev.step === 'pick' && prev.decision !== 'picked') d = Math.max(d, HOLD_AFTER_REJECT)
    else if (prev.step === 'pick') d = Math.max(d, HOLD_AFTER_PICK)
    return d
  })
}

function replay(plan: Plan, onRecord: (r: AuditRecord) => void): RunHandle {
  let cancelled = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const delays = replayDelays(plan.audit)
  const done = new Promise<Plan | null>((resolve) => {
    let i = 0
    const step = () => {
      if (cancelled) return resolve(null)
      if (i >= plan.audit.length) return resolve(plan)
      onRecord(plan.audit[i])
      i += 1
      timer = setTimeout(step, i < delays.length ? delays[i] : 600)
    }
    timer = setTimeout(step, delays[0] ?? 300)
  })
  return {
    done,
    cancel: () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    },
  }
}

export const mockApi: Api = {
  mode: 'mock',
  run: ({ plan }, onRecord) => replay(plan, onRecord),
}
