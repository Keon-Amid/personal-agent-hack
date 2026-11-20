// Is the team's agent server (server/app.py) up, and can it run? Asked at load and every few seconds, so the
// UI goes live by itself the moment the server starts and falls back to replay if it stops.
export interface ServerState {
  /** The server answered. */
  reachable: boolean
  /** It can run the agent: Claude Code and both sponsor keys are present. */
  ready: boolean
  /** What is missing, in plain words, when reachable but not ready. */
  note: string | null
}

interface Health {
  claude_code: boolean
  superlinked_key: boolean
  senso_key: boolean
  runs?: { running: number; max: number }
}

export async function probeServer(): Promise<ServerState> {
  try {
    const res = await fetch('/api/health', { signal: AbortSignal.timeout(2000) })
    if (!res.ok || !(res.headers.get('content-type') ?? '').includes('json')) return { reachable: false, ready: false, note: null }
    const h = (await res.json()) as Health
    const missing = [
      !h.claude_code && 'Claude Code',
      !h.senso_key && 'the Senso key',
      !h.superlinked_key && 'the Superlinked key',
    ].filter(Boolean) as string[]
    return {
      reachable: true,
      ready: missing.length === 0,
      note: missing.length ? `The agent server is up but is missing ${missing.join(' and ')} (.env at the repo root).` : null,
    }
  } catch {
    return { reachable: false, ready: false, note: null }
  }
}
