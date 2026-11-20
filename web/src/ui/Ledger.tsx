// The audit trail. Every row is one record the agent wrote, in the order it wrote it.
import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ListOrdered, Quote, Ruler, ShieldCheck, ShoppingBag, Repeat2, Terminal, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { productById } from '../data'
import { clock, cn, sinceStart, slotLabel, splitName, usd } from '../lib/format'
import { useApp } from '../store'
import type { AuditRecord, PlanItem } from '../types'
import { ProductPhoto } from './bits'

type Tone = 'fits' | 'nofit' | 'unsure' | null
interface Row {
  r: AuditRecord
  title: string
  source: string
  tone: Tone
  /** Tool calls and the agent's own narration: real, but shown only when Details is on. */
  minor: boolean
  icon: typeof Check
}

const family = (id?: string) => (id && productById[id] ? splitName(productById[id].name)[0] : 'this one')

function toRow(r: AuditRecord): Row {
  const base = { r, tone: null as Tone, minor: false }
  if (r.step === 'estimate_room') {
    if (r.decision.startsWith('style')) return { ...base, title: 'Read the style you asked for', source: 'Superlinked', icon: Quote }
    return { ...base, title: 'Took the room measurements', source: 'Room', icon: Ruler }
  }
  if (r.step === 'rank' && r.decision === 'ranked by style')
    return { ...base, title: 'Ranked the catalog by style', source: 'Superlinked', icon: ListOrdered }
  if (r.step === 'rank' && r.decision === 'fit checked')
    return { ...base, title: 'Checked what fits the room', source: 'Fit check', icon: Ruler }
  if (r.step === 'rank') return { ...base, title: 'Ranked again for the pick', source: 'Superlinked', icon: ListOrdered, minor: true }
  if (r.step === 'pick' && r.decision === 'picked')
    return { ...base, title: `Picked ${family(r.product_id)}`, source: 'Pick', icon: Check, tone: 'fits' }
  if (r.step === 'pick')
    return {
      ...base,
      title: `Rejected ${family(r.product_id)}`,
      source: 'Pick',
      icon: X,
      tone: r.status === 'unsure' ? 'unsure' : 'nofit',
    }
  if (r.step === 'senso_check')
    return {
      ...base,
      title: r.status === 'verified' ? 'Senso verified the claims' : 'Senso checked the claims',
      source: 'Senso',
      icon: ShieldCheck,
      tone: r.status === 'verified' ? 'fits' : 'unsure',
    }
  if (r.step === 'cart') return { ...base, title: 'Added to the cart', source: 'Claude', icon: ShoppingBag }
  if (r.step === 'measure') return { ...base, title: r.decision.charAt(0).toUpperCase() + r.decision.slice(1), source: 'You', icon: Ruler, tone: r.status === 'no_fit' ? 'nofit' : 'fits' }
  if (r.step === 'swap') return { ...base, title: `You swapped in ${family(r.product_id)}`, source: 'You', icon: Repeat2 }
  if (r.step === 'agent' && r.decision === 'said') return { ...base, title: 'Agent note', source: 'Claude', icon: Quote, minor: true }
  if (r.step === 'agent' && r.decision.startsWith('call '))
    return { ...base, title: r.decision.slice(5), source: 'Tool call', icon: Terminal, minor: true }
  return { ...base, title: r.decision, source: r.source.kind, icon: Terminal, minor: true }
}

/** Pseudo-slot for things the person did to the room (tape measurements). */
const YOU = '__you'

interface Group {
  slot: string | null
  rows: Row[]
}

function group(audit: AuditRecord[]): Group[] {
  const groups: Group[] = []
  const bySlot = new Map<string | null, Group>()
  let last: Group | null = null
  for (const r of audit) {
    const prevSlot: string | null = last ? last.slot : null
    const slot: string | null = r.step === 'measure' ? YOU : (r.item_slot ?? (r.step === 'estimate_room' ? null : prevSlot))
    let g = bySlot.get(slot)
    if (!g) {
      g = { slot, rows: [] }
      bySlot.set(slot, g)
      groups.push(g)
    }
    g.rows.push(toRow(r))
    last = g
  }
  return groups
}

const toneText: Record<Exclude<Tone, null>, string> = { fits: 'text-fits', nofit: 'text-nofit', unsure: 'text-unsure' }

function RowView({ row, start, open, onToggle }: { row: Row; start: string; open: boolean; onToggle: () => void }) {
  const Icon = row.icon
  const mono = row.source === 'Tool call'
  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
      className="relative pl-7"
    >
      <span
        className={cn(
          'absolute left-0 top-[3px] flex h-[18px] w-[18px] items-center justify-center rounded-full bg-raise ring-1 ring-inset ring-line-2',
          row.tone ? toneText[row.tone] : 'text-fg-2',
          row.minor && 'bg-transparent text-fg-3 ring-line',
        )}
      >
        <Icon size={11} strokeWidth={2.2} aria-hidden />
      </span>
      <button type="button" onClick={onToggle} aria-expanded={open} className="block w-full rounded-xs text-left">
        <span className="flex items-baseline justify-between gap-2">
          <span
            className={cn(
              'min-w-0 truncate text-sm',
              row.minor ? 'text-fg-2' : 'font-medium text-fg',
              mono && 'num text-xs',
              row.tone === 'nofit' && 'text-nofit',
            )}
          >
            {row.title}
          </span>
          <span className="num shrink-0 text-2xs text-fg-3">{row.r.source.kind === 'you' ? clock(row.r.ts).slice(0, 5) : sinceStart(row.r.ts, start)}</span>
        </span>
        <span className={cn('mt-0.5 block text-xs leading-relaxed text-fg-2', !open && 'line-clamp-2', row.minor && 'text-fg-3')}>
          <span className="text-fg-3">{row.source}. </span>
          {row.r.why}
        </span>
      </button>
    </motion.li>
  )
}

function SlotHeader({ slot, item, phase, active }: { slot: string; item: PlanItem | null; phase?: string; active: boolean }) {
  const select = useApp((s) => s.select)
  const selected = useApp((s) => s.selectedSlot === slot)
  const [fam, rest] = item ? splitName(item.name) : ['', '']
  return (
    <button
      type="button"
      disabled={!item}
      onClick={() => item && select(selected ? null : slot)}
      aria-pressed={selected}
      className={cn(
        'group/h -mx-2 mb-2.5 flex w-[calc(100%+1rem)] items-center gap-2.5 rounded-sm px-2 py-1.5 text-left transition-colors duration-150',
        item && 'hover:bg-white/5',
        selected && 'bg-ice/8 ring-1 ring-inset ring-ice/40',
      )}
    >
      {item ? (
        <ProductPhoto src={item.image_url} alt="" className="h-9 w-9 shrink-0 rounded-[5px]" />
      ) : (
        <span className="h-9 w-9 shrink-0 rounded-[5px] border border-dashed border-line-2" aria-hidden />
      )}
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="truncate text-sm font-semibold text-fg">{item ? fam : slotLabel(slot)}</span>
          {item && <span className="num text-xs text-fg-2">{usd(item.price_usd)}</span>}
        </span>
        <span className="block truncate text-xs text-fg-3">{item ? `${slotLabel(slot)}, ${rest.replace(/^[^,]*,\s*/, '')}` : 'Looking through the catalog'}</span>
      </span>
      {phase === 'in_cart' || phase === 'verified' ? (
        <ShieldCheck size={15} strokeWidth={2} className="shrink-0 text-fits" aria-label="Verified by Senso" />
      ) : active ? (
        <span className="relative mr-1 flex h-1.5 w-1.5 shrink-0" aria-label="In progress">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-fg/60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-fg" />
        </span>
      ) : null}
    </button>
  )
}

export default function Ledger() {
  const audit = useApp((s) => s.audit)
  const plan = useApp((s) => s.plan)
  const placed = useApp((s) => s.placed)
  const activeSlot = useApp((s) => s.activeSlot)
  const stage = useApp((s) => s.stage)
  const [details, setDetails] = useState(false)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  const groups = useMemo(() => group(audit), [audit])
  const start = audit[0]?.ts ?? ''
  const minorCount = useMemo(() => groups.reduce((n, g) => n + g.rows.filter((r) => r.minor).length, 0), [groups])
  const finished = audit.find((r) => r.step === 'agent' && r.status === 'done')
  const finishedInput = (finished?.input ?? null) as { num_turns?: number; duration_ms?: number } | null

  // Follow the run as it streams. A finished plan opened in one go starts at the top.
  const prevLen = useRef(0)
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const jumped = audit.length - prevLen.current > 6
    prevLen.current = audit.length
    if (jumped) {
      el.scrollTop = 0
      stick.current = false
    } else if ((stick.current && stage === 'running') || audit[audit.length - 1]?.source.kind === 'you') {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audit.length, stage])

  if (!plan) return null
  const shown = audit.length - (details ? 0 : minorCount)

  return (
    <motion.aside
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: 'spring', stiffness: 360, damping: 34 }}
      aria-label="Audit trail"
      className="glass absolute bottom-4 left-3 top-16 z-10 flex w-[336px] flex-col overflow-hidden rounded-lg"
    >
      <div className="flex items-center justify-between gap-2 px-4 pb-2.5 pt-3.5">
        <div>
          <h2 className="text-base font-semibold text-fg">Audit trail</h2>
          <p className="mt-0.5 text-xs text-fg-3">
            <span className="num">{shown}</span> of <span className="num">{audit.length}</span> records shown
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDetails((d) => !d)}
          aria-pressed={details}
          title="Show every tool call and note the agent wrote"
          className={cn('btn h-7 px-2 text-xs', details ? 'btn-ghost text-fg' : 'btn-quiet')}
        >
          <Terminal size={12} strokeWidth={2} aria-hidden />
          {details ? 'Hide tool calls' : 'Tool calls'}
        </button>
      </div>
      <div className="hairline" />
      <div
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
        }}
        className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-3"
      >
        {groups.map((g, gi) => {
          const rows = details ? g.rows : g.rows.filter((r) => !r.minor)
          if (!rows.length && g.slot === null) return null
          const item = g.slot ? (plan.items.find((i) => i.slot === g.slot && placed[i.slot]) ?? null) : null
          return (
            <section key={g.slot ?? 'room'} className={cn(gi > 0 && 'mt-4 border-t border-line pt-3')}>
              {g.slot === YOU ? (
                <h3 className="mb-2.5 text-sm font-semibold text-fg">Your measurements</h3>
              ) : g.slot ? (
                <SlotHeader slot={g.slot} item={item} phase={placed[g.slot]} active={stage === 'running' && activeSlot === g.slot} />
              ) : (
                <h3 className="mb-2.5 text-sm font-semibold text-fg">The room</h3>
              )}
              <ol className="relative space-y-3 before:absolute before:bottom-2 before:left-[8.5px] before:top-2 before:w-px before:bg-line">
                <AnimatePresence initial={false}>
                  {rows.map((row) => {
                    const key = `${row.r.ts}|${row.r.step}|${row.r.decision}|${row.r.product_id ?? ''}|${row.r.item_slot ?? ''}`
                    return (
                      <RowView
                        key={key}
                        row={row}
                        start={start}
                        open={open.has(key)}
                        onToggle={() =>
                          setOpen((o) => {
                            const n = new Set(o)
                            if (n.has(key)) n.delete(key)
                            else n.add(key)
                            return n
                          })
                        }
                      />
                    )
                  })}
                </AnimatePresence>
              </ol>
            </section>
          )
        })}
        {stage === 'done' && finished && (
          <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-fg-3">
            The agent finished after <span className="num text-fg-2">{finishedInput?.num_turns ?? '?'}</span> turns
            {finishedInput?.duration_ms ? (
              <>
                {' '}
                and <span className="num text-fg-2">{Math.round(finishedInput.duration_ms / 1000)}</span> seconds
              </>
            ) : null}
            . Its tools refuse to add anything to the cart without a passing fit check and a Senso check.
          </p>
        )}
      </div>
    </motion.aside>
  )
}
