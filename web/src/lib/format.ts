import clsx, { type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...v: ClassValue[]) => twMerge(clsx(v))

/** 89.75 -> "89.75", 88 -> "88", 37.375 -> "37.38" */
export const inches = (v: number | null | undefined, digits = 2): string => {
  if (v === null || v === undefined || Number.isNaN(v)) return '?'
  const s = v.toFixed(digits)
  return s.includes('.') ? s.replace(/0+$/, '').replace(/\.$/, '') : s
}

export const usd = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return 'No price listed'
  const whole = Number.isInteger(v)
  return v.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: whole ? 0 : 2,
    maximumFractionDigits: 2,
  })
}

/** "KIVIK Sofa - Tibbleby beige/gray" -> ["KIVIK", "Sofa, Tibbleby beige/gray"] */
export const splitName = (name: string): [string, string] => {
  const m = name.match(/^([A-ZÅÄÖÉØÆÜ0-9][A-ZÅÄÖÉØÆÜ0-9\- ]*?)\s+(.*)$/)
  if (!m) return [name, '']
  return [m[1], m[2].replace(/\s+-\s+/, ', ')]
}

export const slotLabel = (slot: string): string => {
  const s = slot.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export const clock = (ts: string): string => {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/** Seconds between the first record of a run and this one, as "+0:42". */
export const sinceStart = (ts: string, start: string): string => {
  const s = Math.max(0, Math.round((Date.parse(ts) - Date.parse(start)) / 1000))
  return `+${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export const verdictLabel: Record<string, string> = {
  fits: 'Fits',
  unsure: 'Measure to be sure',
  no_fit: 'Does not fit',
}

export const checkLabel: Record<string, string> = {
  wall: 'Against the wall',
  floor: 'Walkway in front',
  doorway_width: 'Box through the door, width',
  doorway_height: 'Box through the door, height',
  rug_width: 'Rug across the room',
  rug_depth: 'Rug along the room',
  in_room: 'Inside the walls',
  overlap: 'Clear of other furniture',
  door_swing: 'Clear of the door swing',
  clearance: 'Room to reach it',
}
