// New furniture, the rejected "ghost", and the drafting marks around them (frames, dimension callouts).
import { Component, Suspense, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line, useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import type { Dims, Placement, PlanItem } from '../types'
import { productById } from '../data'
import { useApp, type Ghost, type Phase } from '../store'
import { inches } from '../lib/format'
import { COLORS, IN, STILL } from './roomModel'
import { categoryOf } from './layout'
import { Shape } from './shapes'

/** DOM layer over the canvas that <Html> labels portal into (see RoomScene). */
export const overlayRef: { current: HTMLDivElement | null } = { current: null }
const portal = overlayRef as unknown as RefObject<HTMLElement>

export const pill: CSSProperties = {
  font: '500 11px/1 var(--font-mono)',
  fontVariantNumeric: 'tabular-nums',
  letterSpacing: '-0.01em',
  color: COLORS.bone,
  background: 'rgba(12,13,15,.82)',
  border: '1px solid rgba(255,255,255,.1)',
  borderRadius: 5,
  padding: '4px 6px',
  whiteSpace: 'nowrap',
  pointerEvents: 'none',
  userSelect: 'none',
}

const noRay = () => null
type P3 = [number, number, number]

function boxEdges(w: number, h: number, d: number): P3[] {
  const x = w / 2
  const z = d / 2
  const c: P3[] = [
    [-x, 0, -z],
    [x, 0, -z],
    [x, 0, z],
    [-x, 0, z],
    [-x, h, -z],
    [x, h, -z],
    [x, h, z],
    [-x, h, z],
  ]
  const e = [0, 1, 1, 2, 2, 3, 3, 0, 4, 5, 5, 6, 6, 7, 7, 4, 0, 4, 1, 5, 2, 6, 3, 7]
  return e.map((i) => c[i])
}

/** A line that stays readable on both the pale model and the dark desk: colour over a dark casing. */
export function Mark({
  points,
  color,
  width = 1.6,
  opacity = 1,
  segments = false,
  dashed = false,
  xray = true,
}: {
  points: P3[]
  color: string
  width?: number
  opacity?: number
  segments?: boolean
  dashed?: boolean
  xray?: boolean
}) {
  return (
    <>
      <Line
        points={points}
        segments={segments}
        color={COLORS.casing}
        lineWidth={width + 2.4}
        transparent
        opacity={0.5 * opacity}
        depthTest={!xray}
        depthWrite={false}
        renderOrder={40}
        raycast={noRay}
      />
      <Line
        points={points}
        segments={segments}
        color={color}
        lineWidth={width}
        transparent
        opacity={opacity}
        depthTest={!xray}
        depthWrite={false}
        dashed={dashed}
        dashSize={0.06}
        gapSize={0.045}
        renderOrder={41}
        raycast={noRay}
      />
    </>
  )
}

function Frame(p: { w: number; h: number; d: number; color: string; width?: number; opacity?: number; dashed?: boolean; xray?: boolean }) {
  const pts = useMemo(() => boxEdges(p.w, p.h, p.d), [p.w, p.h, p.d])
  return <Mark points={pts} segments color={p.color} width={p.width} opacity={p.opacity} dashed={p.dashed} xray={p.xray} />
}

export function Label({ position, children, style }: { position: P3; children: React.ReactNode; style?: CSSProperties }) {
  return (
    <Html position={position} center portal={portal} zIndexRange={[30, 0]} style={{ pointerEvents: 'none' }}>
      <div style={{ ...pill, ...style }}>{children}</div>
    </Html>
  )
}

const tmp = new THREE.Vector3()

/** The red tag over a piece that does not fit: name on one line, the real math under it. Sits above the piece. */
function FitTag({ position, name, math, opacityRef }: { position: P3; name?: string; math: string; opacityRef?: RefObject<HTMLDivElement | null> }) {
  return (
    <Html position={position} portal={portal} zIndexRange={[40, 31]} style={{ pointerEvents: 'none' }}>
      <div
        ref={opacityRef}
        style={{
          ...pill,
          transform: 'translate(-50%, -100%)',
          width: 'max-content',
          maxWidth: 300,
          padding: '7px 9px 8px',
          borderColor: 'rgba(255,107,94,.45)',
          borderRadius: 7,
          whiteSpace: 'normal',
          textAlign: 'left',
          boxShadow: '0 12px 30px -12px rgba(0,0,0,.8)',
        }}
      >
        {name && (
          <div
            style={{
              font: '600 12px/1.25 var(--font-sans)',
              letterSpacing: 0,
              color: COLORS.bone,
              marginBottom: 4,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {name}
          </div>
        )}
        <div
          style={{
            font: '500 11px/1.4 var(--font-mono)',
            color: COLORS.nofit,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {math}
        </div>
      </div>
    </Html>
  )
}

/** W x D x H along the three edges nearest the camera. */
function Callouts({ w, d, h, dims }: { w: number; d: number; h: number; dims: Dims }) {
  const g = useRef<THREE.Group>(null)
  const [sx, setSx] = useState(1)
  const [sz, setSz] = useState(1)
  useFrame(({ camera }) => {
    if (!g.current) return
    const p = g.current.worldToLocal(tmp.copy(camera.position))
    const nx = p.x >= 0 ? 1 : -1
    const nz = p.z >= 0 ? 1 : -1
    if (nx !== sx) setSx(nx)
    if (nz !== sz) setSz(nz)
  })
  const o = 0.09
  const tick = 0.035
  const x = sx * (w / 2 + o)
  const z = sz * (d / 2 + o)
  const y = 0.012
  const wide: P3[] = [
    [-w / 2, y, z],
    [w / 2, y, z],
    [-w / 2, y, z - tick],
    [-w / 2, y, z + tick],
    [w / 2, y, z - tick],
    [w / 2, y, z + tick],
  ]
  const deep: P3[] = [
    [x, y, -d / 2],
    [x, y, d / 2],
    [x - tick, y, -d / 2],
    [x + tick, y, -d / 2],
    [x - tick, y, d / 2],
    [x + tick, y, d / 2],
  ]
  const hx = sx * (w / 2 + o)
  const hz = -sz * (d / 2)
  const tall: P3[] = [
    [hx, 0, hz],
    [hx, h, hz],
    [hx - tick, 0, hz],
    [hx + tick, 0, hz],
    [hx - tick, h, hz],
    [hx + tick, h, hz],
  ]
  return (
    <group ref={g}>
      <Mark points={wide} segments color={COLORS.ice} width={1.5} />
      <Mark points={deep} segments color={COLORS.ice} width={1.5} />
      <Label position={[0, y, z + 0.05 * sz]}>{inches(dims.w)} in</Label>
      <Label position={[x + 0.05 * sx, y, 0]}>{inches(dims.d)} in</Label>
      {dims.h !== null && h > 0.08 && (
        <>
          <Mark points={tall} segments color={COLORS.ice} width={1.5} />
          <Label position={[hx + 0.05 * sx, h / 2, hz]}>{inches(dims.h)} in</Label>
        </>
      )}
    </group>
  )
}

const TINT: Record<string, string> = {
  gray: '#8d8d8f',
  grey: '#8d8d8f',
  'dark gray': '#5b5b5e',
  beige: '#cdbb9c',
  black: '#2d2c2b',
  white: '#ffffff',
  brown: '#7b5b3e',
  birch: '#d6b98c',
  oak: '#b9945f',
  natural: '#cdb58f',
  blue: '#5d7fa6',
  green: '#6f8f6a',
  red: '#a8483e',
  yellow: '#d9b44a',
  pink: '#d79aa6',
  turquoise: '#4f9d9a',
  orange: '#d0823f',
}
function clayFor(color: string | null | undefined, amount: number): THREE.Color {
  const base = new THREE.Color(COLORS.clay)
  const key = (color ?? '').toLowerCase()
  const hit = TINT[key] ?? Object.entries(TINT).find(([k]) => key.includes(k))?.[1]
  return hit ? base.lerp(new THREE.Color(hit), amount) : base
}

const easeOutBack = (t: number) => {
  const c1 = 1.25
  const c3 = c1 + 1
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2)
}

/** A product's own 3D model (AI-generated from its IKEA photo), stretched to the listed W x D x H. */
function PhotoModel({
  url,
  w,
  d,
  h,
  rotY,
  register,
}: {
  url: string
  w: number
  d: number
  h: number
  rotY: number
  register: (m: THREE.Material[]) => void
}) {
  const { scene } = useGLTF(url)
  const built = useMemo(() => {
    const root = scene.clone(true)
    const materials: THREE.Material[] = []
    root.traverse((o) => {
      const m = o as THREE.Mesh
      if (!m.isMesh) return
      m.castShadow = true
      m.receiveShadow = true
      m.renderOrder = 11
      const own = (Array.isArray(m.material) ? m.material : [m.material]).map((x) => x.clone())
      materials.push(...own)
      m.material = Array.isArray(m.material) ? own : own[0]
    })
    root.rotation.set(0, rotY, 0)
    root.updateMatrixWorld(true)
    const box = new THREE.Box3().setFromObject(root)
    const size = box.getSize(new THREE.Vector3())
    const centre = box.getCenter(new THREE.Vector3())
    root.position.set(-centre.x, -box.min.y, -centre.z)
    const holder = new THREE.Group()
    holder.add(root)
    holder.scale.set(w / (size.x || 1), h / (size.y || 1), d / (size.z || 1))
    return { holder, materials }
  }, [scene, w, d, h, rotY])
  useEffect(() => {
    register(built.materials)
    return () => {
      register([])
      built.materials.forEach((m) => m.dispose())
    }
  }, [built, register])
  return <primitive object={built.holder} />
}

class ModelBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export interface PhotoEntry {
  url: string
  rotY: number
}

export function Piece({
  item,
  placement,
  phase,
  selected,
  hovered,
  interactive,
  photo,
}: {
  item: PlanItem
  placement: Placement
  phase: Phase
  selected: boolean
  hovered: boolean
  interactive: boolean
  /** the product's own 3D model, when it has one and the person wants photo models */
  photo?: PhotoEntry | null
}) {
  const product = productById[item.product_id]
  const category = categoryOf(item)
  const w = item.dims_in.w * IN
  const d = item.dims_in.d * IN
  const h = Math.max(item.dims_in.h ?? 0.5, 0.4) * IN

  const mats = useMemo(() => {
    const color = clayFor(product?.color, category === 'rug' ? 0.2 : 0.15)
    const main = new THREE.MeshStandardMaterial({ color, roughness: 0.94, metalness: 0 })
    const dark = new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.84), roughness: 0.96, metalness: 0 })
    // depth-only pass so a translucent piece shows its surface, not its insides
    const pre = new THREE.MeshBasicMaterial({ colorWrite: false, transparent: true })
    // a piece that stopped fitting after a new measurement: the same red volume as a rejection, but it stays
    const bad = new THREE.MeshBasicMaterial({ color: COLORS.nofit, transparent: true, opacity: 0.3, depthWrite: false, toneMapped: false })
    return { main, dark, pre, bad }
  }, [product?.color, category])
  useEffect(() => () => Object.values(mats).forEach((m) => m.dispose()), [mats])

  const photoMats = useRef<THREE.Material[]>([])
  const register = useCallback((m: THREE.Material[]) => {
    photoMats.current = m
  }, [])

  const drop = useRef<THREE.Group>(null)
  const pre = useRef<THREE.Group>(null)
  const pulse = useRef<THREE.Group>(null)
  const st = useRef({ t: STILL ? 10 : 0, opacity: 0, pulse: -1, phase })

  useFrame((_, dt) => {
    const s = st.current
    const step = Math.min(dt, 0.1)
    s.t += step
    if (s.phase === 'picked' && phase !== 'picked') s.pulse = 0
    s.phase = phase
    const k = Math.min(s.t / 0.6, 1)
    if (drop.current) drop.current.position.y = (1 - easeOutBack(k)) * 0.45
    const target = (phase === 'picked' ? 0.68 : 1) * Math.min(s.t / 0.25, 1)
    s.opacity += (target - s.opacity) * (STILL ? 1 : 1 - Math.exp(-step * 9))
    const see = s.opacity < 0.985
    const apply = (m: THREE.Material) => {
      m.opacity = see ? s.opacity : 1
      if (m.transparent !== see) {
        m.transparent = see
        m.needsUpdate = true
      }
    }
    apply(mats.main)
    apply(mats.dark)
    for (const m of photoMats.current) apply(m)
    if (pre.current) pre.current.visible = see && photoMats.current.length === 0
    if (pulse.current) {
      if (s.pulse >= 0) {
        s.pulse += step
        const p = Math.min(s.pulse / 0.7, 1)
        pulse.current.visible = p < 1
        pulse.current.scale.setScalar(1 + 0.05 * p)
        pulse.current.traverse((o) => {
          const lm = (o as THREE.Mesh).material as THREE.Material & { opacity: number }
          if (lm && 'opacity' in lm) lm.opacity = (1 - p) * (o.renderOrder === 40 ? 0.5 : 1)
        })
        if (p >= 1) s.pulse = -1
      } else pulse.current.visible = false
    }
  })

  const select = useApp((s) => s.select)
  const hover = useApp((s) => s.hover)
  const handlers = interactive
    ? {
        onPointerOver: (e: { stopPropagation: () => void }) => {
          e.stopPropagation()
          hover(item.slot)
          document.body.style.cursor = 'pointer'
        },
        onPointerOut: () => {
          hover(null)
          document.body.style.cursor = ''
        },
        onClick: (e: { stopPropagation: () => void }) => {
          e.stopPropagation()
          select(item.slot)
        },
      }
    : {}
  useEffect(
    () => () => {
      document.body.style.cursor = ''
    },
    [],
  )

  const translucent = phase === 'picked'
  const verdict = item.fit?.verdict
  const noFit = verdict === 'no_fit'
  const failing = noFit ? item.fit.results.find((r) => r.verdict === 'no_fit')?.math : undefined
  const clay = <Shape category={category} w={w} d={d} h={h} mat={mats.main} dark={mats.dark} ro={11} shadow={category !== 'rug'} />
  return (
    <group position={[placement.x_in * IN, 0, placement.z_in * IN]} rotation-y={(placement.rotation * Math.PI) / 180} {...handlers}>
      <group ref={drop}>
        <group ref={pre} visible={false}>
          {!noFit && <Shape category={category} w={w} d={d} h={h} mat={mats.pre} ro={10} shadow={false} />}
        </group>
        {noFit ? (
          <Shape category={category} w={w} d={d} h={h} mat={mats.bad} ro={30} shadow={false} />
        ) : photo ? (
          <ModelBoundary fallback={clay}>
            <Suspense fallback={clay}>
              <PhotoModel url={photo.url} w={w} d={d} h={h} rotY={photo.rotY} register={register} />
            </Suspense>
          </ModelBoundary>
        ) : (
          clay
        )}
        {noFit && !selected && <Frame w={w} h={h} d={d} color={COLORS.nofit} width={1.8} />}
        {noFit && (
          <FitTag
            position={h < 0.1 ? [0, 0.32, d / 2 + 0.25] : [0, Math.max(h + 0.14, 0.95), 0]}
            name={item.name}
            math={failing ? `Does not fit: ${failing}` : 'Does not fit'}
          />
        )}
        {verdict === 'unsure' && !selected && <Frame w={w} h={h} d={d} color={COLORS.unsure} width={1.6} />}
        {translucent && !selected && !noFit && verdict !== 'unsure' && (
          <Frame w={w} h={h} d={d} color={COLORS.bone} width={1.1} opacity={0.6} dashed xray={false} />
        )}
        {hovered && !selected && !noFit && <Frame w={w} h={h} d={d} color={COLORS.bone} width={1.3} opacity={0.75} />}
        {selected && (
          <>
            <Frame w={w} h={h} d={d} color={COLORS.ice} width={1.7} />
            <Callouts w={w} d={d} h={h} dims={item.dims_in} />
          </>
        )}
        <group ref={pulse} visible={false}>
          <Frame w={w} h={h} d={d} color={COLORS.ice} width={2.2} />
        </group>
      </group>
    </group>
  )
}

/** A product the agent rejected, at true size where it would have stood, with the real math. */
export function GhostPiece({ ghost, placement }: { ghost: Ghost; placement: Placement }) {
  const product = productById[ghost.productId]
  const category = product?.category ?? ghost.slot
  const w = ghost.dims.w * IN
  const d = ghost.dims.d * IN
  const h = Math.max(ghost.dims.h ?? 0.5, 0.4) * IN
  const clearGhost = useApp((s) => s.clearGhost)
  const mat = useMemo(
    () => new THREE.MeshBasicMaterial({ color: COLORS.nofit, transparent: true, opacity: 0, depthWrite: false, toneMapped: false }),
    [],
  )
  useEffect(() => () => mat.dispose(), [mat])
  useEffect(() => {
    const id = setTimeout(() => clearGhost(ghost.key), 1800)
    return () => clearTimeout(id)
  }, [ghost.key, clearGhost])

  const g = useRef<THREE.Group>(null)
  const label = useRef<HTMLDivElement>(null)
  const t = useRef(0)
  useFrame((_, dt) => {
    t.current += Math.min(dt, 0.1)
    const a = Math.min(t.current / 0.16, 1) * (1 - Math.min(Math.max((t.current - 1.38) / 0.4, 0), 1))
    mat.opacity = 0.26 * a
    if (label.current) label.current.style.opacity = String(a)
    if (g.current) {
      g.current.traverse((o) => {
        const lm = (o as THREE.Mesh).material as (THREE.Material & { opacity: number; isLineMaterial?: boolean }) | undefined
        if (lm && lm.isLineMaterial) lm.opacity = a * (o.renderOrder === 40 ? 0.5 : 1)
      })
      g.current.position.y = (1 - Math.min(t.current / 0.2, 1)) * 0.12
    }
  })
  const [, math] = splitWhy(ghost.why)
  return (
    <group position={[placement.x_in * IN, 0.004, placement.z_in * IN]} rotation-y={(placement.rotation * Math.PI) / 180}>
      <group ref={g}>
        <Shape category={category} w={w} d={d} h={h} mat={mat} ro={30} shadow={false} />
        <Frame w={w} h={h} d={d} color={COLORS.nofit} width={1.8} />
      </group>
      <FitTag position={[0, Math.max(h + 0.14, 0.95), 0]} name={ghost.name} math={math} opacityRef={label} />
    </group>
  )
}

/** "style #1 of 7 (...); no_fit: rug 79 in + ... > 88 in (user)" -> ["style #1 of 7 (...)", "Does not fit: rug 79 in ..."] */
function splitWhy(why: string): [string, string] {
  const i = why.search(/(no_fit|unsure):/)
  if (i < 0) return ['', why]
  const head = why.slice(0, i).replace(/;\s*$/, '')
  const tail = why
    .slice(i)
    .replace(/^no_fit:\s*/, 'Does not fit: ')
    .replace(/^unsure:\s*/, 'Not sure it fits: ')
  return [head, tail]
}
