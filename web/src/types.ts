// Shapes mirror the team's run files exactly: contracts/plan.*.json (brendan's agent), data/products.json and
// fit/ (alistair). See CONTRACT.md. Nothing here is invented by the UI.

export interface Measurement {
  value_in: number
  error_in: number
  source: string // "user" | "scan:lidar" | "estimated:door" | ...
}

export interface Dims {
  w: number
  d: number
  h: number | null
}

export type Verdict = 'fits' | 'unsure' | 'no_fit'
export type MeasureKey = 'wall' | 'depth' | 'door_width' | 'door_height'

export interface PlanRoom {
  wall: Measurement
  depth: Measurement
  door_width: Measurement
  door_height: Measurement
  photo_url: string | null
}

export interface FitResult {
  check: string
  verdict: Verdict
  math: string
  need_in?: number
  available?: Measurement
  margin_in?: number
}

export interface SensoClaim {
  claim: string
  verdict: string // "verified" | "conflict" | "unsupported" | "not_verifiable"
  quote?: string | null
}

export interface Senso {
  check_id: string
  accuracy_pct: number | null
  claims: SensoClaim[]
}

export interface ItemStyle {
  rank: number
  fused: number
  photo_score: number
  text_score: number
  product_styles: string[]
}

export interface Rejected {
  product_id: string
  name: string
  status: string
  why: string
}

export interface PlanItem {
  slot: string
  product_id: string
  name: string
  price_usd: number | null
  dims_in: Dims
  image_url: string
  source_url: string
  style: ItemStyle | null
  why: string
  why_source: { kind: string; [k: string]: unknown } | null
  fit: { verdict: Verdict; results: FitResult[] }
  senso: Senso | null
  rejected: Rejected[]
}

export interface CartItem {
  product_id: string
  name: string
  price_usd: number | null
  source_url: string
}

export interface Cart {
  items: CartItem[]
  total_usd: number
  delivery_note?: string
  no_purchase?: boolean
}

export interface AuditSource {
  kind: string // "template" | "claude" | "superlinked" | "fit" | "senso"
  [k: string]: unknown
}

export interface AuditRecord {
  ts: string
  step: string // estimate_room | agent | rank | pick | senso_check | cart | swap
  decision: string
  why: string
  source: AuditSource
  status?: string
  item_slot?: string
  product_id?: string
  input?: unknown
}

export interface Plan {
  plan_id: string
  plan_url: string
  room: PlanRoom
  style: { style_text: string; detected_style: unknown }
  items: PlanItem[]
  cart: Cart
  audit: AuditRecord[]
}

export interface Product {
  id: string
  retailer: string
  name: string
  article_number: string
  category: string
  price_usd: number | null
  price_note: string | null
  dims_in: Dims
  packages_in: Dims[]
  rating: number | null
  review_count: number | null
  color: string | null
  material: string | null
  description?: string | null
  image_url: string
  image_urls?: string[]
  source_url: string
}

/** One row of fit.options(products, category, room). */
export interface Option {
  id: string
  name: string
  price_usd: number | null
  rating: number | null
  review_count: number
  image_url: string
  source_url: string
  fit: Verdict
  fit_results: FitResult[]
  best_value: boolean
  why: string
}

// ---- The room as the 3D view and the layout see it (inches, floor plane x/z, Y up). ----
// Same shape as fit.scan.load_scan() so a scan parsed in the browser and one parsed in Python agree.

export type Vec2 = [number, number]

export interface RoomWall {
  id: string
  a: Vec2
  b: Vec2
  length_in: number
}

export interface RoomDoor {
  id: string
  wall?: string
  center: Vec2
  width_in: number
  height_in: number
  axis: 'x' | 'z'
  into_room: Vec2
}

export interface RoomExisting {
  id: string
  label: string
  category: string
  x_in: number
  z_in: number
  w_in: number
  d_in: number
  h_in: number
  bottom_in: number
  on_floor: boolean
}

export interface RoomModel {
  /** roomplan = named-object scan (Polycam Floorplan); mesh = raw LiDAR mesh; typed = drawn from typed measurements */
  source: 'roomplan' | 'mesh' | 'typed'
  outline: Vec2[]
  walls: RoomWall[]
  doors: RoomDoor[]
  existing: RoomExisting[]
  height_in: number
}

/** Where the UI stands an item on the floor: centre in inches, rotation in degrees about Y. */
export interface Placement {
  slot: string
  x_in: number
  z_in: number
  rotation: number
}
