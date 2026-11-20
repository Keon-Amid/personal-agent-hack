// Clay furniture built from primitives. Every shape fills exactly its real W x D x H box:
// x in [-w/2, w/2], y in [0, h], z in [-d/2, d/2], front facing +z. Units are metres.
import { RoundedBox } from '@react-three/drei'
import type * as THREE from 'three'

interface P {
  w: number
  d: number
  h: number
  mat: THREE.Material
  /** a slightly darker companion material for plinths, rug borders, legs */
  dark?: THREE.Material
  ro?: number
  shadow?: boolean
}
type V3 = [number, number, number]

function B({ s, p, r = 0.03, mat, ro, shadow = true }: { s: V3; p: V3; r?: number; mat: THREE.Material; ro?: number; shadow?: boolean }) {
  const rr = Math.min(r, Math.min(s[0], s[1], s[2]) * 0.32)
  if (rr < 0.005)
    return (
      <mesh position={p} material={mat} renderOrder={ro} castShadow={shadow} receiveShadow>
        <boxGeometry args={s} />
      </mesh>
    )
  return (
    <RoundedBox args={s} radius={rr} smoothness={3} position={p} material={mat} renderOrder={ro} castShadow={shadow} receiveShadow />
  )
}

function Seat({ w, d, h, mat, ro, shadow, cushions }: P & { cushions: number }) {
  const aw = Math.min(0.2, w * 0.13)
  const bd = Math.min(0.26, d * 0.28)
  const sh = Math.min(0.44, h * 0.56)
  const ah = Math.min(h * 0.82, sh + 0.2)
  const inner = w - 2 * aw
  const cush = Math.min(0.14, sh * 0.34)
  const cw = inner / cushions
  return (
    <group>
      <B s={[inner, sh - cush, d - bd]} p={[0, (sh - cush) / 2, bd / 2]} mat={mat} ro={ro} shadow={shadow} />
      {Array.from({ length: cushions }, (_, i) => (
        <B
          key={i}
          s={[cw - 0.012, cush, d - bd - 0.02]}
          p={[-inner / 2 + cw * (i + 0.5), sh - cush / 2, bd / 2 + 0.01]}
          r={0.045}
          mat={mat}
          ro={ro}
          shadow={shadow}
        />
      ))}
      <B s={[inner, h, bd]} p={[0, h / 2, -d / 2 + bd / 2]} r={0.05} mat={mat} ro={ro} shadow={shadow} />
      <B s={[aw, ah, d]} p={[-w / 2 + aw / 2, ah / 2, 0]} r={0.05} mat={mat} ro={ro} shadow={shadow} />
      <B s={[aw, ah, d]} p={[w / 2 - aw / 2, ah / 2, 0]} r={0.05} mat={mat} ro={ro} shadow={shadow} />
    </group>
  )
}

function Table({ w, d, h, mat, ro, shadow, round }: P & { round: boolean }) {
  const tt = Math.min(0.05, h * 0.14)
  const leg = Math.min(0.05, Math.min(w, d) * 0.09)
  if (round) {
    const r = Math.min(w, d) / 2
    const k = r * 0.62
    return (
      <group scale={[w / (2 * r), 1, d / (2 * r)]}>
        <mesh position={[0, h - tt / 2, 0]} material={mat} renderOrder={ro} castShadow={shadow} receiveShadow>
          <cylinderGeometry args={[r, r, tt, 48]} />
        </mesh>
        {[0, 1, 2].map((i) => {
          const a = (i / 3) * Math.PI * 2 + Math.PI / 6
          return (
            <mesh key={i} position={[Math.cos(a) * k, (h - tt) / 2, Math.sin(a) * k]} material={mat} renderOrder={ro} castShadow={shadow}>
              <cylinderGeometry args={[leg / 2, leg / 2.4, h - tt, 12]} />
            </mesh>
          )
        })}
      </group>
    )
  }
  const ix = w / 2 - leg / 2 - 0.015
  const iz = d / 2 - leg / 2 - 0.015
  return (
    <group>
      <B s={[w, tt, d]} p={[0, h - tt / 2, 0]} r={0.012} mat={mat} ro={ro} shadow={shadow} />
      {[
        [ix, iz],
        [-ix, iz],
        [ix, -iz],
        [-ix, -iz],
      ].map(([x, z], i) => (
        <B key={i} s={[leg, h - tt, leg]} p={[x, (h - tt) / 2, z]} r={0.006} mat={mat} ro={ro} shadow={shadow} />
      ))}
    </group>
  )
}

function Rug({ w, d, h, mat, dark, ro }: P) {
  const t = Math.max(h, 0.012)
  const b = Math.min(0.09, Math.min(w, d) * 0.06)
  return (
    <group>
      <mesh position={[0, t / 2, 0]} material={dark ?? mat} renderOrder={ro} receiveShadow>
        <boxGeometry args={[w, t, d]} />
      </mesh>
      <mesh position={[0, t + 0.0015, 0]} rotation-x={-Math.PI / 2} material={mat} renderOrder={ro} receiveShadow>
        <planeGeometry args={[w - 2 * b, d - 2 * b]} />
      </mesh>
    </group>
  )
}

function Lamp({ w, d, h, mat, dark, ro, shadow }: P) {
  const r = Math.min(w, d) / 2
  const sh = Math.min(0.3, h * 0.2)
  return (
    <group scale={[w / (2 * r), 1, d / (2 * r)]}>
      <mesh position={[0, 0.0125, 0]} material={dark ?? mat} renderOrder={ro} castShadow={shadow} receiveShadow>
        <cylinderGeometry args={[r * 0.72, r * 0.78, 0.025, 36]} />
      </mesh>
      <mesh position={[0, (h - sh) / 2, 0]} material={dark ?? mat} renderOrder={ro} castShadow={shadow}>
        <cylinderGeometry args={[0.011, 0.011, h - sh, 10]} />
      </mesh>
      <mesh position={[0, h - sh / 2, 0]} material={mat} renderOrder={ro} castShadow={shadow}>
        <cylinderGeometry args={[r * 0.74, r, sh, 40]} />
      </mesh>
    </group>
  )
}

function Carcass({ w, d, h, mat, dark, ro, shadow, shelves }: P & { shelves: boolean }) {
  const pl = Math.min(0.06, h * 0.08)
  if (shelves) {
    const t = 0.022
    const n = Math.max(2, Math.round(h / 0.36))
    return (
      <group>
        <B s={[t, h, d]} p={[-w / 2 + t / 2, h / 2, 0]} r={0.004} mat={mat} ro={ro} shadow={shadow} />
        <B s={[t, h, d]} p={[w / 2 - t / 2, h / 2, 0]} r={0.004} mat={mat} ro={ro} shadow={shadow} />
        <B s={[w - 2 * t, h, 0.008]} p={[0, h / 2, -d / 2 + 0.004]} r={0} mat={dark ?? mat} ro={ro} shadow={shadow} />
        {Array.from({ length: n + 1 }, (_, i) => (
          <B key={i} s={[w - 2 * t, t, d - 0.01]} p={[0, pl + ((h - pl - t) * i) / n + t / 2, 0.005]} r={0} mat={mat} ro={ro} shadow={shadow} />
        ))}
      </group>
    )
  }
  return (
    <group>
      <B s={[w - 0.05, pl, d - 0.05]} p={[0, pl / 2, 0]} r={0} mat={dark ?? mat} ro={ro} shadow={shadow} />
      <B s={[w, h - pl, d]} p={[0, pl + (h - pl) / 2, 0]} r={0.014} mat={mat} ro={ro} shadow={shadow} />
    </group>
  )
}

function Bed({ w, d, h, mat, dark, ro, shadow }: P) {
  const base = Math.min(0.28, h * 0.3)
  const mt = Math.min(0.22, h * 0.24)
  const hb = 0.07
  return (
    <group>
      <B s={[w, base, d - hb]} p={[0, base / 2, hb / 2]} r={0.02} mat={dark ?? mat} ro={ro} shadow={shadow} />
      <B s={[w - 0.05, mt, d - hb - 0.05]} p={[0, base + mt / 2, hb / 2]} r={0.06} mat={mat} ro={ro} shadow={shadow} />
      <B s={[w, h, hb]} p={[0, h / 2, -d / 2 + hb / 2]} r={0.02} mat={mat} ro={ro} shadow={shadow} />
      {[-1, 1].map((s) => (
        <B key={s} s={[w * 0.4, 0.11, 0.38]} p={[s * w * 0.23, base + mt + 0.05, -d / 2 + hb + 0.26]} r={0.05} mat={mat} ro={ro} shadow={shadow} />
      ))}
    </group>
  )
}

function Chair({ w, d, h, mat, ro, shadow }: P) {
  const sh = Math.min(0.46, h * 0.5)
  const t = 0.04
  const leg = 0.035
  const ix = w / 2 - leg / 2
  const iz = d / 2 - leg / 2
  return (
    <group>
      <B s={[w, t, d]} p={[0, sh - t / 2, 0]} r={0.012} mat={mat} ro={ro} shadow={shadow} />
      <B s={[w, h - sh, t]} p={[0, sh + (h - sh) / 2, -d / 2 + t / 2]} r={0.012} mat={mat} ro={ro} shadow={shadow} />
      {[
        [ix, iz],
        [-ix, iz],
        [ix, -iz],
        [-ix, -iz],
      ].map(([x, z], i) => (
        <B key={i} s={[leg, sh - t, leg]} p={[x, (sh - t) / 2, z]} r={0.005} mat={mat} ro={ro} shadow={shadow} />
      ))}
    </group>
  )
}

export function Shape({ category, ...p }: P & { category: string }) {
  switch (category) {
    case 'sofa':
      return <Seat {...p} cushions={p.w > 1.95 ? 3 : 2} />
    case 'armchair':
      return <Seat {...p} cushions={1} />
    case 'coffee_table':
    case 'side_table':
    case 'dining_table':
      return <Table {...p} round={Math.abs(p.w - p.d) < 0.03} />
    case 'desk':
    case 'table':
      return <Table {...p} round={false} />
    case 'rug':
      return <Rug {...p} />
    case 'floor_lamp':
      return <Lamp {...p} />
    case 'bookcase':
      return <Carcass {...p} shelves />
    case 'tv_bench':
    case 'dresser':
    case 'nightstand':
    case 'storage':
      return <Carcass {...p} shelves={false} />
    case 'bed':
      return <Bed {...p} />
    case 'dining_chair':
    case 'desk_chair':
      return <Chair {...p} />
    default:
      return <B s={[p.w, p.h, p.d]} p={[0, p.h / 2, 0]} mat={p.mat} ro={p.ro} shadow={p.shadow} />
  }
}
