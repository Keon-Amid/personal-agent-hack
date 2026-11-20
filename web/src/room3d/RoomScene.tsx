// The 3D room: a box built from the room's measurements, a door, and each item at real size.
// Everything inside <group scale={IN}> is authored in inches.

import { useEffect, useMemo } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { Html, OrbitControls } from '@react-three/drei'
import { Vector3, type PerspectiveCamera } from 'three'
import { Furniture, fmt } from './Furniture'
import { autoLayout } from './layout'
import { useModelManifest } from './Model'
import type { Measurement, RenderItem, Room, Wall } from './types'

const IN = 0.0254 // inches to metres

type Props = {
  room: Room
  items: RenderItem[]
  selected?: string | null // slot to highlight
  onSelect?: (slot: string | null) => void // an item was clicked, or null for empty space
  modelsUrl?: string | null // folder holding index.json and the .glb files; null = simple shapes only
}

export function describe(m: Measurement): string {
  const src = m.source === 'user' ? 'measured' : m.source.replace('estimated:', 'estimated from ')
  return `${fmt(m.value_in)} in${m.error_in > 0 ? ` ± ${fmt(m.error_in)}` : ''} · ${src}`
}

// Pull the camera back until the whole room fits, whatever shape the window is.
// Runs on load and on resize only, so dragging to turn the room still works.
function FitCamera({ radius, targetY }: { radius: number; targetY: number }) {
  const camera = useThree((s) => s.camera) as PerspectiveCamera
  const width = useThree((s) => s.size.width)
  const height = useThree((s) => s.size.height)
  const controls = useThree((s) => s.controls) as { update?: () => void } | null
  useEffect(() => {
    const v = (camera.fov * Math.PI) / 180
    const h = 2 * Math.atan(Math.tan(v / 2) * (width / Math.max(height, 1)))
    const dist = radius / Math.sin(Math.min(v, h) / 2)
    const dir = new Vector3(-0.5, 0.7, 0.9).normalize()
    camera.position.set(dir.x * dist, targetY + dir.y * dist, dir.z * dist)
    camera.lookAt(0, targetY, 0)
    camera.updateProjectionMatrix()
    controls?.update?.()
  }, [camera, controls, width, height, radius, targetY])
  return null
}

function WallPlane({ size, pos, rotY, color }: { size: [number, number]; pos: [number, number, number]; rotY: number; color: string }) {
  // Single-sided on purpose: a wall between the camera and the room is not drawn, so you can always see in.
  return (
    <mesh position={pos} rotation={[0, rotY, 0]} receiveShadow>
      <planeGeometry args={size} />
      <meshStandardMaterial color={color} roughness={0.95} />
    </mesh>
  )
}

function onWall(wall: Wall, W: number, D: number, along: number, y: number, inset: number): { pos: [number, number, number]; rotY: number } {
  switch (wall) {
    case 'back':
      return { pos: [along, y, inset], rotY: 0 }
    case 'left':
      return { pos: [inset, y, along], rotY: Math.PI / 2 }
    case 'right':
      return { pos: [W - inset, y, along], rotY: -Math.PI / 2 }
    case 'front':
      return { pos: [W - along, y, D - inset], rotY: Math.PI }
  }
}

function Label({ pos, children }: { pos: [number, number, number]; children: React.ReactNode }) {
  return (
    <Html position={pos} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
      <div className="dim">{children}</div>
    </Html>
  )
}

export function RoomScene({ room, items, selected = null, onSelect = () => {}, modelsUrl = '/models/' }: Props) {
  const auto = useMemo(() => autoLayout(room, items), [room, items])
  const models = useModelManifest(modelsUrl ? modelsUrl + 'index.json' : null)
  const W = room.wall.value_in
  const D = room.depth.value_in
  const H = room.ceiling_in ?? 96
  const doorWall = room.door_wall ?? 'right'
  const dw = room.door_width.value_in
  const dh = room.door_height.value_in
  const doorAlong = (room.door_offset_in ?? 12) + dw / 2
  const door = onWall(doorWall, W, D, doorAlong, dh / 2, 0.5)
  const doorLabel = onWall(doorWall, W, D, doorAlong, dh + 8, 2)
  const wallColor = '#efece6'

  return (
    <Canvas
      shadows
      camera={{ position: [-W * IN, H * IN * 2, D * IN * 1.5], fov: 42, near: 0.1, far: 100 }}
      onPointerMissed={() => onSelect(null)}
    >
      <FitCamera radius={0.5 * Math.hypot(W, D, H) * IN} targetY={H * IN * 0.3} />
      <color attach="background" args={['#dfe3e8']} />
      <ambientLight intensity={0.85} />
      <hemisphereLight args={['#ffffff', '#b9b2a6', 0.6]} />
      <directionalLight
        position={[2.5, 6, 3.5]}
        intensity={1.5}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-6}
        shadow-camera-right={6}
        shadow-camera-top={6}
        shadow-camera-bottom={-6}
      />
      <OrbitControls
        target={[0, H * IN * 0.3, 0]}
        maxPolarAngle={Math.PI / 2 - 0.04}
        minDistance={1.5}
        maxDistance={30}
        makeDefault
      />

      <group scale={IN} position={[(-W / 2) * IN, 0, (-D / 2) * IN]}>
        {/* floor */}
        <mesh position={[W / 2, 0, D / 2]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[W, D]} />
          <meshStandardMaterial color="#c8ad86" roughness={0.9} />
        </mesh>

        {/* walls, facing inward */}
        <WallPlane size={[W, H]} pos={[W / 2, H / 2, 0]} rotY={0} color={wallColor} />
        <WallPlane size={[D, H]} pos={[0, H / 2, D / 2]} rotY={Math.PI / 2} color="#e7e3db" />
        <WallPlane size={[D, H]} pos={[W, H / 2, D / 2]} rotY={-Math.PI / 2} color="#e7e3db" />
        <WallPlane size={[W, H]} pos={[W / 2, H / 2, D]} rotY={Math.PI} color={wallColor} />

        {/* door */}
        <mesh position={door.pos} rotation={[0, door.rotY, 0]}>
          <planeGeometry args={[dw, dh]} />
          <meshStandardMaterial color="#8b6f55" roughness={0.8} />
        </mesh>
        <Label pos={doorLabel.pos}>
          Door {fmt(dw)} × {fmt(dh)} in
        </Label>

        {/* how far off an estimated measurement may be: the wall could be anywhere inside the band */}
        {room.wall.error_in > 0 && (
          <mesh position={[W, 0.2, D / 2]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[room.wall.error_in * 2, D]} />
            <meshBasicMaterial color="#d99a1c" transparent opacity={0.4} depthWrite={false} />
          </mesh>
        )}
        {room.depth.error_in > 0 && (
          <mesh position={[W / 2, 0.2, D]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[W, room.depth.error_in * 2]} />
            <meshBasicMaterial color="#d99a1c" transparent opacity={0.4} depthWrite={false} />
          </mesh>
        )}

        <Label pos={[W / 2, 0, D + 12]}>Wall {describe(room.wall)}</Label>
        <Label pos={[-12, 0, D / 2]}>Depth {describe(room.depth)}</Label>

        {items.map((it) => (
          <Furniture
            key={it.slot}
            product={it.product}
            fit={it.fit}
            placement={it.placement ?? auto[it.slot]}
            model={modelsUrl ? models[it.product.id] : undefined}
            modelBaseUrl={modelsUrl ?? undefined}
            selected={selected === it.slot}
            onSelect={() => onSelect(it.slot)}
          />
        ))}
      </group>
    </Canvas>
  )
}
