import { create } from 'zustand'
import type { AuditRecord, Dims, MeasureKey, Plan, PlanItem, RoomModel } from './types'
import { optionsFor, productById } from './data'
import { effective, overall, refit } from './lib/refit'
import { splitName } from './lib/format'

export type Stage = 'start' | 'reading' | 'ready' | 'running' | 'done'
/** What the agent has proven about an item so far. The 3D view draws each phase differently. */
export type Phase = 'picked' | 'verified' | 'in_cart'
export type CameraPreset = 'iso' | 'top' | 'front'
/** Furniture the scan found already in the room. */
export type ExistingMode = 'show' | 'ghost' | 'hidden'

/** A product the agent rejected, shown at true size for a moment where it would have gone. */
export interface Ghost {
  key: number
  slot: string
  productId: string
  name: string
  dims: Dims
  why: string
  status: string
}

export interface AppState {
  stage: Stage
  plan: Plan | null
  /** GLB to show. null = draw the room from plan.room. */
  modelUrl: string | null
  modelLabel: string | null
  /** Set by the 3D scene once the model is loaded and measured. */
  room: RoomModel | null

  audit: AuditRecord[]
  placed: Record<string, Phase>
  activeSlot: string | null
  ghost: Ghost | null

  selectedSlot: string | null
  hoveredSlot: string | null
  camera: CameraPreset
  cameraNonce: number
  existing: ExistingMode
  measuring: MeasureKey | null
  overrides: Partial<Record<MeasureKey, number>>
  cartOpen: boolean
  budget: number | null
  runError: string | null

  openRoom: (o: { plan: Plan; modelUrl: string | null; modelLabel: string | null }) => void
  setRoom: (room: RoomModel | null) => void
  roomReady: () => void
  startRun: () => void
  applyRecord: (r: AuditRecord) => void
  finishRun: () => void
  showAll: () => void
  clearGhost: (key?: number) => void
  select: (slot: string | null) => void
  hover: (slot: string | null) => void
  setCamera: (c: CameraPreset) => void
  setExisting: (m: ExistingMode) => void
  setMeasuring: (k: MeasureKey | null) => void
  setOverride: (k: MeasureKey, v: number | null) => void
  setCartOpen: (open: boolean) => void
  setBudget: (b: number | null) => void
  /** Replace a slot's item with another catalog product (fit re-checked by fit.options; Senso not yet). */
  swap: (slot: string, productId: string) => void
  reset: () => void
}

let ghostKey = 0

const blank = {
  stage: 'start' as Stage,
  plan: null,
  modelUrl: null,
  modelLabel: null,
  room: null,
  audit: [] as AuditRecord[],
  placed: {} as Record<string, Phase>,
  activeSlot: null,
  ghost: null,
  selectedSlot: null,
  hoveredSlot: null,
  camera: 'iso' as CameraPreset,
  cameraNonce: 0,
  existing: 'show' as ExistingMode,
  measuring: null,
  overrides: {},
  cartOpen: false,
  budget: null,
  runError: null,
}

/** Fold one audit record into what the room shows. This is the only place run state changes. */
function fold(s: AppState, r: AuditRecord): Partial<AppState> {
  const out: Partial<AppState> = { audit: [...s.audit, r] }
  const slot = r.item_slot
  if (slot) out.activeSlot = slot
  if (r.step === 'pick' && slot) {
    if (r.decision === 'picked') {
      out.placed = { ...s.placed, [slot]: 'picked' }
      out.ghost = null
    } else if (r.product_id) {
      const p = productById[r.product_id]
      if (p) {
        out.ghost = {
          key: ++ghostKey,
          slot,
          productId: p.id,
          name: p.name,
          dims: p.dims_in,
          why: r.why,
          status: r.status ?? 'no_fit',
        }
      }
    }
  }
  if (r.step === 'senso_check' && slot && s.placed[slot]) {
    out.placed = { ...(out.placed ?? s.placed), [slot]: r.status === 'verified' ? 'verified' : s.placed[slot] }
  }
  if (r.step === 'cart' && slot && r.status === 'in_cart') {
    out.placed = { ...(out.placed ?? s.placed), [slot]: 'in_cart' }
  }
  return out
}

export const useApp = create<AppState>((set, get) => ({
  ...blank,

  openRoom: ({ plan, modelUrl, modelLabel }) =>
    set({ ...blank, stage: 'reading', plan, modelUrl, modelLabel, room: null }),
  setRoom: (room) => set({ room }),
  roomReady: () => {
    if (get().stage === 'reading') set({ stage: 'ready' })
  },
  startRun: () =>
    set({ stage: 'running', audit: [], placed: {}, activeSlot: null, ghost: null, selectedSlot: null, existing: 'ghost' }),
  applyRecord: (r) => set((s) => fold(s, r)),
  finishRun: () => set({ stage: 'done', activeSlot: null, ghost: null }),
  showAll: () => {
    const plan = get().plan
    if (!plan) return
    let s = { ...get(), audit: [], placed: {}, ghost: null } as AppState
    for (const r of plan.audit) s = { ...s, ...fold(s, r) }
    set({ audit: s.audit, placed: s.placed, stage: 'done', activeSlot: null, ghost: null, existing: 'ghost' })
  },
  clearGhost: (key) => {
    const g = get().ghost
    if (g && (key === undefined || g.key === key)) set({ ghost: null })
  },
  select: (slot) => set({ selectedSlot: slot, cartOpen: slot ? false : get().cartOpen }),
  hover: (slot) => {
    if (get().hoveredSlot !== slot) set({ hoveredSlot: slot })
  },
  setCamera: (camera) => set((s) => ({ camera, cameraNonce: s.cameraNonce + 1 })),
  setExisting: (existing) => set({ existing }),
  setMeasuring: (measuring) => set({ measuring }),
  // A tape measurement from the person. Every piece is re-checked against it, and the change is logged.
  setOverride: (k, v) =>
    set((s) => {
      const overrides = { ...s.overrides }
      if (v === null) delete overrides[k]
      else overrides[k] = v
      if (!s.plan) return { overrides, measuring: null }
      const label = { wall: 'wall', depth: 'depth of the room', door_width: 'door width', door_height: 'door height' }[k]
      const before = Object.fromEntries(s.plan.items.map((i) => [i.slot, i.fit.verdict]))
      const items = s.plan.items.map((i) => {
        const results = refit(i.fit.results, s.plan!.room, overrides)
        return { ...i, fit: { verdict: overall(results), results } }
      })
      const flipped = items.filter((i) => s.placed[i.slot] && i.fit.verdict !== before[i.slot])
      const broken = items.filter((i) => s.placed[i.slot] && i.fit.verdict !== 'fits')
      const m = effective(s.plan.room, overrides, k)
      const was = s.plan.room[k]
      const changes = flipped.length
        ? flipped
            .map((i) => {
              const bad = i.fit.results.find((r) => r.verdict === i.fit.verdict)
              return i.fit.verdict === 'fits'
                ? `${splitName(i.name)[0]} fits again`
                : `${splitName(i.name)[0]} no longer fits (${bad?.math ?? i.fit.verdict})`
            })
            .join('; ')
        : 'every piece keeps its verdict'
      const rec: AuditRecord = {
        ts: new Date().toISOString(),
        step: 'measure',
        decision: v === null ? `measurement removed: ${label}` : `you measured the ${label}`,
        why:
          v === null
            ? `Back to ${was.value_in} in (${was.source}). Re-checked ${Object.keys(s.placed).length} pieces: ${changes}.`
            : `${m.value_in} in by tape; the agent used ${was.value_in} in (${was.source}). Re-checked ${Object.keys(s.placed).length} pieces: ${changes}.`,
        source: { kind: 'you' },
        status: broken.length ? 'no_fit' : 'fits',
        input: { [k]: v },
      }
      const hasRun = s.stage === 'running' || s.stage === 'done'
      return {
        overrides,
        measuring: null,
        plan: { ...s.plan, items },
        audit: hasRun ? [...s.audit, rec] : s.audit,
        // Open the first piece that stopped fitting, so the fix is one click away.
        selectedSlot: flipped.find((i) => i.fit.verdict !== 'fits')?.slot ?? s.selectedSlot,
        cartOpen: flipped.some((i) => i.fit.verdict !== 'fits') ? false : s.cartOpen,
      }
    }),
  setCartOpen: (cartOpen) => set({ cartOpen, selectedSlot: cartOpen ? null : get().selectedSlot }),
  setBudget: (budget) => set({ budget }),
  swap: (slot, productId) =>
    set((s) => {
      if (!s.plan) return {}
      const p = productById[productId]
      const raw = optionsFor(s.plan.plan_id, slot).find((o) => o.id === productId)
      const results = raw ? refit(raw.fit_results, s.plan.room, s.overrides) : []
      const opt = raw ? { ...raw, fit_results: results, fit: overall(results) } : undefined
      const old = s.plan.items.find((i) => i.slot === slot)
      if (!p || !opt || !old) return {}
      const item: PlanItem = {
        slot,
        product_id: p.id,
        name: p.name,
        price_usd: p.price_usd,
        dims_in: p.dims_in,
        image_url: p.image_url,
        source_url: p.source_url,
        style: null,
        why:
          opt.fit === 'fits'
            ? `You chose this one. It passes all ${results.length} fit checks for this room${opt.best_value ? ', and nothing that fits is cheaper and better rated' : ''}.`
            : opt.why,
        why_source: { kind: 'fit' },
        fit: { verdict: opt.fit, results: opt.fit_results },
        senso: null,
        rejected: [],
      }
      const items = s.plan.items.map((i) => (i.slot === slot ? item : i))
      const cartItems = items.map((i) => ({
        product_id: i.product_id,
        name: i.name,
        price_usd: i.price_usd,
        source_url: i.source_url,
      }))
      const total = Math.round(items.reduce((sum, i) => sum + (i.price_usd ?? 0), 0) * 100) / 100
      const rec: AuditRecord = {
        ts: new Date().toISOString(),
        step: 'swap',
        decision: 'swapped by you',
        why: `You swapped ${old.name} for ${p.name}. Fit re-checked against the room: ${opt.fit === 'fits' ? `all ${results.length} checks pass` : opt.why}. Senso has not checked this one yet.`,
        source: { kind: 'you' },
        status: opt.fit,
        item_slot: slot,
        product_id: p.id,
      }
      return {
        plan: { ...s.plan, items, cart: { ...s.plan.cart, items: cartItems, total_usd: total } },
        audit: [...s.audit, rec],
        placed: { ...s.placed, [slot]: 'picked' },
      }
    }),
  reset: () => set({ ...blank }),
}))

export const itemBySlot = (plan: Plan | null, slot: string | null): PlanItem | null =>
  (slot && plan?.items.find((i) => i.slot === slot)) || null

/** Items the agent has placed so far, in plan order. */
export const placedItems = (s: Pick<AppState, 'plan' | 'placed'>): PlanItem[] =>
  s.plan ? s.plan.items.filter((i) => s.placed[i.slot]) : []
