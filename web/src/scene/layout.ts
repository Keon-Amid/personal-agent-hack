// Where the UI stands each piece on the floor. Inches, floor plane (x, z), rotation in degrees about Y.
// Rotation 0 = width along +x, front facing +z. These are layout rules for showing the plan; the fit verdicts
// themselves come from the fit module (plan.items[].fit), not from here.
import type { PlanItem, Placement, RoomDoor, RoomModel, RoomWall, Vec2 } from '../types'
import { productById } from '../data'
import { distToSegment, pointInPoly, wallFrame } from './roomModel'

interface Rect {
  cx: number
  cz: number
  /** half extents along the item's own width / depth axes */
  hw: number
  hd: number
  rot: number
}
interface Box {
  x0: number
  z0: number
  x1: number
  z1: number
}

export interface LayoutDetail {
  placements: Record<string, Placement>
  /** the wall the anchor piece (sofa / bed) backs onto, and the direction it faces */
  anchorWall: RoomWall | null
  depthWall: RoomWall | null
  facing: Vec2
}

const rad = (d: number) => (d * Math.PI) / 180
const add = (a: Vec2, b: Vec2, k = 1): Vec2 => [a[0] + b[0] * k, a[1] + b[1] * k]
const dot = (a: Vec2, b: Vec2) => a[0] * b[0] + a[1] * b[1]
const rotOf = (f: Vec2) => (Math.atan2(f[0], f[1]) * 180) / Math.PI

export const categoryOf = (item: Pick<PlanItem, 'slot' | 'product_id'>): string =>
  productById[item.product_id]?.category ?? item.slot

function corners(r: Rect): Vec2[] {
  const c = Math.cos(rad(r.rot))
  const s = Math.sin(rad(r.rot))
  // local x (width) -> world (c, -s); local z (depth/front) -> world (s, c)
  const ax: Vec2 = [c * r.hw, -s * r.hw]
  const az: Vec2 = [s * r.hd, c * r.hd]
  return [
    [r.cx + ax[0] + az[0], r.cz + ax[1] + az[1]],
    [r.cx - ax[0] + az[0], r.cz - ax[1] + az[1]],
    [r.cx - ax[0] - az[0], r.cz - ax[1] - az[1]],
    [r.cx + ax[0] - az[0], r.cz + ax[1] - az[1]],
  ]
}
function aabb(r: Rect): Box {
  const cs = corners(r)
  const xs = cs.map((p) => p[0])
  const zs = cs.map((p) => p[1])
  return { x0: Math.min(...xs), z0: Math.min(...zs), x1: Math.max(...xs), z1: Math.max(...zs) }
}
const boxesOverlap = (a: Box, b: Box, gap = 0) =>
  a.x0 < b.x1 + gap && a.x1 > b.x0 - gap && a.z0 < b.z1 + gap && a.z1 > b.z0 - gap

function doorZone(d: RoomDoor, inset: number): Box {
  const c = add(d.center, d.into_room, d.width_in / 2 + inset)
  const h = d.width_in / 2
  return { x0: c[0] - h, z0: c[1] - h, x1: c[0] + h, z1: c[1] + h }
}

export function layoutDetail(room: RoomModel, items: PlanItem[]): LayoutDetail {
  const inset = room.source === 'roomplan' ? 2 : 0
  const outline = room.outline
  const frames = room.walls.map((w) => ({ w, ...wallFrame(w, outline) }))
  const zones = room.doors.map((d) => doorZone(d, inset))
  const placed: { slot: string; box: Box; rug: boolean }[] = []
  const out: Record<string, Placement> = {}

  /** every corner and edge midpoint inside the walls, at least `margin` clear of them */
  const inRoom = (r: Rect, margin: number): boolean => {
    const cs = corners(r)
    const pts: Vec2[] = [...cs, ...cs.map((p, i) => [(p[0] + cs[(i + 1) % 4][0]) / 2, (p[1] + cs[(i + 1) % 4][1]) / 2] as Vec2)]
    pts.push([r.cx, r.cz])
    for (const p of pts) {
      if (!pointInPoly(p, outline)) return false
      for (const f of frames) if (distToSegment(p, f.w.a, f.w.b) < inset + margin - 0.6) return false
    }
    const b = aabb(r)
    // a wall corner poking into the footprint (the notch of an L-shaped room)
    return !outline.some((v) => v[0] > b.x0 + 0.5 && v[0] < b.x1 - 0.5 && v[1] > b.z0 + 0.5 && v[1] < b.z1 - 0.5)
  }
  const clear = (r: Rect, opts: { doors?: boolean; others?: boolean; gap?: number; ignore?: string[] } = {}) => {
    const b = aabb(r)
    if (opts.doors !== false && zones.some((z) => boxesOverlap(b, z))) return false
    if (opts.others !== false)
      for (const p of placed) {
        if (p.rug || opts.ignore?.includes(p.slot)) continue
        if (boxesOverlap(b, p.box, opts.gap ?? 0)) return false
      }
    return true
  }
  const put = (item: PlanItem, r: Rect) => {
    out[item.slot] = {
      slot: item.slot,
      x_in: Math.round(r.cx * 10) / 10,
      z_in: Math.round(r.cz * 10) / 10,
      rotation: Math.round(r.rot * 10) / 10,
    }
    placed.push({ slot: item.slot, box: aabb(r), rug: categoryOf(item) === 'rug' })
  }
  const dims = (item: PlanItem) => ({ w: item.dims_in.w, d: item.dims_in.d })
  const byCat = (...cats: string[]) => items.find((i) => cats.includes(categoryOf(i)))

  // ---------- anchor: the sofa (or bed) backs onto a wall ----------
  const anchor = byCat('sofa') ?? byCat('bed') ?? byCat('armchair')
  const lamp = byCat('floor_lamp')
  const tv = room.existing.find((e) => e.category === 'television')

  let order = [...frames].sort((a, b) => b.w.length_in - a.w.length_in)
  const typedWall = frames.find((f) => f.w.id === 'wall')
  if (typedWall) order = [typedWall, ...order.filter((f) => f !== typedWall)]
  let tvPoint: Vec2 | null = null
  if (tv) {
    tvPoint = [tv.x_in, tv.z_in]
    const tvWall = [...frames].sort(
      (a, b) => distToSegment(tvPoint!, a.w.a, a.w.b) - distToSegment(tvPoint!, b.w.a, b.w.b),
    )[0]
    const opposite = frames
      .filter((f) => dot(f.n, tvWall.n) < -0.9)
      .sort((a, b) => b.w.length_in - a.w.length_in)
    order = [...opposite, ...order.filter((f) => !opposite.includes(f))]
  }

  let anchorFrame = order[0] ?? null
  let anchorRect: Rect | null = null
  let lampRect: Rect | null = null

  // The lamp stands against the sofa's wall, past the sofa's end. If the room corner is close, tuck it into
  // the corner (between the sofa's end and the side wall) so it never reads as standing in the walkway.
  const lampBeside = (f: (typeof frames)[number], s: number, a: { w: number; d: number }, side: number): Rect | null => {
    if (!lamp) return null
    const l = dims(lamp)
    const L = Math.hypot(f.w.b[0] - f.w.a[0], f.w.b[1] - f.w.a[1])
    const end = s + side * (a.w / 2) // the sofa's end on this side, along the wall
    const cornerAt = side > 0 ? L - inset - 2 - l.w / 2 : inset + 2 + l.w / 2
    const besideAt = end + side * (3 + l.w / 2)
    const gap = side > 0 ? L - inset - end : end - inset
    const spots = gap <= 44 ? [cornerAt, besideAt] : [besideAt]
    for (const along of spots) {
      if (side > 0 ? along < besideAt - 0.01 : along > besideAt + 0.01) continue // would overlap the sofa
      const c = add(add(f.w.a, f.t, along), f.n, inset + l.d / 2 + 2)
      const r: Rect = { cx: c[0], cz: c[1], hw: l.w / 2, hd: l.d / 2, rot: rotOf(f.n) }
      if (inRoom(r, 0) && clear(r)) return r
    }
    return null
  }

  if (anchor) {
    const a = dims(anchor)
    const tryWall = (f: (typeof frames)[number], needLamp: boolean): boolean => {
      const L = Math.hypot(f.w.b[0] - f.w.a[0], f.w.b[1] - f.w.a[1])
      const s0 = tvPoint ? dot([tvPoint[0] - f.w.a[0], tvPoint[1] - f.w.a[1]], f.t) : L / 2
      for (let k = 0; k <= L; k += 1) {
        for (const sgn of k === 0 ? [1] : [1, -1]) {
          const s = Math.min(L, Math.max(0, s0)) + sgn * k
          if (s - a.w / 2 < inset || s + a.w / 2 > L - inset) continue
          const c = add(add(f.w.a, f.t, s), f.n, inset + a.d / 2 + 1)
          const r: Rect = { cx: c[0], cz: c[1], hw: a.w / 2, hd: a.d / 2, rot: rotOf(f.n) }
          if (!inRoom(r, 0) || !clear(r)) continue
          let lr: Rect | null = null
          if (needLamp) {
            lr = lampBeside(f, s, a, 1) ?? lampBeside(f, s, a, -1)
            if (!lr) continue
          }
          anchorFrame = f
          anchorRect = r
          lampRect = lr
          return true
        }
      }
      return false
    }
    const first = order[0]
    // Prefer the first-choice wall. Shift along it to make room for the lamp if that costs little.
    if (!(first && lamp && tryWall(first, true)) && !order.some((f) => tryWall(f, false))) {
      // nothing fits cleanly anywhere: stand it on the first wall anyway so the overhang is visible
      const f = order[0]
      if (f) {
        const c = add(f.mid, f.n, inset + a.d / 2 + 1)
        anchorFrame = f
        anchorRect = { cx: c[0], cz: c[1], hw: a.w / 2, hd: a.d / 2, rot: rotOf(f.n) }
      }
    }
    if (anchorRect) put(anchor, anchorRect)
  }

  const f0 = anchorFrame
  const n: Vec2 = f0 ? f0.n : [0, 1]
  const t: Vec2 = f0 ? f0.t : [1, 0]
  const xs = outline.map((p) => p[0])
  const zs = outline.map((p) => p[1])
  const mid: Vec2 = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...zs) + Math.max(...zs)) / 2]
  const A: Rect = anchorRect ?? { cx: mid[0] - n[0] * 30, cz: mid[1] - n[1] * 30, hw: 30, hd: 15, rot: rotOf(n) }
  const aCenter: Vec2 = [A.cx, A.cz]
  const front = A.hd // distance from the anchor's centre to its front edge

  // ---------- rug: in front of the sofa, front legs on it ----------
  const rug = byCat('rug')
  let rugRect: Rect | null = null
  if (rug) {
    const r = dims(rug)
    const tries: { alongT: number; alongN: number; rot: number }[] = []
    const long = Math.max(r.w, r.d)
    const short = Math.min(r.w, r.d)
    // long side parallel to the sofa first
    tries.push({ alongT: long, alongN: short, rot: rotOf(n) + (r.d > r.w ? 90 : 0) })
    tries.push({ alongT: short, alongN: long, rot: rotOf(n) + (r.d > r.w ? 0 : 90) })
    let best: { rect: Rect; cost: number } | null = null
    tries.forEach((o, oi) => {
      const pref = add(aCenter, n, front - 8 + o.alongN / 2)
      for (let dn = 0; dn <= 48; dn += 2) {
        for (let dt = 0; dt <= 72; dt += 2) {
          for (const sg of dt === 0 ? [1] : [1, -1]) {
            const cost = dt + dn * 1.5 + oi * 30
            if (best && cost >= best.cost) continue
            const c = add(add(pref, t, sg * dt), n, dn)
            const rect: Rect = { cx: c[0], cz: c[1], hw: r.w / 2, hd: r.d / 2, rot: o.rot }
            if (inRoom(rect, 6)) best = { rect, cost }
          }
        }
      }
    })
    const o = tries[1]
    const fallback = add(aCenter, n, front - 8 + o.alongN / 2)
    rugRect = (best as { rect: Rect } | null)?.rect ?? { cx: fallback[0], cz: fallback[1], hw: r.w / 2, hd: r.d / 2, rot: o.rot }
    put(rug, rugRect)
  }

  // ---------- coffee table: on the rug, in front of the sofa ----------
  const table = byCat('coffee_table')
  let tableRect: Rect | null = null
  if (table) {
    const d = dims(table)
    const longAlongT = d.d > d.w
    const alongN = longAlongT ? d.w : d.d
    for (const leg of [16, 12, 9, 6]) {
      const c = add(aCenter, n, front + leg + alongN / 2)
      const r: Rect = { cx: c[0], cz: c[1], hw: d.w / 2, hd: d.d / 2, rot: rotOf(n) + (longAlongT ? 90 : 0) }
      tableRect = r
      if (inRoom(r, 2) && clear(r, { doors: false })) break
    }
    if (tableRect) put(table, tableRect)
  }
  const focus: Vec2 = tableRect ? [tableRect.cx, tableRect.cz] : add(aCenter, n, front + 30)
  const focusHalfT = tableRect ? Math.max(...corners(tableRect).map((p) => Math.abs(dot([p[0] - focus[0], p[1] - focus[1]], t)))) : 14
  const focusHalfN = tableRect ? Math.max(...corners(tableRect).map((p) => Math.abs(dot([p[0] - focus[0], p[1] - focus[1]], n)))) : 14

  // ---------- armchair: beside the table, turned toward it; or across from the sofa in a narrow room ----------
  const chair = anchor && categoryOf(anchor) === 'armchair' ? undefined : byCat('armchair')
  let chairRect: Rect | null = null
  if (chair) {
    const d = dims(chair)
    const candidates: Rect[] = []
    const room4side = (sg: number) => {
      let k = 0
      while (k < 200 && pointInPoly(add(focus, t, sg * (focusHalfT + k)), outline)) k += 4
      return k
    }
    const sides = room4side(1) >= room4side(-1) ? [1, -1] : [-1, 1]
    for (const sg of sides)
      for (const gap of [22, 16, 10, 6]) {
        const c = add(add(focus, t, sg * (focusHalfT + gap + d.d / 2)), n, 8)
        const f: Vec2 = [focus[0] - c[0], focus[1] - c[1]]
        candidates.push({ cx: c[0], cz: c[1], hw: d.w / 2, hd: d.d / 2, rot: rotOf(f) })
      }
    for (const sg of sides)
      for (const gap of [18, 12, 8]) {
        const c = add(add(focus, n, focusHalfN + gap + d.d / 2), t, sg * 14)
        candidates.push({ cx: c[0], cz: c[1], hw: d.w / 2, hd: d.d / 2, rot: rotOf([-n[0], -n[1]]) + sg * 25 })
      }
    chairRect = candidates.find((r) => inRoom(r, 1) && clear(r, { gap: 3 })) ?? candidates[0]
    put(chair, chairRect)
  }

  // ---------- floor lamp: beside the sofa, else by the armchair, else a free corner ----------
  if (lamp) {
    const l = dims(lamp)
    let r: Rect | null = lampRect
    if (!r && f0 && anchorRect) {
      const s = dot([A.cx - f0.w.a[0], A.cz - f0.w.a[1]], f0.t)
      r = lampBeside(f0, s, { w: A.hw * 2, d: A.hd * 2 }, 1) ?? lampBeside(f0, s, { w: A.hw * 2, d: A.hd * 2 }, -1)
    }
    if (!r && chairRect) {
      const fdir: Vec2 = [Math.sin(rad(chairRect.rot)), Math.cos(rad(chairRect.rot))]
      const side: Vec2 = [fdir[1], -fdir[0]]
      for (const sg of [1, -1])
        for (const back of [10, 0, 18]) {
          const c = add(add([chairRect.cx, chairRect.cz], side, sg * (chairRect.hw + l.w / 2 + 4)), fdir, -back)
          const cand: Rect = { cx: c[0], cz: c[1], hw: l.w / 2, hd: l.d / 2, rot: 0 }
          if (!r && inRoom(cand, 2) && clear(cand)) r = cand
        }
    }
    if (!r) {
      const cornersIn = outline
        .map((v) => {
          const dir: Vec2 = [Math.sign(mid[0] - v[0]) || 1, Math.sign(mid[1] - v[1]) || 1]
          return { cx: v[0] + dir[0] * (inset + l.w / 2 + 3), cz: v[1] + dir[1] * (inset + l.d / 2 + 3), hw: l.w / 2, hd: l.d / 2, rot: 0 } as Rect
        })
        .sort((a, b) => Math.hypot(a.cx - A.cx, a.cz - A.cz) - Math.hypot(b.cx - A.cx, b.cz - A.cz))
      r = cornersIn.find((c) => inRoom(c, 0) && clear(c)) ?? cornersIn[0] ?? null
    }
    if (r) put(lamp, r)
  }

  // ---------- everything else: back against a wall, TV bench on the wall the sofa faces ----------
  const rest = items.filter((i) => !out[i.slot])
  for (const item of rest) {
    const d = dims(item)
    const cat = categoryOf(item)
    let walls = [...frames].sort((a, b) => b.w.length_in - a.w.length_in)
    let pref: Vec2 | null = null
    if (cat === 'tv_bench') {
      const facing = frames.filter((f) => dot(f.n, n) < -0.9)
      walls = [...facing, ...walls.filter((f) => !facing.includes(f))]
      pref = tvPoint ?? aCenter
    } else if (cat === 'side_table' || cat === 'nightstand') {
      walls = f0 ? [f0, ...walls.filter((f) => f !== f0)] : walls
      pref = aCenter
    }
    let done = false
    for (const f of walls) {
      const L = Math.hypot(f.w.b[0] - f.w.a[0], f.w.b[1] - f.w.a[1])
      const s0 = pref ? dot([pref[0] - f.w.a[0], pref[1] - f.w.a[1]], f.t) : L / 2
      for (let k = 0; k <= L && !done; k += 2) {
        for (const sg of k === 0 ? [1] : [1, -1]) {
          const s = Math.min(L, Math.max(0, s0)) + sg * k
          if (s - d.w / 2 < inset || s + d.w / 2 > L - inset) continue
          const c = add(add(f.w.a, f.t, s), f.n, inset + d.d / 2 + 1)
          const r: Rect = { cx: c[0], cz: c[1], hw: d.w / 2, hd: d.d / 2, rot: rotOf(f.n) }
          if (inRoom(r, 0) && clear(r, { gap: 2 })) {
            put(item, r)
            done = true
            break
          }
        }
      }
      if (done) break
    }
    if (!done) put(item, { cx: mid[0], cz: mid[1], hw: d.w / 2, hd: d.d / 2, rot: 0 })
  }

  const depthWall =
    (f0 && [...frames].filter((f) => Math.abs(dot(f.n, f0.n)) < 0.2).sort((a, b) => b.w.length_in - a.w.length_in)[0]?.w) || null

  return { placements: out, anchorWall: f0?.w ?? null, depthWall, facing: n }
}

export function layoutRoom(room: RoomModel, items: PlanItem[]): Record<string, Placement> {
  return layoutDetail(room, items).placements
}
