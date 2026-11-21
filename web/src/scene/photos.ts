// Turn a product's IKEA photo into something the 3D room can use.
// IKEA serves its product photos with CORS for this origin, so a canvas can read the pixels.
//   rugTexture(url): the rug itself, cropped out of its white studio background, as a texture for the rug's top.
//   cutout(url):     the product with its white background removed, for pieces that have no 3D model (lamps).
import * as THREE from 'three'

export interface Cutout {
  texture: THREE.Texture
  /** width / height of the cropped product */
  aspect: number
}

const images = new Map<string, Promise<HTMLImageElement>>()
const rugs = new Map<string, Promise<THREE.Texture | null>>()
const cutouts = new Map<string, Promise<Cutout | null>>()

function loadImage(url: string): Promise<HTMLImageElement> {
  let p = images.get(url)
  if (!p) {
    p = new Promise((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.decoding = 'async'
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error(`could not load ${url}`))
      img.src = url
    })
    images.set(url, p)
  }
  return p
}

/** The product photo IKEA lists for the item, fetched through the dev server so its pixels are readable. */
const loadBest = (url: string) => loadImage(url.replace(/^https:\/\/www\.ikea\.com\//, '/ikea-img/'))

function pixels(img: HTMLImageElement, maxSide = 1024) {
  const s = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight))
  const w = Math.max(1, Math.round(img.naturalWidth * s))
  const h = Math.max(1, Math.round(img.naturalHeight * s))
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  ctx.drawImage(img, 0, 0, w, h)
  return { canvas, ctx, w, h, data: ctx.getImageData(0, 0, w, h) }
}

/** Studio white: bright and nearly grey. */
const isBackdrop = (d: Uint8ClampedArray, i: number, tol: number) => {
  const r = d[i]
  const g = d[i + 1]
  const b = d[i + 2]
  return r > 255 - tol && g > 255 - tol && b > 255 - tol && Math.max(r, g, b) - Math.min(r, g, b) < 14
}

/** Mark the white background that touches the photo's edges (flood fill), so white parts of the product stay. */
function backdropMask(d: Uint8ClampedArray, w: number, h: number, tol: number): Uint8Array {
  const mask = new Uint8Array(w * h)
  const stack: number[] = []
  const push = (x: number, y: number) => {
    const k = y * w + x
    if (mask[k] || !isBackdrop(d, k * 4, tol)) return
    mask[k] = 1
    stack.push(k)
  }
  for (let x = 0; x < w; x++) {
    push(x, 0)
    push(x, h - 1)
  }
  for (let y = 0; y < h; y++) {
    push(0, y)
    push(w - 1, y)
  }
  while (stack.length) {
    const k = stack.pop()!
    const x = k % w
    const y = (k - x) / w
    if (x > 0) push(x - 1, y)
    if (x < w - 1) push(x + 1, y)
    if (y > 0) push(x, y - 1)
    if (y < h - 1) push(x, y + 1)
  }
  return mask
}

function bounds(mask: Uint8Array, w: number, h: number) {
  let x0 = w
  let y0 = h
  let x1 = -1
  let y1 = -1
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++)
      if (!mask[y * w + x]) {
        if (x < x0) x0 = x
        if (x > x1) x1 = x
        if (y < y0) y0 = y
        if (y > y1) y1 = y
      }
  return x1 < 0 ? null : { x0, y0, x1, y1 }
}

function crop(src: HTMLCanvasElement, b: { x0: number; y0: number; x1: number; y1: number }, inset = 0) {
  const w = b.x1 - b.x0 + 1 - 2 * inset
  const h = b.y1 - b.y0 + 1 - 2 * inset
  const c = document.createElement('canvas')
  c.width = Math.max(1, w)
  c.height = Math.max(1, h)
  c.getContext('2d')!.drawImage(src, b.x0 + inset, b.y0 + inset, w, h, 0, 0, w, h)
  return c
}

function toTexture(c: HTMLCanvasElement): THREE.Texture {
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  t.needsUpdate = true
  return t
}

/**
 * The rug cropped out of its photo, for the rug's top face. rugW/rugD are the rug's size in the room
 * (x and z): if the photo is landscape and the rug runs the other way, the texture is turned a quarter.
 */
export function rugTexture(url: string, rugW: number, rugD: number): Promise<THREE.Texture | null> {
  const key = `${url}|${rugW > rugD ? 'wide' : 'deep'}`
  let p = rugs.get(key)
  if (!p) {
    p = (async () => {
      try {
        const img = await loadBest(url)
        const { canvas, data, w, h } = pixels(img)
        const b = bounds(backdropMask(data.data, w, h, 18), w, h)
        if (!b) return null
        // trim a few pixels so the soft photo edge and shadow don't read as a border
        const c = crop(canvas, b, Math.round(Math.min(b.x1 - b.x0, b.y1 - b.y0) * 0.02))
        const t = toTexture(c)
        const photoWide = c.width > c.height
        if (photoWide !== rugW > rugD && Math.abs(c.width - c.height) > 0.08 * Math.max(c.width, c.height)) {
          t.center.set(0.5, 0.5)
          t.rotation = Math.PI / 2
        }
        return t
      } catch {
        return null
      }
    })()
    rugs.set(key, p)
  }
  return p
}

/** The product with its white backdrop made transparent and cropped tight, for an upright photo in the room. */
export function cutout(url: string): Promise<Cutout | null> {
  let p = cutouts.get(url)
  if (!p) {
    p = (async () => {
      try {
        const img = await loadBest(url)
        const { canvas, ctx, data, w, h } = pixels(img)
        const mask = backdropMask(data.data, w, h, 10)
        const d = data.data
        for (let k = 0; k < w * h; k++) if (mask[k]) d[k * 4 + 3] = 0
        ctx.putImageData(data, 0, 0)
        const b = bounds(mask, w, h)
        if (!b) return null
        const c = crop(canvas, b)
        return { texture: toTexture(c), aspect: c.width / c.height }
      } catch {
        return null
      }
    })()
    cutouts.set(url, p)
  }
  return p
}
