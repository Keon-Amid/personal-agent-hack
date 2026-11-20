// One interface, two implementations: mock.ts replays a recorded real run, live.ts drives the team's agent
// server (server/app.py). By default the app picks for itself: live whenever the server is up and ready,
// replay otherwise. VITE_API=mock or VITE_API=live forces one.
import type { AuditRecord, Plan } from '../types'
import { mockApi } from './mock'
import { liveApi } from './live'

export interface RunHandle {
  /** Resolves with the finished plan, or null if the run was cancelled. */
  done: Promise<Plan | null>
  cancel: () => void
}

export interface RoomInput {
  wall: number
  depth: number
  door_width: number
  door_height: number
}

export interface RunInput {
  /** The room's recorded plan: its measurements, and (in replay) the run to play back. */
  plan: Plan
  /** Measurements to send. With scanPath set, only the ones the person taped (they override the scan). */
  room: Partial<RoomInput>
  /** Repo-relative path of the room's scan, when the server can read it. */
  scanPath?: string | null
  styleText: string
  budgetUsd: number | null
}

export interface Api {
  mode: 'mock' | 'live'
  /** Runs the agent. onRecord fires once per audit record, in order; onPlan when the plan itself grows (live). */
  run: (input: RunInput, onRecord: (r: AuditRecord) => void, onPlan?: (p: Plan) => void) => RunHandle
}

export const API_PREF: 'mock' | 'live' | 'auto' =
  import.meta.env.VITE_API === 'mock' ? 'mock' : import.meta.env.VITE_API === 'live' ? 'live' : 'auto'

export const wantsLive = (serverReady: boolean) => API_PREF === 'live' || (API_PREF === 'auto' && serverReady)
export const apiFor = (serverReady: boolean): Api => (wantsLive(serverReady) ? liveApi : mockApi)
