// Test harness for the 3D renderer. This is NOT the app's UI: it only feeds <RoomScene> a plan
// and lets you swap the product in each slot, so the renderer can be checked on its own.
//
// Plans it can draw:
//   - the agent's real runs in contracts/ (plan.live.json, plan.room_scan.json, plan.example.json)
//   - web/public/demo-plan.json, a fit-only run written by scripts/demo_plan.py (no agent, no Senso)

import { useEffect, useMemo, useState } from 'react'
import {
  RoomScene, VERDICT_COLOR, VERDICT_LABEL, fmt, fromAgentPlan,
  type AgentPlan, type Candidate, type Plan, type Product, type RenderItem, type RoomScan,
} from './room3d'
import scanUrl from '../../assets/room_scan_geometry.glb?url'
import scanAlign from '../../assets/room_scan_geometry.align.json'

// The LiDAR scan of the room we demo in, and where the room sits inside it (scripts/scan_align.py).
const ROOM_SCAN: RoomScan = {
  url: scanUrl,
  corner_m: [scanAlign.wall_ends_m[0], scanAlign.floor_m, scanAlign.back_wall_m],
  ceiling_in: scanAlign.measured_in.ceiling,
}
import catalogFile from '../../data/products.json'
import planLive from '../../contracts/plan.live.json'
import planRoomScan from '../../contracts/plan.room_scan.json'
import planExample from '../../contracts/plan.example.json'

const catalog: Record<string, Product> = Object.fromEntries(
  (catalogFile.products as unknown as Product[]).map((p) => [p.id, p]),
)

const AGENT_PLANS: Record<string, { label: string; plan: AgentPlan }> = {
  room_scan: { label: 'Agent run · our scanned room (plan.room_scan.json)', plan: planRoomScan as unknown as AgentPlan },
  live: { label: 'Agent run · 88 in wall (plan.live.json)', plan: planLive as unknown as AgentPlan },
  example: { label: 'Fixture · 88 in wall (plan.example.json)', plan: planExample as unknown as AgentPlan },
}
const DEMO = 'demo'
const POSITION_NOTE = 'Item positions are a rule of thumb in the renderer, not chosen by the agent.'

const short = (c: Candidate) => c.product.name.split(' - ')[0]

// ?clean hides the panel (for screenshots); ?plan=live picks the starting plan.
const QUERY = new URLSearchParams(window.location.search)
const CLEAN = QUERY.has('clean')

export default function Harness() {
  const [source, setSource] = useState<string>(() => {
    const p = QUERY.get('plan')
    return p && (p === DEMO || p in AGENT_PLANS) ? p : 'room_scan'
  })
  const [demoPlan, setDemoPlan] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  // slot -> index into that slot's `others`; missing = the plan's own pick
  const [trying, setTrying] = useState<Record<string, number>>({})
  const [useModels, setUseModels] = useState(true)
  const [useScan, setUseScan] = useState(true)

  useEffect(() => {
    if (source !== DEMO || demoPlan) return
    fetch('/demo-plan.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`demo-plan.json: HTTP ${r.status}`))))
      .then(setDemoPlan)
      .catch((e) => setError(`${e.message}. Run: python3 scripts/demo_plan.py`))
  }, [source, demoPlan])

  const plan: Plan | null = useMemo(
    () => (source === DEMO ? demoPlan : fromAgentPlan(AGENT_PLANS[source].plan, catalog, AGENT_PLANS[source].label)),
    [source, demoPlan],
  )

  const shown = useMemo(
    () =>
      (plan?.items ?? []).map((item) => {
        const i = trying[item.slot]
        const cand: Candidate = i != null && item.others?.[i] ? item.others[i] : item
        return { item, cand }
      }),
    [plan, trying],
  )
  const items: RenderItem[] = useMemo(
    () =>
      shown.map(({ item, cand }) => ({
        slot: item.slot,
        product: cand.product,
        fit: cand.fit,
        placement: cand === item ? item.placement : undefined,
      })),
    [shown],
  )

  if (error) return <div className="center-msg">Could not load the plan: {error}</div>
  if (!plan) return <div className="center-msg">Loading the room…</div>
  const notes = [...(plan.stubbed ?? []), POSITION_NOTE]

  return (
    <div className="harness">
      <RoomScene
        key={source}
        room={plan.room}
        items={items}
        selected={selected}
        onSelect={setSelected}
        modelsUrl={useModels ? '/models/' : null}
        scan={source === 'room_scan' && useScan ? ROOM_SCAN : null}
      />

      <div className="panel" style={CLEAN ? { display: 'none' } : undefined}>
        <b>3D renderer · test harness</b>
        <select
          value={source}
          onChange={(e) => {
            setSource(e.target.value)
            setTrying({})
            setSelected(null)
          }}
        >
          {Object.entries(AGENT_PLANS).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
          <option value={DEMO}>Fit-only demo run (demo-plan.json)</option>
        </select>
        <div className="stub">
          <b>{source === DEMO ? 'DEMO DATA' : 'NOTE'}</b>
          {notes.map((s) => (
            <div key={s}>{s}</div>
          ))}
        </div>
        {shown.map(({ item, cand }) => (
          <label key={item.slot} className={selected === item.slot ? 'on' : ''}>
            <span className="dot" style={{ background: VERDICT_COLOR[cand.fit] }} title={VERDICT_LABEL[cand.fit]} />
            <span className="slot">{item.slot.replace('_', ' ')}</span>
            <select
              value={trying[item.slot] ?? -1}
              onFocus={() => setSelected(item.slot)}
              onChange={(e) => {
                const i = Number(e.target.value)
                setSelected(item.slot)
                setTrying(({ [item.slot]: _, ...rest }) => (i < 0 ? rest : { ...rest, [item.slot]: i }))
              }}
            >
              <option value={-1}>
                {short(item)} · {fmt(item.product.dims_in.w)} in · {VERDICT_LABEL[item.fit]}
              </option>
              {(item.others ?? []).map((o, i) => (
                <option key={o.product.id} value={i}>
                  {short(o)} · {fmt(o.product.dims_in.w)} in · {VERDICT_LABEL[o.fit]}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          <input type="checkbox" checked={useModels} onChange={(e) => setUseModels(e.target.checked)} />
          <span>Use 3D models where one exists (off = simple shapes)</span>
        </label>
        {source === 'room_scan' && (
          <label>
            <input type="checkbox" checked={useScan} onChange={(e) => setUseScan(e.target.checked)} />
            <span>Draw the LiDAR scan as the room (off = box from measurements)</span>
          </label>
        )}
        <div className="muted">Drag to turn · scroll to zoom · click an item</div>
      </div>
    </div>
  )
}
