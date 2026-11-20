// Turns a room (a scanned GLB, or typed measurements) into (a) meshes the scene can draw and animate and
// (b) a RoomModel in inches, the same shape as fit.scan.load_scan() in Python.
import * as THREE from 'three'
import type { PlanRoom, RoomDoor, RoomExisting, RoomModel, RoomWall, Vec2 } from '../types'

export const IN = 0.0254
const M_TO_IN = 39.3701
const r1 = (v: number) => Math.round(v * 10) / 10

export const COLORS = {
  wall: '#d9d3c8',
  floor: '#bfb8ac',
  clay: '#e9e3d8',
  existing: '#8f8a82',
  tv: '#2c2c30',
  door: '#a9a195',
  ice: '#9fe3f0',
  nofit: '#ff6b5e',
  bone: '#eeeae3',
  casing: '#0c0d0f',
}

// Shared, long-lived materials. Only one room is on screen at a time.
export const MAT = {
  wall: new THREE.MeshStandardMaterial({ color: COLORS.wall, roughness: 0.96, metalness: 0 }),
  floor: new THREE.MeshStandardMaterial({ color: COLORS.floor, roughness: 1, metalness: 0 }),
  door: new THREE.MeshStandardMaterial({ color: COLORS.door, roughness: 0.9, metalness: 0 }),
  existing: new THREE.MeshStandardMaterial({ color: COLORS.existing, roughness: 0.95, metalness: 0, transparent: true }),
  existingEdge: new THREE.LineBasicMaterial({ color: COLORS.bone, transparent: true, opacity: 0, depthWrite: false }),
  tv: new THREE.MeshStandardMaterial({ color: COLORS.tv, roughness: 0.55, metalness: 0.1, transparent: true }),
  mesh: new THREE.MeshStandardMaterial({ color: COLORS.wall, roughness: 0.98, metalness: 0, side: THREE.FrontSide }),
}

export function pointInPoly(p: Vec2, poly: Vec2[]): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, zi] = poly[i]
    const [xj, zj] = poly[j]
    if (zi > p[1] !== zj > p[1] && p[0] < ((xj - xi) * (p[1] - zi)) / (zj - zi) + xi) inside = !inside
  }
  return inside
}

export function distToSegment(p: Vec2, a: Vec2, b: Vec2): number {
  const dx = b[0] - a[0]
  const dz = b[1] - a[1]
  const len2 = dx * dx + dz * dz
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / len2))
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dz))
}

/** Unit tangent (a -> b) and unit normal pointing into the room. */
export function wallFrame(w: RoomWall, outline: Vec2[]): { t: Vec2; n: Vec2; mid: Vec2 } {
  const len = Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) || 1
  const t: Vec2 = [(w.b[0] - w.a[0]) / len, (w.b[1] - w.a[1]) / len]
  const mid: Vec2 = [(w.a[0] + w.b[0]) / 2, (w.a[1] + w.b[1]) / 2]
  let n: Vec2 = [-t[1], t[0]]
  if (!pointInPoly([mid[0] + n[0] * 8, mid[1] + n[1] * 8], outline)) n = [-n[0], -n[1]]
  return { t, n, mid }
}

/** One wall (or a wall plus what hangs on it) that can be cut down so you can see into the room. */
export interface WallPart {
  id: string
  objects: THREE.Object3D[]
  /** centre and outward normal on the floor plane, metres */
  cx: number
  cz: number
  nx: number
  nz: number
  height: number
  /** current and intro state, driven by the scene */
  s: number
  order: number
}

export interface ExistingPart {
  id: string
  mesh: THREE.Mesh
  edges: THREE.LineSegments
  mounted: boolean
  wall: WallPart | null
}

export interface Shell {
  group: THREE.Group
  walls: WallPart[]
  joints: { object: THREE.Object3D; walls: WallPart[] }[]
  existing: ExistingPart[]
  room: RoomModel
  /** metres */
  center: THREE.Vector3
  radius: number
  height: number
  /** half the wall thickness when the outline runs along wall centre-lines (scans), else 0 */
  insetIn: number
}

function chain(segs: [Vec2, Vec2][], tol: number): Vec2[] | null {
  if (segs.length < 3) return null
  const left = segs.map((s) => [s[0], s[1]] as [Vec2, Vec2])
  const first = left.shift()!
  const pts: Vec2[] = [first[0], first[1]]
  while (left.length) {
    const end = pts[pts.length - 1]
    let hit = -1
    let flip = false
    let best = tol
    left.forEach((s, i) => {
      const d0 = Math.hypot(s[0][0] - end[0], s[0][1] - end[1])
      const d1 = Math.hypot(s[1][0] - end[0], s[1][1] - end[1])
      if (d0 <= best) {
        best = d0
        hit = i
        flip = false
      }
      if (d1 <= best) {
        best = d1
        hit = i
        flip = true
      }
    })
    if (hit < 0) return null
    const [s] = left.splice(hit, 1)
    const from = flip ? s[1] : s[0]
    const to = flip ? s[0] : s[1]
    // snap the shared corner: walls meet at the crossing of their centre-lines
    const prev = pts[pts.length - 2]
    const corner: Vec2 =
      Math.abs(prev[0] - end[0]) < Math.abs(prev[1] - end[1]) ? [end[0], from[1]] : [from[0], end[1]]
    pts[pts.length - 1] = corner
    pts.push(to)
  }
  // close: drop the duplicate last point if it meets the first
  const a = pts[0]
  const z = pts[pts.length - 1]
  if (Math.hypot(a[0] - z[0], a[1] - z[1]) > tol) return null
  pts.pop()
  return pts
}

const CATEGORY: [string, string][] = [
  ['chair_dining', 'dining_chair'],
  ['chair_swivel', 'desk_chair'],
  ['chair', 'armchair'],
  ['sofa', 'sofa'],
  ['table_dining', 'dining_table'],
  ['table_coffee', 'coffee_table'],
  ['table', 'table'],
  ['bed', 'bed'],
  ['storage', 'storage'],
  ['television', 'television'],
]
const categoryOf = (label: string) => CATEGORY.find(([p]) => label.startsWith(p))?.[1] ?? label.split('_')[0]

function finishShell(
  group: THREE.Group,
  room: RoomModel,
  walls: WallPart[],
  joints: Shell['joints'],
  existing: ExistingPart[],
  insetIn: number,
): Shell {
  const xs = room.outline.map((p) => p[0])
  const zs = room.outline.map((p) => p[1])
  const cx = ((Math.min(...xs) + Math.max(...xs)) / 2) * IN
  const cz = ((Math.min(...zs) + Math.max(...zs)) / 2) * IN
  const w = (Math.max(...xs) - Math.min(...xs)) * IN
  const d = (Math.max(...zs) - Math.min(...zs)) * IN
  const height = room.height_in * IN
  return {
    group,
    room,
    walls,
    joints,
    existing,
    center: new THREE.Vector3(cx, 0, cz),
    radius: Math.hypot(w, d) / 2,
    height,
    insetIn,
  }
}

/** A Polycam Floorplan (Apple RoomPlan) export: every wall, door and piece of furniture is a named mesh. */
export function buildScanShell(scene: THREE.Object3D): Shell | null {
  const root = scene.clone(true)
  root.updateMatrixWorld(true)
  const group = new THREE.Group()
  group.add(root)

  const box = new THREE.Box3()
  const meshes: THREE.Mesh[] = []
  root.traverse((o) => {
    if ((o as THREE.Mesh).isMesh) meshes.push(o as THREE.Mesh)
  })
  const named = (re: RegExp) => meshes.filter((m) => re.test(m.name))
  const wallMeshes = named(/^Wall_\d+$/)
  if (wallMeshes.length < 3) return null

  let floorY = 0
  for (const m of named(/^Floor_/)) {
    floorY = box.setFromObject(m).max.y
    m.material = MAT.floor
    m.receiveShadow = true
  }
  for (const m of named(/^Ceiling_/)) m.visible = false

  const walls: WallPart[] = []
  const rw: RoomWall[] = []
  const segs: [Vec2, Vec2][] = []
  let top = 2.4
  let half = 0.05
  wallMeshes.forEach((m, i) => {
    const b = box.setFromObject(m)
    const dx = b.max.x - b.min.x
    const dz = b.max.z - b.min.z
    half = Math.min(dx, dz) / 2
    let a: Vec2
    let e: Vec2
    if (dx >= dz) {
      const zc = (b.min.z + b.max.z) / 2
      a = [b.min.x + dz / 2, zc]
      e = [b.max.x - dz / 2, zc]
    } else {
      const xc = (b.min.x + b.max.x) / 2
      a = [xc, b.min.z + dx / 2]
      e = [xc, b.max.z - dx / 2]
    }
    top = Math.max(top, b.max.y - floorY)
    segs.push([a, e])
    rw.push({
      id: m.name,
      a: [r1(a[0] * M_TO_IN), r1(a[1] * M_TO_IN)],
      b: [r1(e[0] * M_TO_IN), r1(e[1] * M_TO_IN)],
      length_in: r1((Math.max(dx, dz) - Math.min(dx, dz)) * M_TO_IN),
    })
    m.material = MAT.wall
    m.castShadow = true
    m.receiveShadow = true
    walls.push({
      id: m.name,
      objects: [m],
      cx: (a[0] + e[0]) / 2,
      cz: (a[1] + e[1]) / 2,
      nx: 0,
      nz: 0,
      height: b.max.y - floorY,
      s: 0,
      order: i,
    })
  })

  const chained = chain(segs, 0.3)
  const xsAll = segs.flatMap((s) => [s[0][0], s[1][0]])
  const zsAll = segs.flatMap((s) => [s[0][1], s[1][1]])
  const outlineM: Vec2[] = chained ?? [
    [Math.min(...xsAll), Math.min(...zsAll)],
    [Math.max(...xsAll), Math.min(...zsAll)],
    [Math.max(...xsAll), Math.max(...zsAll)],
    [Math.min(...xsAll), Math.max(...zsAll)],
  ]
  const outline: Vec2[] = outlineM.map(([x, z]) => [r1(x * M_TO_IN), r1(z * M_TO_IN)])

  // outward normals
  walls.forEach((w, i) => {
    const { n } = wallFrame(rw[i], outline)
    w.nx = -n[0]
    w.nz = -n[1]
  })
  const nearestWall = (x: number, z: number): number => {
    let best = 0
    let bd = Infinity
    rw.forEach((w, i) => {
      const d = distToSegment([x * M_TO_IN, z * M_TO_IN], w.a, w.b)
      if (d < bd) {
        bd = d
        best = i
      }
    })
    return best
  }

  // joints follow the lower of the walls they connect
  const joints: Shell['joints'] = []
  for (const m of named(/^Joint_\d+$/)) {
    const b = box.setFromObject(m)
    const jx = (b.min.x + b.max.x) / 2
    const jz = (b.min.z + b.max.z) / 2
    m.material = MAT.wall
    m.castShadow = true
    m.receiveShadow = true
    const near = walls.filter((_, i) =>
      [segs[i][0], segs[i][1]].some((p) => Math.hypot(p[0] - jx, p[1] - jz) < half * 2 + 0.12),
    )
    joints.push({ object: m, walls: near })
  }

  // doors / openings / windows: RoomPlan gives a flat plane inside the wall, so draw our own slab
  const doors: RoomDoor[] = []
  for (const m of named(/^(Door|Opening|Window)_\d+$/)) {
    const b = box.setFromObject(m)
    const dx = b.max.x - b.min.x
    const dz = b.max.z - b.min.z
    const axis: 'x' | 'z' = dx < dz ? 'z' : 'x'
    const cx = (b.min.x + b.max.x) / 2
    const cz = (b.min.z + b.max.z) / 2
    const width = Math.max(dx, dz)
    const h = b.max.y - b.min.y
    const wi = nearestWall(cx, cz)
    m.visible = false
    const t = half * 2 + 0.024
    const slab = new THREE.Mesh(
      new THREE.BoxGeometry(axis === 'z' ? t : width, h, axis === 'z' ? width : t),
      MAT.door,
    )
    slab.geometry.translate(0, h / 2, 0)
    slab.position.set(cx, b.min.y, cz)
    slab.name = `${m.name}_slab`
    slab.receiveShadow = true
    group.add(slab)
    walls[wi].objects.push(slab)
    const nIn: Vec2 = axis === 'z' ? [1, 0] : [0, 1]
    const cIn: Vec2 = [cx * M_TO_IN, cz * M_TO_IN]
    const into: Vec2 = pointInPoly([cIn[0] + nIn[0] * 12, cIn[1] + nIn[1] * 12], outline) ? nIn : [-nIn[0], -nIn[1]]
    if (/^Door_/.test(m.name)) {
      doors.push({
        id: m.name,
        wall: rw[wi].id,
        center: [r1(cIn[0]), r1(cIn[1])],
        width_in: r1(width * M_TO_IN),
        height_in: r1(h * M_TO_IN),
        axis,
        into_room: into,
      })
    }
  }

  // furniture the scan found already in the room
  const existing: ExistingPart[] = []
  const items: RoomExisting[] = []
  for (const m of meshes) {
    if (!/_\d+$/.test(m.name) || /^(Wall|Joint|Floor|Ceiling|Door|Opening|Window)_/.test(m.name)) continue
    const b = box.setFromObject(m)
    const bottom = (b.min.y - floorY) * M_TO_IN
    const label = m.name.replace(/_\d+$/, '')
    const category = categoryOf(m.name)
    const mounted = bottom >= 24
    m.material = category === 'television' ? MAT.tv : MAT.existing
    m.castShadow = true
    m.receiveShadow = true
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 25), MAT.existingEdge)
    edges.visible = false
    m.add(edges)
    const cx = (b.min.x + b.max.x) / 2
    const cz = (b.min.z + b.max.z) / 2
    existing.push({ id: m.name, mesh: m, edges, mounted, wall: mounted ? walls[nearestWall(cx, cz)] : null })
    items.push({
      id: m.name,
      label,
      category,
      x_in: r1(cx * M_TO_IN),
      z_in: r1(cz * M_TO_IN),
      w_in: r1((b.max.x - b.min.x) * M_TO_IN),
      d_in: r1((b.max.z - b.min.z) * M_TO_IN),
      h_in: r1((b.max.y - b.min.y) * M_TO_IN),
      bottom_in: r1(bottom),
      on_floor: bottom < 6,
    })
  }

  const room: RoomModel = {
    source: 'roomplan',
    outline,
    walls: rw,
    doors,
    existing: items,
    height_in: r1(top * M_TO_IN),
  }
  return finishShell(group, room, walls, joints, existing, r1(half * M_TO_IN))
}

/** A raw LiDAR mesh with no named parts: keep it as one surface, cut the top off, measure its bounding box. */
export function buildMeshShell(scene: THREE.Object3D): Shell {
  const root = scene.clone(true)
  root.updateMatrixWorld(true)
  const group = new THREE.Group()
  const bounds = new THREE.Box3().setFromObject(root)
  const lift = -bounds.min.y
  const clip = new THREE.Plane(new THREE.Vector3(0, -1, 0), Math.min(2.3, bounds.max.y - bounds.min.y - 0.25))
  const mat = MAT.mesh.clone()
  mat.clippingPlanes = [clip]
  root.traverse((o) => {
    const m = o as THREE.Mesh
    if (!m.isMesh) return
    m.geometry = m.geometry.clone()
    m.geometry.computeVertexNormals()
    m.material = mat
    m.receiveShadow = true
  })
  root.position.y = lift
  group.add(root)
  const lo: Vec2 = [r1(bounds.min.x * M_TO_IN), r1(bounds.min.z * M_TO_IN)]
  const hi: Vec2 = [r1(bounds.max.x * M_TO_IN), r1(bounds.max.z * M_TO_IN)]
  const outline: Vec2[] = [lo, [hi[0], lo[1]], hi, [lo[0], hi[1]]]
  const walls: RoomWall[] = outline.map((a, i) => {
    const b = outline[(i + 1) % 4]
    return { id: `side_${i}`, a, b, length_in: r1(Math.hypot(b[0] - a[0], b[1] - a[1])) }
  })
  const room: RoomModel = {
    source: 'mesh',
    outline,
    walls,
    doors: [],
    existing: [],
    height_in: r1((bounds.max.y - bounds.min.y) * M_TO_IN),
  }
  return finishShell(group, room, [], [], [], 0)
}

/** No scan: draw the room from the plan's typed measurements. The sofa wall ("wall") is the back wall. */
export function buildTypedShell(pr: PlanRoom): Shell {
  const W = pr.wall.value_in
  const D = pr.depth.value_in
  const dw = Math.min(pr.door_width.value_in, D - 16)
  const dh = pr.door_height.value_in
  const H = 96
  const T = 4
  const group = new THREE.Group()
  const hw = W / 2
  const hd = D / 2
  const outline: Vec2[] = [
    [-hw, -hd],
    [hw, -hd],
    [hw, hd],
    [-hw, hd],
  ]
  const rw: RoomWall[] = [
    { id: 'wall', a: [-hw, -hd], b: [hw, -hd], length_in: W },
    { id: 'east', a: [hw, -hd], b: [hw, hd], length_in: D },
    { id: 'front', a: [hw, hd], b: [-hw, hd], length_in: W },
    { id: 'west', a: [-hw, hd], b: [-hw, -hd], length_in: D },
  ]

  const slab = (wIn: number, hIn: number, dIn: number, x: number, y0: number, z: number) => {
    const g = new THREE.BoxGeometry(wIn * IN, hIn * IN, dIn * IN)
    g.translate(0, (hIn * IN) / 2, 0)
    const m = new THREE.Mesh(g, MAT.wall)
    m.position.set(x * IN, y0 * IN, z * IN)
    m.castShadow = true
    m.receiveShadow = true
    return m
  }
  const part = (id: string, objects: THREE.Object3D[], c: Vec2, n: Vec2, order: number): WallPart => {
    objects.forEach((o) => group.add(o))
    return { id, objects, cx: c[0] * IN, cz: c[1] * IN, nx: n[0], nz: n[1], height: H * IN, s: 0, order }
  }

  const doorZ = hd - 8 - dw / 2
  const z0 = doorZ - dw / 2 // door edge nearer the back
  const z1 = doorZ + dw / 2
  const westBits: THREE.Object3D[] = [
    slab(T, H, z0 + hd + T, -hw - T / 2, 0, (z0 - hd - T) / 2),
    slab(T, H, hd + T - z1, -hw - T / 2, 0, (z1 + hd + T) / 2),
  ]
  if (dh < H) westBits.push(slab(T, H - dh, dw, -hw - T / 2, dh, doorZ))

  const walls: WallPart[] = [
    part('wall', [slab(W + 2 * T, H, T, 0, 0, -hd - T / 2)], [0, -hd], [0, -1], 0),
    part('east', [slab(T, H, D, hw + T / 2, 0, 0)], [hw, 0], [1, 0], 1),
    part('front', [slab(W + 2 * T, H, T, 0, 0, hd + T / 2)], [0, hd], [0, 1], 2),
    part('west', westBits, [-hw, 0], [-1, 0], 3),
  ]

  const floor = new THREE.Mesh(new THREE.BoxGeometry((W + 2 * T) * IN, 0.1, (D + 2 * T) * IN), MAT.floor)
  floor.position.y = -0.05
  floor.receiveShadow = true
  group.add(floor)

  const room: RoomModel = {
    source: 'typed',
    outline,
    walls: rw,
    doors: [
      { id: 'door', wall: 'west', center: [-hw, r1(doorZ)], width_in: dw, height_in: dh, axis: 'z', into_room: [1, 0] },
    ],
    existing: [],
    height_in: H,
  }
  return finishShell(group, room, walls, [], [], 0)
}
