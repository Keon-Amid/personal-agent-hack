// Live mode: the team's agent server, server/app.py (see CONTRACT.md, "HTTP API").
//   POST /api/plan  {room:{wall,depth,door_width,door_height}, style_text, budget_total_usd} -> {plan_id}
//   GET  /api/plan/{id}  -> Plan + run:{status,error}; items[] and audit[] grow while the agent works
//   POST /api/plan/{id}/approve -> Plan + shopping_list (no order is placed)
// The UI polls the plan once a second and plays each new audit record as it appears.
import type { AuditRecord, Plan } from '../types'
import type { Api, RunHandle } from './api'

const POLL_MS = 1000

export type LivePlan = Plan & { run?: { status: string; error: string | null } }

async function problem(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* not JSON */
  }
  return `The agent server answered ${res.status}.`
}

export async function fetchPlan(planId: string, signal?: AbortSignal): Promise<LivePlan | null> {
  const res = await fetch(`/api/plan/${planId}`, { signal })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(await problem(res))
  return (await res.json()) as LivePlan
}

/** Follow a plan the server is working on: every new audit record, then the finished plan. */
export function followPlan(planId: string, onRecord: (r: AuditRecord) => void, onPlan?: (p: Plan) => void): RunHandle {
  const ctrl = new AbortController()
  let cancelled = false
  const done = (async (): Promise<Plan | null> => {
    let seen = 0
    while (!cancelled) {
      const current = await fetchPlan(planId, ctrl.signal)
      if (!current) throw new Error('The agent server no longer has this plan.')
      onPlan?.(current)
      const audit = current.audit ?? []
      for (; seen < audit.length; seen += 1) onRecord(audit[seen])
      const status = current.run?.status
      if (status === 'error' || status === 'interrupted') throw new Error(current.run?.error ?? 'The agent stopped before it finished.')
      if (status === 'done' || (!status && audit.some((a) => a.step === 'agent' && a.status === 'done'))) return current
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
}

export async function approvePlan(planId: string): Promise<LivePlan> {
  const res = await fetch(`/api/plan/${planId}/approve`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' })
  if (!res.ok) throw new Error(await problem(res))
  return (await res.json()) as LivePlan
}

export const liveApi: Api = {
  mode: 'live',
  run: ({ room, styleText, budgetUsd }, onRecord, onPlan): RunHandle => {
    let inner: RunHandle | null = null
    let cancelled = false
    const done = (async (): Promise<Plan | null> => {
      const res = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        // The budget chip is a budget for the whole room, which the agent calls budget_total_usd.
        body: JSON.stringify({ room, style_text: styleText, budget_total_usd: budgetUsd }),
      })
      if (!res.ok) throw new Error(await problem(res))
      const { plan_id } = (await res.json()) as { plan_id: string }
      if (cancelled) return null
      inner = followPlan(plan_id, onRecord, onPlan)
      return inner.done
    })()
    return {
      done,
      cancel: () => {
        cancelled = true
        inner?.cancel()
      },
    }
  },
}
