// The 3D room: an architect's clay model on a dark drafting desk.
// Reads the app store, never writes run state. Calls back only setRoom / select / hover / clearGhost.
import { Component, Suspense, useEffect, useMemo, useRef, type ReactNode } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { CameraControls, Environment, Grid, Lightformer, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { Plan, Placement, RoomDoor, RoomWall, Vec2 } from '../types'
import { useApp } from '../store'
import { inches } from '../lib/format'
import { buildMeshShell, buildScanShell, buildTypedShell, COLORS, IN, MAT, STILL, wallFrame, type Shell } from './roomModel'
import { layoutDetail, type LayoutDetail } from './layout'
import { GhostPiece, Label, Mark, overlayRef, Piece } from './pieces'
import { useModelManifest } from '../room3d/Model'

const MODELS = '/models/'

// dev only: lets a screenshot script drive the live store (window.__app.getState().select('sofa'))
if (import.meta.env.DEV) (window as unknown as { __app?: typeof useApp }).__app = useApp

const CURB = 0.13 // height a wall is cut down to when it stands between you and the room (m)
const CUT = 2.25 // every wall is sectioned here, like an architect's model: above the TV, below the ceiling
const FOV = 34
const rad = (d: number) => (d * Math.PI) / 180
const CAMERA = { fov: FOV, near: 0.1, far: 120, position: [7, 6, 8] as [number, number, number] }
const GL = {
  antialias: true,
  alpha: true,
  powerPreference: 'high-performance' as const,
  toneMapping: THREE.NeutralToneMapping,
  toneMappingExposure: 1.02,
}
const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

// ---------------------------------------------------------------------------------------------------------
// Shell: cut-away walls, the furniture the scan found, intro
// ---------------------------------------------------------------------------------------------------------
function ShellAnimator({ shell }: { shell: Shell }) {
  const t = useRef(0)
  const low = useRef<boolean[]>([])
  const fade = useRef({ fill: 0, edge: 0, tv: 0, casting: true })
  useEffect(() => {
    t.current = STILL ? 10 : 0
    low.current = []
    shell.walls.forEach((w) => (w.s = 0))
    fade.current = { fill: 0, edge: 0, tv: 0, casting: true }
  }, [shell])

  useFrame(({ camera }, dt) => {
    const s = useApp.getState()
    const d = Math.min(dt, 0.1)
    t.current += d
    const k = STILL ? 1 : 1 - Math.exp(-d * 7)
    const dx = camera.position.x - shell.center.x
    const dz = camera.position.z - shell.center.z
    const plan = s.camera === 'top' && Math.hypot(dx, dz) < camera.position.y * 0.45

    shell.walls.forEach((w, i) => {
      const out = (camera.position.x - w.cx) * w.nx + (camera.position.z - w.cz) * w.nz
      if (out > 0.35) low.current[i] = true
      else if (out < 0.05) low.current[i] = false
      const rise = easeOut(clamp01((t.current - 0.07 * w.order) / 0.75))
      const target = ((plan || low.current[i] ? CURB : Math.min(CUT, w.height)) / w.height) * rise
      w.s += (target - w.s) * k
      const sy = Math.max(w.s, 0.003)
      for (const o of w.objects) o.scale.y = sy
      for (const e of w.extras) e.object.scale.y = Math.max(0.003, Math.min(1, (w.s * w.height) / e.height))
    })
    for (const j of shell.joints) {
      const sy = j.walls.length ? Math.min(...j.walls.map((w) => w.s)) : 1
      j.object.scale.y = Math.max(sy, 0.003)
    }

    // furniture already in the room
    const f = fade.current
    const appear = clamp01((t.current - 0.55) / 0.5)
    const fill = (s.existing === 'show' ? 1 : s.existing === 'ghost' ? 0.06 : 0) * appear
    const edge = (s.existing === 'ghost' ? 0.4 : 0) * appear
    f.fill += (fill - f.fill) * k
    f.edge += (edge - f.edge) * k
    const solid = f.fill > 0.97
    MAT.existing.opacity = solid ? 1 : f.fill
    if (MAT.existing.transparent === solid) {
      MAT.existing.transparent = !solid
      MAT.existing.depthWrite = solid
      MAT.existing.needsUpdate = true
    }
    MAT.existingEdge.opacity = f.edge
    const casting = f.fill > 0.5
    let tvTarget = appear
    for (const e of shell.existing) {
      if (e.mounted) {
        if (e.wall && e.wall.s * e.wall.height < 1.6) tvTarget = 0
        continue
      }
      e.mesh.visible = f.fill > 0.012 || f.edge > 0.012
      e.edges.visible = f.edge > 0.012
      if (casting !== f.casting) e.mesh.castShadow = casting
    }
    f.casting = casting
    f.tv += (tvTarget - f.tv) * k
    const tvSolid = f.tv > 0.97
    MAT.tv.opacity = tvSolid ? 1 : f.tv
    if (MAT.tv.transparent === tvSolid) {
      MAT.tv.transparent = !tvSolid
      MAT.tv.needsUpdate = true
    }
    for (const e of shell.existing) if (e.mounted) e.mesh.visible = f.tv > 0.02
  })
  return null
}

// ---------------------------------------------------------------------------------------------------------
// Camera, key light, centring in the free part of the screen
// ---------------------------------------------------------------------------------------------------------
type Controls = InstanceType<typeof import('camera-controls').default>

function Rig({ shell, layout, hero, plan }: { shell: Shell; layout: LayoutDetail; hero: boolean; plan: Plan | null }) {
  const controls = useRef<Controls>(null)
  const light = useRef<THREE.DirectionalLight>(null)
  const lightTarget = useMemo(() => new THREE.Object3D(), [])
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera
  const size = useThree((s) => s.size)
  const preset = useApp((s) => s.camera)
  const nonce = useApp((s) => s.cameraNonce)
  const state = useRef({ touched: false, sx: 0, sy: 0, w: 0, h: 0, first: true, idle: 0 })

  const target = useMemo(() => new THREE.Vector3(shell.center.x, Math.min(0.5, shell.height * 0.2), shell.center.z), [shell])

  const pose = (which: 'iso' | 'top' | 'front' | 'intro') => {
    const s = useApp.getState()
    const H = size.height
    const W = size.width
    const freeW = hero ? W * 0.52 : Math.max(320, W - (W > 1000 ? 348 : 0))
    const freeH = hero ? H * 0.72 : Math.max(240, H - 180)
    const tanV = Math.tan(rad(FOV / 2)) * (freeH / H)
    const tanH = Math.tan(rad(FOV / 2)) * (freeW / H)
    const n = new THREE.Vector3(layout.facing[0], 0, layout.facing[1])
    const xs = shell.room.outline.map((p) => p[0] * IN)
    const zs = shell.room.outline.map((p) => p[1] * IN)
    const wx = Math.max(...xs) - Math.min(...xs)
    const wz = Math.max(...zs) - Math.min(...zs)
    void s
    if (which === 'top') {
      const wide = wx >= wz
      const halfH = (wide ? wz : wx) / 2 + 0.55
      const halfW = (wide ? wx : wz) / 2 + 0.55
      const dist = Math.max(halfH / tanV, halfW / tanH) + CURB
      const v = wide ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0)
      return { pos: new THREE.Vector3(target.x, 0, target.z).addScaledVector(v, 0.004).setY(dist), tgt: new THREE.Vector3(target.x, 0, target.z) }
    }
    const longX = wx >= wz
    const short = longX ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0)
    const long = longX ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 0, 1)
    const along = n.dot(short)
    // look across the short side so the long side spans the screen; lean toward what the sofa faces
    const base = Math.abs(along) > 0.7 ? short.clone().multiplyScalar(Math.sign(along)) : short
    const side = Math.abs(along) > 0.7 ? long : n
    const cut = Math.min(CUT, shell.height)
    const fit = Math.hypot(shell.radius, cut / 2) / Math.sin(Math.atan(Math.min(tanV, tanH)))
    if (which === 'front') {
      const polar = rad(70)
      const dist = fit * 0.8
      return { pos: target.clone().add(new THREE.Vector3(n.x * Math.sin(polar), Math.cos(polar), n.z * Math.sin(polar)).multiplyScalar(dist)), tgt: target }
    }
    const lean = Math.abs(along) > 0.7 ? 24 : 12
    const swing = which === 'intro' ? lean - 20 : lean
    const v = base.clone().multiplyScalar(Math.cos(rad(swing))).addScaledVector(side, Math.sin(rad(swing))).normalize()
    const polar = rad(which === 'intro' ? 44 : 52)
    const dist = fit * (which === 'intro' ? 1.06 : hero ? 0.98 : 0.88)
    return { pos: target.clone().add(new THREE.Vector3(v.x * Math.sin(polar), Math.cos(polar), v.z * Math.sin(polar)).multiplyScalar(dist)), tgt: target }
  }

  // a new room: start a little wide, glide in
  useEffect(() => {
    const c = controls.current
    if (!c) return
    state.current.touched = false
    const a = pose(hero || STILL || preset !== 'iso' ? preset : 'intro')
    c.setLookAt(a.pos.x, a.pos.y, a.pos.z, a.tgt.x, a.tgt.y, a.tgt.z, false)
    if (!hero && !STILL && preset === 'iso') {
      const b = pose('iso')
      c.setLookAt(b.pos.x, b.pos.y, b.pos.z, b.tgt.x, b.tgt.y, b.tgt.z, true)
    }
    state.current.first = false
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell, hero])

  // a preset button
  useEffect(() => {
    const c = controls.current
    if (!c || nonce === 0) return
    state.current.touched = false
    const a = pose(preset)
    c.setLookAt(a.pos.x, a.pos.y, a.pos.z, a.tgt.x, a.tgt.y, a.tgt.z, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce])

  // selecting a piece brings it to the middle of the free space; letting go returns to the room
  const selected = useApp((s) => s.selectedSlot)
  const focused = useRef(false)
  useEffect(() => {
    const c = controls.current
    if (!c || hero) return
    const pl = selected ? layout.placements[selected] : undefined
    const item = selected ? plan?.items.find((i) => i.slot === selected) : undefined
    if (pl && item) {
      // ease toward the piece, but keep about half the room in frame around it
      const room = pose(useApp.getState().camera)
      const roomDist = room.pos.distanceTo(room.tgt)
      const k = 0.6
      const y = Math.min(((item.dims_in.h ?? 20) * IN) / 2, 0.6)
      c.moveTo(
        room.tgt.x + (pl.x_in * IN - room.tgt.x) * k,
        room.tgt.y + (y - room.tgt.y) * k,
        room.tgt.z + (pl.z_in * IN - room.tgt.z) * k,
        !STILL,
      )
      c.dollyTo(roomDist * 0.94, !STILL)
      focused.current = true
    } else if (focused.current) {
      const room = pose(useApp.getState().camera)
      c.moveTo(room.tgt.x, room.tgt.y, room.tgt.z, true)
      c.dollyTo(room.pos.distanceTo(room.tgt), true)
      focused.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, layout])

  useEffect(() => {
    const c = controls.current
    if (!c) return
    const stop = () => (state.current.touched = true)
    c.addEventListener('controlstart', stop)
    return () => c.removeEventListener('controlstart', stop)
  }, [])

  useEffect(() => {
    if (light.current) light.current.target = lightTarget
  }, [lightTarget])

  useEffect(
    () => () => {
      camera.clearViewOffset()
    },
    [camera],
  )

  useFrame((_, dt) => {
    const c = controls.current
    const s = useApp.getState()
    const st = state.current
    const d = Math.min(dt, 0.1)

    // keep the room centred in the part of the screen the panels leave free
    const W = size.width
    const H = size.height
    let cx: number
    let cy: number
    if (hero) {
      cx = W * 0.7
      cy = H * 0.5
    } else {
      const wide = W > 1000
      const left = wide && (s.stage === 'running' || s.stage === 'done') ? 348 : 0
      const right = !wide ? 0 : s.cartOpen ? 432 : s.selectedSlot ? 396 : 0
      cx = (left + (W - right)) / 2
      cy = (60 + (H - 120)) / 2
    }
    const tx = cx - W / 2
    const ty = cy - H / 2
    const k = st.w === 0 || STILL ? 1 : 1 - Math.exp(-d * 6)
    const nx = st.sx + (tx - st.sx) * k
    const ny = st.sy + (ty - st.sy) * k
    if (Math.abs(nx - st.sx) > 0.05 || Math.abs(ny - st.sy) > 0.05 || st.w !== W || st.h !== H || !camera.view?.enabled) {
      st.sx = nx
      st.sy = ny
      st.w = W
      st.h = H
      camera.setViewOffset(W, H, -nx, -ny, W, H)
    }

    if (c) {
      const idle = hero || (!st.touched && !s.selectedSlot && !s.cartOpen && !s.measuring && s.camera !== 'top')
      if (idle && !STILL) {
        if (hero) c.azimuthAngle += d * rad(3)
        else {
          // a slow sway around the composed view, not a full turn: the long side stays across the screen
          st.idle += d
          const w = (Math.PI * 2) / 28
          c.azimuthAngle += d * rad(12) * w * Math.cos(w * st.idle)
        }
      } else st.idle = 0
      // the key light rides with the camera, so the cut-away side is always the lit side
      if (light.current) {
        const az = c.azimuthAngle - 0.38
        const el = rad(58)
        const L = shell.radius * 2 + 6
        light.current.position.set(
          target.x + Math.sin(az) * Math.cos(el) * L,
          Math.sin(el) * L,
          target.z + Math.cos(az) * Math.cos(el) * L,
        )
      }
    }
  })

  const r = shell.radius + 1.2
  return (
    <>
      <CameraControls
        ref={controls as never}
        makeDefault
        enabled={!hero}
        minPolarAngle={0}
        maxPolarAngle={Math.PI / 2 - 0.1}
        minDistance={shell.radius * 0.9}
        maxDistance={shell.radius * 7}
        smoothTime={0.42}
        draggingSmoothTime={0.16}
        azimuthRotateSpeed={0.7}
        polarRotateSpeed={0.7}
        dollySpeed={0.5}
        truckSpeed={0}
      />
      <primitive object={lightTarget} position={[target.x, 0, target.z]} />
      <directionalLight
        ref={light}
        castShadow
        intensity={2.3}
        color="#ffffff"
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-normalBias={0.03}
        shadow-radius={9}
        shadow-intensity={0.9}
      >
        <orthographicCamera attach="shadow-camera" args={[-r, r, r, -r, 1, shell.radius * 4 + 16]} />
      </directionalLight>
    </>
  )
}

// ---------------------------------------------------------------------------------------------------------
// Drafting marks: the wall being measured, and the floor-plan labels in the top view
// ---------------------------------------------------------------------------------------------------------
function WallMark({ wall, shell, glow, value }: { wall: RoomWall; shell: Shell; glow: boolean; value?: number }) {
  const { t, n } = wallFrame(wall, shell.room.outline)
  const off = shell.insetIn + 4
  const a: [number, number, number] = [(wall.a[0] + n[0] * off) * IN, 0.02, (wall.a[1] + n[1] * off) * IN]
  const b: [number, number, number] = [(wall.b[0] + n[0] * off) * IN, 0.02, (wall.b[1] + n[1] * off) * IN]
  const tk = 0.05
  const pts: [number, number, number][] = [
    a,
    b,
    [a[0] - n[0] * tk, a[1], a[2] - n[1] * tk],
    [a[0] + n[0] * tk, a[1], a[2] + n[1] * tk],
    [b[0] - n[0] * tk, b[1], b[2] - n[1] * tk],
    [b[0] + n[0] * tk, b[1], b[2] + n[1] * tk],
  ]
  const len = Math.hypot(b[0] - a[0], b[2] - a[2])
  const strip = useRef<THREE.MeshBasicMaterial>(null)
  useFrame(({ clock }) => {
    if (strip.current) strip.current.opacity = 0.2 + 0.1 * Math.sin(clock.elapsedTime * 3.2)
  })
  const mid: [number, number, number] = [(a[0] + b[0]) / 2, 0.02, (a[2] + b[2]) / 2]
  return (
    <group>
      {glow && (
        <mesh position={[mid[0] + n[0] * 0.12, 0.012, mid[2] + n[1] * 0.12]} rotation={[-Math.PI / 2, 0, Math.atan2(-t[1], t[0])]} renderOrder={20}>
          <planeGeometry args={[len, 0.34]} />
          <meshBasicMaterial ref={strip} color={COLORS.ice} transparent opacity={0.24} depthWrite={false} toneMapped={false} />
        </mesh>
      )}
      <Mark points={pts} segments color={COLORS.ice} width={1.6} />
      <Label position={[mid[0] + n[0] * 0.22, 0.02, mid[2] + n[1] * 0.22]} style={glow ? { borderColor: 'rgba(159,227,240,.55)' } : undefined}>
        {inches(value ?? wall.length_in, 1)} in
      </Label>
    </group>
  )
}

function DoorMark({ door, shell, label }: { door: RoomDoor; shell: Shell; label?: string }) {
  const ax: Vec2 = door.axis === 'z' ? [0, 1] : [1, 0]
  const w = door.width_in
  const hinge: Vec2 = [door.center[0] - (ax[0] * w) / 2, door.center[1] - (ax[1] * w) / 2]
  const base: Vec2 = [hinge[0] + door.into_room[0] * shell.insetIn, hinge[1] + door.into_room[1] * shell.insetIn]
  const pts: [number, number, number][] = []
  for (let i = 0; i <= 18; i++) {
    const a = (i / 18) * (Math.PI / 2)
    const x = base[0] + (ax[0] * Math.cos(a) + door.into_room[0] * Math.sin(a)) * w
    const z = base[1] + (ax[1] * Math.cos(a) + door.into_room[1] * Math.sin(a)) * w
    pts.push([x * IN, 0.016, z * IN])
  }
  const leaf: [number, number, number][] = [
    [base[0] * IN, 0.016, base[1] * IN],
    [(base[0] + door.into_room[0] * w) * IN, 0.016, (base[1] + door.into_room[1] * w) * IN],
  ]
  const c: [number, number, number] = [
    (door.center[0] + door.into_room[0] * (w * 0.55)) * IN,
    0.02,
    (door.center[1] + door.into_room[1] * (w * 0.55)) * IN,
  ]
  return (
    <group>
      <Mark points={pts} color={label ? COLORS.ice : COLORS.bone} width={1.2} opacity={label ? 1 : 0.7} dashed xray={false} />
      <Mark points={leaf} color={label ? COLORS.ice : COLORS.bone} width={1.4} opacity={label ? 1 : 0.8} xray={false} />
      <Label position={c} style={label ? { borderColor: 'rgba(159,227,240,.55)' } : { color: '#aeaaa3' }}>
        {label ?? `Door ${inches(door.width_in, 1)} in`}
      </Label>
    </group>
  )
}

function Marks({ shell, layout, plan }: { shell: Shell; layout: LayoutDetail; plan: Plan | null }) {
  const measuring = useApp((s) => s.measuring)
  const top = useApp((s) => s.camera === 'top')
  const overrides = useApp((s) => s.overrides)
  const { walls, doors, outline } = shell.room

  const pick = (key: 'wall' | 'depth'): RoomWall | null => {
    if (!walls.length) return null
    if (!plan) return key === 'wall' ? layout.anchorWall : layout.depthWall
    const closest = (pool: RoomWall[], v: number) => [...pool].sort((a, b) => Math.abs(a.length_in - v) - Math.abs(b.length_in - v))[0] ?? null
    const main = walls.find((w) => w.id === 'wall') ?? closest(walls, plan.room.wall.value_in)
    if (key === 'wall' || !main) return main
    const mt = wallFrame(main, outline).t
    const cross = walls.filter((w) => {
      const t = wallFrame(w, outline).t
      return Math.abs(t[0] * mt[0] + t[1] * mt[1]) < 0.2
    })
    return closest(cross, plan.room.depth.value_in)
  }

  const measured = measuring === 'wall' || measuring === 'depth' ? pick(measuring) : null
  const door = doors[0]
  return (
    <>
      {measured && <WallMark wall={measured} shell={shell} glow value={overrides[measuring as 'wall' | 'depth']} />}
      {door && (measuring === 'door_width' || measuring === 'door_height') && (
        <DoorMark
          door={door}
          shell={shell}
          label={
            measuring === 'door_width'
              ? `Door width ${inches(overrides.door_width ?? door.width_in, 1)} in`
              : `Door height ${inches(overrides.door_height ?? door.height_in, 1)} in`
          }
        />
      )}
      {top && !measuring && (
        <>
          {walls.map((w) => {
            const { n, mid } = wallFrame(w, outline)
            const o = shell.insetIn + 13
            return (
              <Label key={w.id} position={[(mid[0] - n[0] * o) * IN, CURB, (mid[1] - n[1] * o) * IN]} style={{ color: '#aeaaa3' }}>
                {inches(w.length_in, 1)} in
              </Label>
            )
          })}
          {doors.map((d) => (
            <DoorMark key={d.id} door={d} shell={shell} />
          ))}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------------------------------------
// Room contents
// ---------------------------------------------------------------------------------------------------------
function RoomContents({ shell, plan, hero }: { shell: Shell; plan: Plan | null; hero: boolean }) {
  const setRoom = useApp((s) => s.setRoom)
  useEffect(() => {
    setRoom(shell.room)
  }, [shell, setRoom])

  const layout = useMemo(() => layoutDetail(shell.room, plan?.items ?? []), [shell, plan])
  const placed = useApp((s) => s.placed)
  const selected = useApp((s) => s.selectedSlot)
  const hovered = useApp((s) => s.hoveredSlot)
  const ghost = useApp((s) => s.ghost)
  const photoStyle = useApp((s) => s.modelStyle === 'photo')
  const manifest = useModelManifest(`${MODELS}index.json`)
  useEffect(() => {
    // warm the cache so a piece doesn't pop from clay to its model as it lands
    for (const i of plan?.items ?? []) {
      const e = manifest[i.product_id]
      if (e && photoStyle) useGLTF.preload(MODELS + e.file)
    }
  }, [manifest, plan, photoStyle])
  const fallback: Placement = { slot: '', x_in: shell.center.x / IN, z_in: shell.center.z / IN, rotation: 0 }

  return (
    <>
      <primitive object={shell.group} />
      <ShellAnimator shell={shell} />
      <Rig shell={shell} layout={layout} hero={hero} plan={plan} />
      {!hero && <Marks shell={shell} layout={layout} plan={plan} />}
      {!hero &&
        plan?.items
          .filter((i) => placed[i.slot] && layout.placements[i.slot])
          .map((item) => {
            const e = photoStyle ? manifest[item.product_id] : undefined
            return (
            <Piece
              key={`${item.slot}:${item.product_id}`}
              photo={e ? { url: MODELS + e.file, rotY: ((e.rot_y_deg ?? 0) * Math.PI) / 180 } : null}
              item={item}
              placement={layout.placements[item.slot]}
              phase={placed[item.slot]}
              selected={selected === item.slot}
              hovered={hovered === item.slot}
              interactive
            />
            )
          })}
      {!hero && ghost && <GhostPiece key={ghost.key} ghost={ghost} placement={layout.placements[ghost.slot] ?? fallback} />}
    </>
  )
}

function ScanRoom({ url, plan, hero }: { url: string; plan: Plan | null; hero: boolean }) {
  const gltf = useGLTF(url)
  const shell = useMemo(() => buildScanShell(gltf.scene) ?? buildMeshShell(gltf.scene), [gltf.scene])
  return <RoomContents shell={shell} plan={plan} hero={hero} />
}

function TypedRoom({ plan }: { plan: Plan }) {
  const shell = useMemo(() => buildTypedShell(plan.room), [plan.room])
  return <RoomContents shell={shell} plan={plan} hero={false} />
}

/** If a scan can't be read, fall back to the typed room instead of taking the page down. */
class ScanBoundary extends Component<{ fallback: ReactNode; children: ReactNode; resetKey: string }, { failed: string | null }> {
  state = { failed: null as string | null }
  static getDerivedStateFromError() {
    return { failed: 'x' }
  }
  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.failed) this.setState({ failed: null })
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function Room() {
  const plan = useApp((s) => s.plan)
  const modelUrl = useApp((s) => s.modelUrl)
  const stage = useApp((s) => s.stage)
  const hero = stage === 'start'
  if (modelUrl) {
    return (
      <ScanBoundary resetKey={modelUrl} fallback={plan && !hero ? <TypedRoom plan={plan} /> : null}>
        <Suspense fallback={null}>
          <ScanRoom key={modelUrl} url={modelUrl} plan={hero ? null : plan} hero={hero} />
        </Suspense>
      </ScanBoundary>
    )
  }
  if (plan && !hero) return <TypedRoom key={plan.plan_id} plan={plan} />
  return null
}

// ---------------------------------------------------------------------------------------------------------
// The desk the model sits on
// ---------------------------------------------------------------------------------------------------------
function Desk() {
  const pool = useMemo(() => {
    const c = document.createElement('canvas')
    c.width = c.height = 256
    const g = c.getContext('2d')!
    const grad = g.createRadialGradient(128, 128, 0, 128, 128, 128)
    grad.addColorStop(0, 'rgba(255,250,240,0.085)')
    grad.addColorStop(0.45, 'rgba(255,250,240,0.035)')
    grad.addColorStop(1, 'rgba(255,250,240,0)')
    g.fillStyle = grad
    g.fillRect(0, 0, 256, 256)
    const t = new THREE.CanvasTexture(c)
    t.colorSpace = THREE.SRGBColorSpace
    return t
  }, [])
  return (
    <group>
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.112, 0]} renderOrder={-3}>
        <planeGeometry args={[26, 26]} />
        <meshBasicMaterial map={pool} transparent depthWrite={false} toneMapped={false} />
      </mesh>
      <Grid
        position={[0, -0.108, 0]}
        args={[60, 60]}
        cellSize={0.3048}
        cellThickness={0.6}
        cellColor="#25272d"
        sectionSize={1.2192}
        sectionThickness={0.9}
        sectionColor="#30333a"
        fadeDistance={22}
        fadeStrength={2.2}
        infiniteGrid
        followCamera={false}
        renderOrder={-2}
      />
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.104, 0]} receiveShadow renderOrder={-1}>
        <planeGeometry args={[60, 60]} />
        <shadowMaterial transparent opacity={0.5} />
      </mesh>
    </group>
  )
}

export default function RoomScene() {
  return (
    <div
      className="absolute inset-0"
      style={{
        isolation: 'isolate',
        background: 'radial-gradient(120% 90% at 58% 42%, #1a1b20 0%, #111215 46%, #0c0d0f 78%)',
      }}
    >
      <Canvas
        shadows="percentage"
        dpr={[1, 2]}
        camera={CAMERA}
        gl={GL}
        onCreated={({ gl }) => {
          gl.localClippingEnabled = true
          gl.setClearColor(0x000000, 0)
        }}
        onPointerMissed={() => {
          const s = useApp.getState()
          if (s.stage !== 'start' && s.selectedSlot) s.select(null)
        }}
      >
        <hemisphereLight args={['#f3f6ff', '#b9b7b3', 0.62]} />
        <Environment resolution={64} environmentIntensity={0.55}>
          <color attach="background" args={['#15161a']} />
          <Lightformer form="rect" intensity={2.2} color="#ffffff" position={[0, 6, 0]} rotation-x={Math.PI / 2} scale={[12, 12, 1]} />
          <Lightformer form="rect" intensity={1.0} color="#fff3e6" position={[-7, 2.5, 3]} rotation-y={Math.PI / 2} scale={[8, 4, 1]} />
          <Lightformer form="rect" intensity={0.7} color="#dfeaf2" position={[7, 2, -4]} rotation-y={-Math.PI / 2} scale={[8, 4, 1]} />
        </Environment>
        <Desk />
        <Room />
      </Canvas>
      <div
        ref={(el) => {
          overlayRef.current = el
        }}
        className="pointer-events-none absolute inset-0 overflow-hidden"
      />
    </div>
  )
}
