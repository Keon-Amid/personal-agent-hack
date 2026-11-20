// Optional per-product 3D models. web/public/models/index.json lists which products have one.
// A model is stretched to the product's listed width x depth x height, so the picture always
// agrees with the numbers the fit checks use. No entry, or a file that fails to load: the caller
// draws its simple shape instead.

import { Component, Suspense, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useGLTF } from '@react-three/drei'
import { Box3, Group, Vector3, type Mesh } from 'three'

export type ModelEntry = {
  file: string // path under the manifest's folder, e.g. "ikea-glostad-...glb"
  source: string // shown to the person, e.g. "AI-generated from the IKEA photo (Hyper3D Rodin)"
  rot_y_deg?: number // turn the raw model so its front faces +z
}
export type ModelManifest = Record<string, ModelEntry>

export function useModelManifest(url: string | null): ModelManifest {
  const [manifest, setManifest] = useState<ModelManifest>({})
  useEffect(() => {
    if (!url) {
      setManifest({})
      return
    }
    let live = true
    fetch(url)
      .then((r) => (r.ok ? r.json() : {}))
      .then((m: unknown) => live && setManifest(m && typeof m === 'object' ? (m as ModelManifest) : {}))
      .catch(() => live && setManifest({}))
    return () => {
      live = false
    }
  }, [url])
  return manifest
}

function Glb({ url, w, d, h, rotY }: { url: string; w: number; d: number; h: number; rotY: number }) {
  const { scene } = useGLTF(url)
  const object = useMemo(() => {
    const root = scene.clone(true)
    root.rotation.set(0, rotY, 0)
    root.updateMatrixWorld(true)
    const box = new Box3().setFromObject(root)
    const size = box.getSize(new Vector3())
    const centre = box.getCenter(new Vector3())
    root.position.set(-centre.x, -box.min.y, -centre.z) // centred on the floor
    root.traverse((o) => {
      if ((o as Mesh).isMesh) {
        o.castShadow = true
        o.receiveShadow = true
      }
    })
    const holder = new Group()
    holder.add(root)
    holder.scale.set(w / (size.x || 1), h / (size.y || 1), d / (size.z || 1)) // exact listed size
    return holder
  }, [scene, w, d, h, rotY])
  return <primitive object={object} />
}

class Fallback extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

type Props = { baseUrl: string; entry: ModelEntry; w: number; d: number; h: number; fallback: ReactNode }

export function ProductModel({ baseUrl, entry, w, d, h, fallback }: Props) {
  return (
    <Fallback fallback={fallback}>
      <Suspense fallback={fallback}>
        <Glb url={baseUrl + entry.file} w={w} d={d} h={h} rotY={((entry.rot_y_deg ?? 0) * Math.PI) / 180} />
      </Suspense>
    </Fallback>
  )
}
