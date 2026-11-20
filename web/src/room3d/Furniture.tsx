// One piece of furniture, drawn as a simple shape per category inside a box of the product's
// real width x depth x height. The outline colour is the fit verdict.

import { useState } from 'react'
import { Edges, Html } from '@react-three/drei'
import { Color } from 'three'
import { ProductModel, type ModelEntry } from './Model'
import type { Placement, Product, Verdict } from './types'
import { VERDICT_COLOR, VERDICT_LABEL } from './types'

const COLOR_WORDS: Record<string, string> = {
  gray: '#8f9399', grey: '#8f9399', beige: '#cdbfa6', black: '#2f2f33', white: '#e9e7e1',
  brown: '#7b5b42', green: '#5f8060', blue: '#4f6f9c', red: '#a8483f', yellow: '#d6b656',
  multicolor: '#9a7fa6',
}
const CATEGORY_COLOR: Record<string, string> = {
  sofa: '#8f9399', armchair: '#b9a58a', coffee_table: '#8a6a4d', side_table: '#cbbfa8',
  rug: '#9aa7b0', floor_lamp: '#3a3a3d', tv_bench: '#4a4a4f', bookcase: '#e2ded5',
  dresser: '#d8d2c6', nightstand: '#d8d2c6', desk: '#b99b78', dining_table: '#a27e58',
  dining_chair: '#a27e58', bed: '#c9c2b6',
}

function baseColor(p: Product): string {
  for (const word of (p.color ?? '').toLowerCase().split(/[\s,]+/)) {
    if (COLOR_WORDS[word]) return COLOR_WORDS[word]
  }
  return CATEGORY_COLOR[p.category] ?? '#a9a39a'
}

function shade(hex: string, lightness: number): string {
  return '#' + new Color(hex).offsetHSL(0, 0, lightness).getHexString()
}

export function fmt(n: number | null | undefined): string {
  return n == null ? '–' : String(Math.round(n * 10) / 10)
}

type V3 = [number, number, number]

function Part({ size, pos, color }: { size: V3; pos: V3; color: string }) {
  return (
    <mesh position={pos} castShadow receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} roughness={0.85} />
    </mesh>
  )
}

function Legs({ w, d, h, t, color }: { w: number; d: number; h: number; t: number; color: string }) {
  const x = w / 2 - t / 2 - Math.min(1, w * 0.04)
  const z = d / 2 - t / 2 - Math.min(1, d * 0.04)
  return (
    <>
      {[[x, z], [-x, z], [x, -z], [-x, -z]].map(([lx, lz], i) => (
        <Part key={i} size={[t, h, t]} pos={[lx, h / 2, lz]} color={color} />
      ))}
    </>
  )
}

// Local axes: x = width, z = depth (the front faces +z), y = up from the floor.
function Shape({ category, w, d, h, color }: { category: string; w: number; d: number; h: number; color: string }) {
  const dark = shade(color, -0.1)
  const light = shade(color, 0.07)
  switch (category) {
    case 'sofa':
    case 'armchair': {
      const arm = Math.min(w * 0.13, 9)
      const back = Math.min(d * 0.26, 9)
      return (
        <>
          <Part size={[w, h * 0.42, d]} pos={[0, h * 0.21, 0]} color={dark} />
          <Part size={[w, h, back]} pos={[0, h / 2, -d / 2 + back / 2]} color={color} />
          <Part size={[arm, h * 0.68, d]} pos={[w / 2 - arm / 2, h * 0.34, 0]} color={color} />
          <Part size={[arm, h * 0.68, d]} pos={[-w / 2 + arm / 2, h * 0.34, 0]} color={color} />
          <Part size={[w - 2 * arm, h * 0.14, d - back]} pos={[0, h * 0.49, back / 2]} color={light} />
        </>
      )
    }
    case 'coffee_table':
    case 'side_table':
    case 'dining_table':
    case 'desk': {
      const top = Math.max(1.2, Math.min(2.5, h * 0.1))
      const leg = Math.max(1.2, Math.min(2.5, Math.min(w, d) * 0.08))
      return (
        <>
          <Part size={[w, top, d]} pos={[0, h - top / 2, 0]} color={color} />
          <Legs w={w} d={d} h={h - top} t={leg} color={dark} />
        </>
      )
    }
    case 'dining_chair': {
      const seat = h * 0.47
      return (
        <>
          <Part size={[w, 2, d]} pos={[0, seat, 0]} color={color} />
          <Legs w={w} d={d} h={seat - 1} t={1.5} color={dark} />
          <Part size={[w, h - seat, 1.5]} pos={[0, seat + (h - seat) / 2, -d / 2 + 0.75]} color={color} />
        </>
      )
    }
    case 'rug':
      return (
        <mesh position={[0, h / 2, 0]} receiveShadow>
          <boxGeometry args={[w, h, d]} />
          <meshStandardMaterial color={color} roughness={1} />
        </mesh>
      )
    case 'floor_lamp': {
      const r = Math.min(w, d) / 2
      return (
        <>
          <mesh position={[0, 0.6, 0]} castShadow>
            <cylinderGeometry args={[r * 0.8, r * 0.8, 1.2, 24]} />
            <meshStandardMaterial color="#3a3a3d" />
          </mesh>
          <mesh position={[0, h * 0.42, 0]} castShadow>
            <cylinderGeometry args={[0.6, 0.6, h * 0.84, 12]} />
            <meshStandardMaterial color="#3a3a3d" />
          </mesh>
          <mesh position={[0, h * 0.91, 0]} castShadow>
            <cylinderGeometry args={[r * 0.6, r, h * 0.18, 24]} />
            <meshStandardMaterial color="#f1e3b0" emissive="#f1e3b0" emissiveIntensity={0.35} />
          </mesh>
        </>
      )
    }
    case 'bed':
      return (
        <>
          <Part size={[w, h * 0.3, d]} pos={[0, h * 0.15, 0]} color={dark} />
          <Part size={[w - 2, h * 0.16, d - 4]} pos={[0, h * 0.38, 1]} color={light} />
          <Part size={[w, h, 3]} pos={[0, h / 2, -d / 2 + 1.5]} color={color} />
        </>
      )
    default: // storage and anything unknown: a solid box
      return (
        <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
          <boxGeometry args={[w, h, d]} />
          <meshStandardMaterial color={color} roughness={0.8} />
          <Edges color={dark} />
        </mesh>
      )
  }
}

type Props = {
  product: Product
  fit: Verdict
  placement: Placement
  selected: boolean
  onSelect: () => void
  model?: ModelEntry // a per-product 3D model, if one exists
  modelBaseUrl?: string
}

export function Furniture({ product, fit, placement, selected, onSelect, model, modelBaseUrl = '/models/' }: Props) {
  const [hover, setHover] = useState(false)
  const { w, d } = product.dims_in
  const h = product.dims_in.h ?? 0.5 // a rug with no listed pile height is drawn 0.5 in thick
  const verdictColor = VERDICT_COLOR[fit]
  const lift = product.category === 'rug' ? 0.05 : 0.08
  return (
    <group
      position={[placement.x_in, lift, placement.z_in]}
      rotation={[0, (placement.rotation_deg * Math.PI) / 180, 0]}
      onClick={(e) => {
        e.stopPropagation()
        onSelect()
      }}
      onPointerOver={(e) => {
        e.stopPropagation()
        setHover(true)
        document.body.style.cursor = 'pointer'
      }}
      onPointerOut={() => {
        setHover(false)
        document.body.style.cursor = ''
      }}
    >
      {model ? (
        <ProductModel
          baseUrl={modelBaseUrl}
          entry={model}
          w={w}
          d={d}
          h={h}
          fallback={<Shape category={product.category} w={w} d={d} h={h} color={baseColor(product)} />}
        />
      ) : (
        <Shape category={product.category} w={w} d={d} h={h} color={baseColor(product)} />
      )}

      {/* The real bounding box, outlined in the verdict colour. */}
      <mesh position={[0, Math.max(h, 1) / 2, 0]}>
        <boxGeometry args={[w + 0.4, Math.max(h, 1) + 0.4, d + 0.4]} />
        <meshBasicMaterial
          color={verdictColor}
          transparent
          opacity={selected ? 0.16 : fit === 'fits' ? 0 : 0.1}
          depthWrite={false}
        />
        <Edges color={verdictColor} />
      </mesh>

      {/* The 36 in walkway the floor check keeps clear in front of the item. */}
      {selected && product.category !== 'rug' && (
        <mesh position={[0, 0.25, d / 2 + 18]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[w, 36]} />
          <meshBasicMaterial color="#3d7bd9" transparent opacity={0.18} depthWrite={false} />
        </mesh>
      )}

      {/* Always mounted and only hidden, so hovering does not mount and unmount a label each time. */}
      <Html position={[0, h + 9, 0]} center zIndexRange={[20, 0]} style={{ pointerEvents: 'none' }}>
        <div className="tag" style={{ display: hover || selected ? 'flex' : 'none' }}>
          <b>{product.name.split(' - ')[0]}</b>
          <span>
            {fmt(w)} × {fmt(d)} × {fmt(product.dims_in.h)} in
          </span>
          <span className="tag-verdict" style={{ color: verdictColor }}>
            {VERDICT_LABEL[fit]}
          </span>
          {model && <span className="tag-source">{model.source}, scaled to listed size</span>}
        </div>
      </Html>
    </group>
  )
}
