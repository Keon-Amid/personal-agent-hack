// Starts, skips and cancels an agent run. One run at a time.
import { api, type RunHandle } from './api/api'
import { useApp } from './store'

let handle: RunHandle | null = null

export function startRun(styleText: string) {
  const s = useApp.getState()
  if (!s.plan || s.stage === 'running') return
  handle?.cancel()
  s.startRun()
  useApp.setState({ runError: null })
  const h = api.run(
    { plan: s.plan, styleText, budgetUsd: s.budget },
    (r) => useApp.getState().applyRecord(r),
    (plan) => useApp.setState({ plan }),
  )
  handle = h
  h.done
    .then((plan) => {
      if (handle !== h) return
      if (plan) useApp.getState().finishRun()
    })
    .catch((err: unknown) => {
      if (handle !== h) return
      useApp.setState({ stage: 'ready', runError: err instanceof Error ? err.message : 'The agent stopped unexpectedly.' })
    })
}

/** Jump to the end of the run: every record lands at once. */
export function skipRun() {
  handle?.cancel()
  handle = null
  useApp.getState().showAll()
}

export function cancelRun() {
  handle?.cancel()
  handle = null
}
