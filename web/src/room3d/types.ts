// Shapes the 3D room view draws. They mirror what the Python side already produces:
// Measurement and FitResult come from fit/checks.py, Candidate from fit/options.py,
// Product from data/products.json. All lengths are inches.

export type Verdict = 'fits' | 'unsure' | 'no_fit'

export type Measurement = { value_in: number; error_in: number; source: string }

export type FitResult = {
  check: string
  verdict: Verdict
  math: string
  need_in?: number
  available?: Measurement
  margin_in?: number
}

export type Product = {
  id: string
  name: string
  category: string
  price_usd: number | null
  dims_in: { w: number; d: number; h: number | null }
  color?: string | null
  image_url?: string | null
  source_url: string
  rating?: number | null
  review_count?: number | null
}

export type Wall = 'back' | 'left' | 'right' | 'front'

// wall = the wall furniture goes against (drawn as the back wall, along x).
// depth = how far the room runs from that wall toward the viewer (along z).
export type Room = {
  wall: Measurement
  depth: Measurement
  door_width: Measurement
  door_height: Measurement
  ceiling_in?: number
  door_wall?: Wall
  door_offset_in?: number // from the start of that wall (back wall: left corner; side walls: back corner)
}

// Centre of the item on the floor. x runs along the back wall from the left corner,
// z runs from the back wall toward the viewer. rotation 0 = the item faces the viewer.
export type Placement = { x_in: number; z_in: number; rotation_deg: 0 | 90 | 180 | 270 }

// What the renderer draws: one product per slot, with its fit verdict.
// product = the catalog entry (data/products.json) for the id the pipeline picked.
// placement is optional: without it the renderer places the item itself (layout.ts).
export type RenderItem = { slot: string; product: Product; fit: Verdict; placement?: Placement }

export type Candidate = {
  product: Product
  fit: Verdict
  fit_results: FitResult[]
  why: string
  best_value?: boolean
}

export type PlanItem = Candidate & {
  slot: string
  placement?: Placement // if the backend sends one it wins; otherwise autoLayout places the item
  others?: Candidate[]
}

export type Plan = {
  about?: string
  generated_at?: string
  generated_by?: string
  stubbed?: string[]
  room: Room
  items: PlanItem[]
}

export const VERDICT_COLOR: Record<Verdict, string> = {
  fits: '#2e9e5b',
  unsure: '#d99a1c',
  no_fit: '#d6453d',
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  fits: 'Fits',
  unsure: 'Unsure',
  no_fit: 'Does not fit',
}
