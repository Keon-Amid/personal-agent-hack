// Starts, skips and cancels an agent run, and keeps an eye on the agent server. One run at a time.
import { apiFor, type RunHandle } from './api/api'
import { approvePlan, fetchPlan, followPlan, type LivePlan } from './api/live'
import { probeServer } from './api/server'
import { effective } from './lib/refit'
import { demoRoomForPlan } from './data'
import { useApp } from './store'
import type { Plan } from './types'

let handle: RunHandle | null = null

/** A live plan is empty for a moment before the agent writes it; keep the room and style we started from. */
function settle(incoming: Plan, base: Plan, styleText: string): Plan {
  return {
    ...incoming,
    room: incoming.room ?? base.room,
    style: incoming.style ?? { style_text: styleText, detected_style: null },
    items: incoming.items ?? [],
    audit: incoming.audit ?? [],
    cart: incoming.cart ?? { items: [], total_usd: 0, delivery_note: base.cart.delivery_note, no_purchase: true },
  }
}

export function startRun(styleText: string) {
  const s = useApp.getState()
  if (!s.plan || s.stage === 'running') return
  handle?.cancel()
  const base = s.plan
  const api = apiFor(s.server.ready)
  // If the server can read this room's scan, let the agent measure it (walls and the real door) and send only
  // what the person taped. Otherwise send every measurement we have.
  const demo = demoRoomForPlan(s.roomPlanId ?? base.plan_id)
  const scanPath = api.mode === 'live' && demo?.modelUrl === s.modelUrl ? (demo?.scanPath ?? null) : null
  const room = scanPath
    ? { ...s.overrides }
    : {
        wall: effective(base.room, s.overrides, 'wall').value_in,
        depth: effective(base.room, s.overrides, 'depth').value_in,
        door_width: effective(base.room, s.overrides, 'door_width').value_in,
        door_height: effective(base.room, s.overrides, 'door_height').value_in,
      }
  s.startRun()
  // A live run is given the tape measurements, so they are part of its plan from here on.
  useApp.setState({ runError: null, runMode: api.mode, ...(api.mode === 'live' ? { overrides: {} } : {}) })
  const h = api.run(
    { plan: base, room, scanPath, styleText, budgetUsd: s.budget },
    (r) => useApp.getState().applyRecord(r),
    (plan) => useApp.setState({ plan: settle(plan, base, styleText) }),
  )
  handle = h
  h.done
    .then((plan) => {
      if (handle !== h || !plan) return
      if (api.mode === 'live') useApp.setState({ plan: settle(plan, base, styleText) })
      useApp.getState().finishRun()
    })
    .catch((err: unknown) => {
      if (handle !== h) return
      useApp.setState({
        stage: 'ready',
        plan: base,
        audit: [],
        placed: {},
        activeSlot: null,
        ghost: null,
        runMode: null,
        existing: 'show',
        runError: err instanceof Error ? err.message : 'The agent stopped unexpectedly.',
      })
    })
}

/** Play the recorded run for this room, whatever the server is doing. */
export function startReplay() {
  const s = useApp.getState()
  if (!s.plan || s.stage === 'running') return
  handle?.cancel()
  const base = s.plan
  s.startRun()
  useApp.setState({ runError: null, runMode: 'mock' })
  const h = apiFor(false).run({ plan: base, room: {}, styleText: base.style.style_text, budgetUsd: null }, (r) =>
    useApp.getState().applyRecord(r),
  )
  handle = h
  void h.done.then((plan) => {
    if (handle === h && plan) useApp.getState().finishRun()
  })
}

/** Jump to the end of a replay: every record lands at once. */
export function skipRun() {
  handle?.cancel()
  handle = null
  useApp.getState().showAll()
}

export function cancelRun() {
  handle?.cancel()
  handle = null
}

/**
 * Open a plan the agent server made (the agent's own link, /plan/<id>). Shows what exists so far and keeps
 * following it while the agent is still working. Returns false if the server has no such plan.
 */
export async function openServerPlan(planId: string, pick: (plan: Plan) => { modelUrl: string | null; modelLabel: string | null }): Promise<boolean> {
  let first: LivePlan | null
  try {
    first = await fetchPlan(planId)
  } catch {
    return false
  }
  if (!first || !first.room) return false
  handle?.cancel()
  const base = settle(first, first, first.style?.style_text ?? '')
  useApp.getState().openRoom({ plan: base, ...pick(base) })
  useApp.getState().startRun()
  useApp.setState({ runMode: 'live' })
  const h = followPlan(
    planId,
    (r) => useApp.getState().applyRecord(r),
    (plan) => useApp.setState({ plan: settle(plan, base, base.style.style_text) }),
  )
  handle = h
  h.done
    .then((plan) => {
      if (handle !== h || !plan) return
      useApp.setState({ plan: settle(plan, base, base.style.style_text) })
      useApp.getState().finishRun()
    })
    .catch((err: unknown) => {
      if (handle !== h) return
      useApp.getState().finishRun()
      useApp.setState({ runError: err instanceof Error ? err.message : 'The agent stopped before it finished.' })
    })
  return true
}

/** The person's OK on the cart. A live plan is approved by the server, which writes the audit record. */
export async function approveCart(): Promise<void> {
  const s = useApp.getState()
  if (!s.plan) return
  if (s.runMode !== 'live') {
    s.approveLocally()
    return
  }
  const before = s.plan
  let next: LivePlan
  try {
    next = await approvePlan(before.plan_id)
  } catch (err) {
    // The server may have updated prices before refusing; show the cart as it now stands.
    const now = await fetchPlan(before.plan_id).catch(() => null)
    if (now) {
      const merged = settle(now, before, before.style.style_text)
      useApp.setState((st) => ({ plan: merged, audit: [...st.audit, ...merged.audit.slice(before.audit.length)] }))
    }
    throw err
  }
  const merged = settle(next, before, before.style.style_text)
  const fresh = (merged.audit ?? []).slice(before.audit.length)
  useApp.setState((st) => ({ plan: merged, audit: [...st.audit, ...fresh] }))
}

let planTimer: ReturnType<typeof setInterval> | null = null
/** A finished live plan can still change (the browser agent's bag check, a swap from Claude Desktop). */
function watchPlan() {
  if (planTimer) clearInterval(planTimer)
  planTimer = setInterval(async () => {
    const s = useApp.getState()
    if (s.runMode !== 'live' || s.stage !== 'done' || !s.plan) return
    try {
      const next = await fetchPlan(s.plan.plan_id)
      const cur = useApp.getState()
      if (!next || !cur.plan || cur.plan.plan_id !== next.plan_id) return
      const known = cur.plan.audit?.length ?? 0
      if ((next.audit?.length ?? 0) <= known) return
      const merged = settle(next, cur.plan, cur.plan.style.style_text)
      useApp.setState({ plan: merged, audit: [...cur.audit, ...merged.audit.slice(known)] })
    } catch {
      /* the server may be restarting; try again next tick */
    }
  }, 3000)
}

let watching = false
/** Ask the agent server how it is doing, now and every few seconds. */
export function watchServer() {
  if (watching) return
  watching = true
  watchPlan()
  const tick = async () => {
    useApp.getState().setServer(await probeServer())
    setTimeout(tick, document.hidden ? 15000 : 5000)
  }
  void tick()
}
