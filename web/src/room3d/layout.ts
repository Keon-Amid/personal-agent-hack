// Where each item goes when the plan gives no placement.
// This is a simple rule of thumb per category, not the agent's decision and not a fit check:
// it only decides where to DRAW an item. Whether it fits is decided by fit/ on the Python side.

import type { Placement, Product, Room } from './types'

type Slotted = { slot: string; product: Product }
type Rot = Placement['rotation_deg']

const GAP = 4 // inches between neighbours on a wall

export function footprint(p: Product, rot: number): { fx: number; fz: number } {
  const { w, d } = p.dims_in
  return rot % 180 === 0 ? { fx: w, fz: d } : { fx: d, fz: w }
}

export function autoLayout(room: Room, items: Slotted[]): Record<string, Placement> {
  const W = room.wall.value_in
  const D = room.depth.value_in
  const out: Record<string, Placement> = {}
  const get = (slot: string) => items.find((i) => i.slot === slot)?.product
  const place = (slot: string, x: number, z: number, rot: Rot = 0) => {
    out[slot] = { x_in: x, z_in: z, rotation_deg: rot }
  }

  // Back wall: the main piece (sofa, else bed), with a side table and a lamp beside it if they fit.
  const main = get('sofa') ? 'sofa' : get('bed') ? 'bed' : null
  const mainP = main ? get(main)! : null
  const sideTable = get('side_table')
  const lamp = get('floor_lamp')
  let mainDepth = 0
  const leftover: string[] = []
  if (mainP && main) {
    mainDepth = mainP.dims_in.d
    const row: { slot: string; p: Product }[] = [{ slot: main, p: mainP }]
    let total = mainP.dims_in.w
    if (lamp && total + GAP + lamp.dims_in.w <= W) {
      row.push({ slot: 'floor_lamp', p: lamp })
      total += GAP + lamp.dims_in.w
    } else if (lamp) leftover.push('floor_lamp')
    if (sideTable && total + GAP + sideTable.dims_in.w <= W) {
      row.unshift({ slot: 'side_table', p: sideTable })
      total += GAP + sideTable.dims_in.w
    } else if (sideTable) leftover.push('side_table')
    // Centre the row. A main piece wider than the wall stays centred, so it visibly pokes through both ends.
    let x = (W - total) / 2
    for (const r of row) {
      place(r.slot, x + r.p.dims_in.w / 2, r.p.dims_in.d / 2 + 1)
      x += r.p.dims_in.w + GAP
    }
  } else {
    if (lamp) leftover.push('floor_lamp')
    if (sideTable) leftover.push('side_table')
  }

  // Front wall: TV bench facing the sofa.
  const tv = get('tv_bench')
  if (tv) place('tv_bench', W / 2, D - tv.dims_in.d / 2 - 1, 180)

  // Side walls: everything else, packed from the back corner forward. Left wall faces right, right wall faces left.
  const doorOnRight = (room.door_wall ?? 'right') === 'right'
  const doorStart = room.door_offset_in ?? D
  let leftZ = mainDepth + 14
  let rightZ = mainDepth + 14
  let leftDepth = 0 // how far side-wall items reach into the room
  let rightDepth = 0
  const sideOrder = ['armchair', 'bookcase', 'dresser', 'desk', 'nightstand', 'dining_table', 'dining_chair', ...leftover]
  let useLeft = true
  for (const slot of sideOrder) {
    const p = get(slot)
    if (!p || out[slot]) continue
    const len = p.dims_in.w // length along the wall once turned
    const rightLimit = doorOnRight ? doorStart - 4 : D - 4
    const fitsRight = rightZ + len <= rightLimit
    const fitsLeft = leftZ + len <= D - 4
    const side = useLeft && fitsLeft ? 'left' : fitsRight ? 'right' : 'left'
    if (side === 'left') {
      place(slot, p.dims_in.d / 2 + 1, leftZ + len / 2, 90)
      leftZ += len + GAP
      leftDepth = Math.max(leftDepth, p.dims_in.d + 1)
    } else {
      place(slot, W - p.dims_in.d / 2 - 1, rightZ + len / 2, 270)
      rightZ += len + GAP
      rightDepth = Math.max(rightDepth, p.dims_in.d + 1)
    }
    useLeft = !useLeft
  }

  // Rug in front of the main piece, long side running down the room.
  const rug = get('rug')
  if (rug) {
    const rot: Rot = rug.dims_in.d >= rug.dims_in.w ? 0 : 90
    const { fz } = footprint(rug, rot)
    place('rug', W / 2, Math.min(mainDepth + 6 + fz / 2, D - fz / 2 - 4), rot)
  }

  // Coffee table in the free floor between the side-wall items, turned whichever way fits that gap.
  const coffee = get('coffee_table')
  if (coffee) {
    const x0 = leftDepth > 0 ? leftDepth + 5 : 4
    const x1 = W - (rightDepth > 0 ? rightDepth + 5 : 4)
    const long = Math.max(coffee.dims_in.w, coffee.dims_in.d)
    const longAlongX: Rot = coffee.dims_in.w >= coffee.dims_in.d ? 0 : 90
    const longAlongZ: Rot = coffee.dims_in.w >= coffee.dims_in.d ? 90 : 0
    const rot = long <= x1 - x0 ? longAlongX : longAlongZ
    const { fz } = footprint(coffee, rot)
    place('coffee_table', (x0 + x1) / 2, mainDepth + 16 + fz / 2, rot)
  }

  // Anything still unplaced (a category this file does not know): line it up along the left wall.
  for (const it of items) {
    if (out[it.slot]) continue
    const p = it.product
    place(it.slot, p.dims_in.d / 2 + 1, leftZ + p.dims_in.w / 2, 90)
    leftZ += p.dims_in.w + GAP
  }
  return out
}
