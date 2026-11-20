// Live mode: the HTTP wrapper around agent.agent.run_agent (see CONTRACT.md, "Agent: agent/").
// STUBBED until that server exists. Two calls, as agreed in the team channel:
//   POST {base}/api/plan   {room:{wall,depth,door_width,door_height}, style_text, budget_total_usd}  -> {plan_id}
//   GET  {base}/api/plan/{id}   -> Plan (contracts/plan.live.json shape); items[] and audit[] grow while it runs
// The UI polls the second one once a second and plays each new audit record as it appears.
import type { Plan } from '../types'
import type { Api, RunHandle } from './api'

const BASE = import.meta.env.VITE_API_BASE ?? ''
const POLL_MS = 1000

export const liveApi: Api = {
  mode: 'live',
  run: ({ plan, styleText, budgetUsd }, onRecord, onPlan): RunHandle => {
    const ctrl = new AbortController()
    let cancelled = false
    const done = (async (): Promise<Plan | null> => {
      const room = {
        wall: plan.room.wall.value_in,
        depth: plan.room.depth.value_in,
        door_width: plan.room.door_width.value_in,
        door_height: plan.room.door_height.value_in,
      }
      const res = await fetch(`${BASE}/api/plan`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        // The budget chip is a budget for the whole room, which the agent calls budget_total_usd.
        body: JSON.stringify({ room, style_text: styleText, budget_total_usd: budgetUsd }),
        signal: ctrl.signal,
      })
      if (!res.ok) throw new Error(`The agent server answered ${res.status}.`)
      const { plan_id } = (await res.json()) as { plan_id: string }
      let seen = 0
      while (!cancelled) {
        const r = await fetch(`${BASE}/api/plan/${plan_id}`, { signal: ctrl.signal })
        if (!r.ok) throw new Error(`The agent server answered ${r.status} while the run was going.`)
        const current = (await r.json()) as Plan
        onPlan?.(current)
        const audit = current.audit ?? []
        for (; seen < audit.length; seen += 1) onRecord(audit[seen])
        if (audit.some((a) => a.step === 'agent' && a.status === 'done')) return current
        await new Promise((ok) => setTimeout(ok, POLL_MS))
      }
      return null
    })()
    return {
      done,
      cancel: () => {
        cancelled = true
        ctrl.abort()
      },
    }
  },
}
