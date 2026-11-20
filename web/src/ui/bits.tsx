import { useEffect, useRef, type ReactNode } from 'react'
import { useMotionValue, useReducedMotion, useSpring } from 'motion/react'
import { Check, HelpCircle, ShieldCheck, X } from 'lucide-react'
import type { Verdict } from '../types'
import { cn, usd } from '../lib/format'

/**
 * A dollar amount that rolls to its new value when a piece lands in the cart.
 * Adapted from Magic UI's number-ticker (spring value written straight to the DOM, no re-render per frame).
 */
export function Ticker({ value, className }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const reduced = useReducedMotion()
  const mv = useMotionValue(value)
  const spring = useSpring(mv, { damping: 36, stiffness: 190 })
  useEffect(() => {
    if (reduced) spring.jump(value)
    else mv.set(value)
  }, [mv, spring, value, reduced])
  useEffect(
    () =>
      spring.on('change', (v) => {
        if (ref.current) ref.current.textContent = usd(Math.abs(v - value) < 0.005 ? value : Math.round(v))
      }),
    [spring, value],
  )
  return (
    <span ref={ref} className={cn('num', className)}>
      {usd(value)}
    </span>
  )
}

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return <kbd className={cn('kbd', className)}>{children}</kbd>
}

const verdictStyle: Record<Verdict, { text: string; ring: string; label: string }> = {
  fits: { text: 'text-fits', ring: 'ring-fits/25 bg-fits/10', label: 'Fits' },
  unsure: { text: 'text-unsure', ring: 'ring-unsure/30 bg-unsure/10', label: 'Measure to be sure' },
  no_fit: { text: 'text-nofit', ring: 'ring-nofit/30 bg-nofit/10', label: 'Does not fit' },
}

export function VerdictIcon({ verdict, size = 13 }: { verdict: Verdict | string; size?: number }) {
  if (verdict === 'fits' || verdict === 'verified') return <Check size={size} strokeWidth={2.4} className="text-fits" aria-hidden />
  if (verdict === 'unsure' || verdict === 'not_verifiable' || verdict === 'unsupported')
    return <HelpCircle size={size} strokeWidth={2} className="text-unsure" aria-hidden />
  return <X size={size} strokeWidth={2.4} className="text-nofit" aria-hidden />
}

/** A verdict is always an icon plus words, never colour alone. */
export function VerdictChip({ verdict, label, className }: { verdict: Verdict; label?: string; className?: string }) {
  const s = verdictStyle[verdict]
  return (
    <span
      className={cn(
        'inline-flex h-[22px] items-center gap-1 rounded-full px-2 text-xs font-medium ring-1 ring-inset',
        s.text,
        s.ring,
        className,
      )}
    >
      <VerdictIcon verdict={verdict} size={12} />
      {label ?? s.label}
    </span>
  )
}

export function SensoChip({ pct, pending, className }: { pct: number | null | undefined; pending?: boolean; className?: string }) {
  if (pending)
    return (
      <span
        className={cn(
          'inline-flex h-[22px] items-center gap-1 rounded-full px-2 text-xs font-medium text-fg-2 ring-1 ring-inset ring-line-2',
          className,
        )}
      >
        <ShieldCheck size={12} strokeWidth={2} aria-hidden />
        Checking with Senso…
      </span>
    )
  return (
    <span
      className={cn(
        'inline-flex h-[22px] items-center gap-1 rounded-full bg-fits/10 px-2 text-xs font-medium text-fits ring-1 ring-inset ring-fits/25',
        className,
      )}
    >
      <ShieldCheck size={12} strokeWidth={2.2} aria-hidden />
      Verified by Senso
      {pct !== null && pct !== undefined && <span className="num text-fits/80">{Math.round(pct)}%</span>}
    </span>
  )
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <h3 className="text-sm font-semibold text-fg">{children}</h3>
      {aside && <div className="text-xs text-fg-3">{aside}</div>}
    </div>
  )
}

/** IKEA product photos are shot on white. Give them their own paper so they don't glare on graphite. */
export function ProductPhoto({ src, alt, className }: { src: string; alt: string; className?: string }) {
  return (
    <div className={cn('overflow-hidden rounded-[7px] bg-[#f3f1ec]', className)}>
      <img
        src={src}
        alt={alt}
        width={400}
        height={400}
        decoding="async"
        referrerPolicy="no-referrer"
        className="h-full w-full object-contain mix-blend-multiply"
      />
    </div>
  )
}
