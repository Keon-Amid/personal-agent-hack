import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Armchair, Box, ShoppingBag } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { API_MODE } from '../api/api'
import { demoRoomForPlan } from '../data'
import { cn, inches, usd } from '../lib/format'
import { useApp, type CameraPreset, type ExistingMode } from '../store'
import type { MeasureKey, Measurement } from '../types'
import { cancelRun } from '../run'
import { Kbd, Ticker } from './bits'
import { Tip } from './tooltip'

export function Wordmark({ className }: { className?: string }) {
  return (
    <span translate="no" className={cn('inline-flex items-center gap-2 text-base font-semibold tracking-[-0.01em] text-fg', className)}>
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
        <path d="M3.5 15V3.5H15M3.5 9.25h8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" />
      </svg>
      Fits
    </span>
  )
}

const sourceWords = (m: Measurement, overridden: boolean) => {
  if (overridden) return 'you measured'
  if (m.source === 'user') return 'typed in'
  if (m.source.startsWith('scan')) return 'from the scan'
  if (m.source.startsWith('estimated')) return 'estimated'
  return m.source
}

const measureLabel: Record<MeasureKey, string> = {
  wall: 'Wall',
  depth: 'Depth',
  door_width: 'Door width',
  door_height: 'Door height',
}

function Measure({ k, m }: { k: MeasureKey; m: Measurement }) {
  const measuring = useApp((s) => s.measuring)
  const override = useApp((s) => s.overrides[k])
  const setMeasuring = useApp((s) => s.setMeasuring)
  const setOverride = useApp((s) => s.setOverride)
  const open = measuring === k
  const value = override ?? m.value_in
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  // Open with an empty field: the number to type is the one on the tape, not an edit of the old one.
  useEffect(() => {
    if (!open) return
    setDraft('')
    const t = setTimeout(() => inputRef.current?.focus(), 30)
    return () => clearTimeout(t)
  }, [open])
  const parsed = Number.parseFloat(draft)
  const valid = Number.isFinite(parsed) && parsed > 0 && parsed < 2000

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setMeasuring(open ? null : k)}
        aria-expanded={open}
        title={`${measureLabel[k]}: ${sourceWords(m, override !== undefined)}. Click to enter your own measurement.`}
        className={cn(
          'flex h-7 items-center gap-1.5 rounded-sm px-2 text-xs transition-colors duration-150',
          open ? 'bg-ice/12 text-fg ring-1 ring-inset ring-ice/50' : 'text-fg-2 hover:bg-white/6 hover:text-fg',
        )}
      >
        <span>{measureLabel[k]}</span>
        <span className="num text-fg">
          {inches(value)}
          {m.error_in > 0 && override === undefined && <span className="text-unsure"> ±{inches(m.error_in)}</span>}
          <span className="text-fg-3"> in</span>
        </span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.form
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
            onSubmit={(e) => {
              e.preventDefault()
              if (valid) setOverride(k, parsed)
            }}
            className="glass-solid absolute left-0 top-9 z-30 w-[264px] origin-top-left rounded-md p-3"
          >
            <label htmlFor={`measure-${k}`} className="block text-sm font-medium text-fg">
              Measure the {measureLabel[k].toLowerCase()}
            </label>
            <p className="mt-1 text-xs leading-relaxed text-fg-2">
              The agent used <span className="num text-fg">{inches(m.value_in)} in</span>, {sourceWords(m, false)}. A tape
              measure beats an estimate.
            </p>
            <div className="mt-2.5 flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  id={`measure-${k}`}
                  ref={inputRef}
                  name={`measure-${k}`}
                  // The popover exists to take one number; desktop only, one field.
                  autoFocus
                  inputMode="decimal"
                  autoComplete="off"
                  value={draft}
                  placeholder={inches(value)}
                  onChange={(e) => setDraft(e.target.value)}
                  className="field num w-full pr-8"
                />
                <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-fg-3">in</span>
              </div>
              <button type="submit" disabled={!valid} className="btn btn-primary">
                Use it
              </button>
            </div>
            {override !== undefined && (
              <button type="button" onClick={() => setOverride(k, null)} className="mt-2 text-xs text-fg-2 underline hover:text-fg">
                Go back to {inches(m.value_in)} in
              </button>
            )}
          </motion.form>
        )}
      </AnimatePresence>
    </div>
  )
}

const cams: { id: CameraPreset; label: string; key: string }[] = [
  { id: 'iso', label: 'Angle', key: '1' },
  { id: 'top', label: 'Plan', key: '2' },
  { id: 'front', label: 'Front', key: '3' },
]

export default function TopBar() {
  const navigate = useNavigate()
  const plan = useApp((s) => s.plan)
  const stage = useApp((s) => s.stage)
  const camera = useApp((s) => s.camera)
  const setCamera = useApp((s) => s.setCamera)
  const room = useApp((s) => s.room)
  const existing = useApp((s) => s.existing)
  const setExisting = useApp((s) => s.setExisting)
  const cartOpen = useApp((s) => s.cartOpen)
  const setCartOpen = useApp((s) => s.setCartOpen)
  const placed = useApp((s) => s.placed)
  const modelLabel = useApp((s) => s.modelLabel)
  const modelStyle = useApp((s) => s.modelStyle)
  const setModelStyle = useApp((s) => s.setModelStyle)
  if (!plan) return null
  const demo = demoRoomForPlan(plan.plan_id)
  const inCart = plan.items.filter((i) => placed[i.slot] === 'in_cart' || (stage === 'done' && placed[i.slot]))
  const total = inCart.reduce((sum, i) => sum + (i.price_usd ?? 0), 0)
  const floorItems = room?.existing.filter((e) => e.on_floor).length ?? 0
  const nextExisting: Record<ExistingMode, ExistingMode> = { show: 'ghost', ghost: 'hidden', hidden: 'show' }
  const existingWords: Record<ExistingMode, string> = {
    show: 'Existing furniture shown',
    ghost: 'Existing furniture faded',
    hidden: 'Existing furniture hidden',
  }

  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-3 p-3">
      <div className="glass pointer-events-auto flex h-10 items-center gap-1 rounded-md pl-3 pr-1.5">
        <button
          type="button"
          onClick={() => {
            cancelRun()
            useApp.getState().reset()
            navigate('/')
          }}
          title="Back to rooms"
          className="-ml-1 rounded-sm px-1 py-1 hover:bg-white/6"
        >
          <Wordmark />
        </button>
        <span className="mx-2 h-4 w-px bg-line-2" aria-hidden />
        <div className="mr-1 flex items-baseline gap-2 whitespace-nowrap">
          <span className="text-sm font-medium text-fg">{demo?.title ?? modelLabel ?? 'Your room'}</span>
          <span className="text-xs text-fg-3">{demo?.note ?? 'Your scan'}</span>
        </div>
        <span className="mx-1 h-4 w-px bg-line-2" aria-hidden />
        <Measure k="wall" m={plan.room.wall} />
        <Measure k="depth" m={plan.room.depth} />
        <Measure k="door_width" m={plan.room.door_width} />
      </div>

      <div className="pointer-events-auto flex items-center gap-2">
        {API_MODE === 'mock' && (
          <span
            className="glass flex h-10 items-center gap-2 rounded-md px-3 text-xs text-fg-2"
            title="This screen replays an agent run the team recorded today. The records, numbers and checks are real; only the waiting is shortened."
          >
            <span className="h-1.5 w-1.5 rounded-full bg-unsure" aria-hidden />
            Replay of a real run
          </span>
        )}
        <div className="glass flex h-10 items-center gap-0.5 rounded-md p-1" role="group" aria-label="Camera view">
          {cams.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setCamera(c.id)}
              aria-pressed={camera === c.id}
              className={cn(
                'flex h-8 items-center gap-1.5 rounded-sm px-2.5 text-sm transition-colors duration-150',
                camera === c.id ? 'bg-white/10 text-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]' : 'text-fg-2 hover:text-fg',
              )}
            >
              {c.label}
              <Kbd className="h-4 min-w-4 px-1 opacity-70">{c.key}</Kbd>
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-line-2" aria-hidden />
          <Tip label={modelStyle === 'photo' ? '3D models made from the IKEA photos. Click for plain shapes.' : 'Plain shapes at the listed sizes. Click for photo models.'}>
            <button
              type="button"
              onClick={() => setModelStyle(modelStyle === 'photo' ? 'clay' : 'photo')}
              aria-pressed={modelStyle === 'photo'}
              aria-label={modelStyle === 'photo' ? 'Photo models on. Switch to plain shapes.' : 'Plain shapes. Switch to photo models.'}
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-sm transition-colors duration-150 hover:bg-white/6',
                modelStyle === 'photo' ? 'text-fg' : 'text-fg-3',
              )}
            >
              <Box size={15} strokeWidth={1.8} />
            </button>
          </Tip>
          {floorItems > 0 && (
            <>
              <Tip label={`${existingWords[existing]}. The scan found ${floorItems} pieces already in the room.`}>
                <button
                  type="button"
                  onClick={() => setExisting(nextExisting[existing])}
                  aria-label={existingWords[existing]}
                  className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-sm transition-colors duration-150 hover:bg-white/6',
                    existing === 'show' ? 'text-fg' : existing === 'ghost' ? 'text-fg-2' : 'text-fg-3',
                  )}
                >
                  <Armchair size={15} strokeWidth={1.8} className={existing === 'hidden' ? 'opacity-50' : ''} />
                </button>
              </Tip>
            </>
          )}
        </div>
        <button
          type="button"
          onClick={() => setCartOpen(!cartOpen)}
          disabled={inCart.length === 0}
          aria-pressed={cartOpen}
          className={cn(
            'glass flex h-10 items-center gap-2 rounded-md px-3 text-sm transition-colors duration-150',
            inCart.length === 0 ? 'text-fg-3' : 'text-fg hover:bg-white/5',
            cartOpen && 'ring-1 ring-inset ring-ice/50',
          )}
        >
          <ShoppingBag size={15} strokeWidth={1.8} aria-hidden />
          <span>Cart</span>
          {inCart.length > 0 && (
            <>
              <span className="num text-fg-2">{inCart.length}</span>
              <span className="h-3.5 w-px bg-line-2" aria-hidden />
              <Ticker value={total} />
            </>
          )}
        </button>
      </div>
    </header>
  )
}
