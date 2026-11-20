// One interface, two implementations. VITE_API=mock (default) replays a recorded real run; VITE_API=live calls
// kyle's server. The UI never knows which one it has, except for the "Replay" pill.
import type { AuditRecord, Plan } from '../types'
import { mockApi } from './mock'
import { liveApi } from './live'

export interface RunHandle {
  /** Resolves with the finished plan, or null if the run was cancelled. */
  done: Promise<Plan | null>
  cancel: () => void
}

export interface RunInput {
  plan: Plan
  styleText: string
  budgetUsd: number | null
}

export interface Api {
  mode: 'mock' | 'live'
  /** Runs the agent. onRecord fires once per audit record, in order; onPlan when the plan itself grows (live). */
  run: (input: RunInput, onRecord: (r: AuditRecord) => void, onPlan?: (p: Plan) => void) => RunHandle
}

export const API_MODE: 'mock' | 'live' = import.meta.env.VITE_API === 'live' ? 'live' : 'mock'
export const api: Api = API_MODE === 'live' ? liveApi : mockApi
