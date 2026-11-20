import { useEffect, useRef, useState } from 'react'
import { CornerDownLeft, RotateCcw, ShoppingBag, Wallet } from 'lucide-react'
import { motion } from 'motion/react'
import { wantsLive } from '../api/api'
import { cn, slotLabel, usd } from '../lib/format'
import { skipRun, startReplay, startRun } from '../run'
import { useApp } from '../store'
import { Kbd } from './bits'
import { Tip } from './tooltip'

const INPUT_ID = 'command-input'
export const focusCommand = () => {
  const el = document.getElementById(INPUT_ID) as HTMLInputElement | null
  el?.focus()
  el?.select()
}

function Budget() {
  const budget = useApp((s) => s.budget)
  const setBudget = useApp((s) => s.setBudget)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (editing) ref.current?.select()
  }, [editing])
  const commit = () => {
    const v = Number.parseFloat(draft.replace(/[^0-9.]/g, ''))
    setBudget(Number.isFinite(v) && v > 0 ? Math.round(v) : null)
    setEditing(false)
  }
  if (editing)
    return (
      <span className="flex h-8 items-center gap-1 rounded-sm bg-black/30 pl-2 pr-1 ring-1 ring-inset ring-ice/60">
        <span className="text-xs text-fg-3">$</span>
        <input
          ref={ref}
          aria-label="Budget in dollars"
          name="budget"
          autoComplete="off"
          inputMode="numeric"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              commit()
            }
            if (e.key === 'Escape') {
              e.stopPropagation()
              setEditing(false)
            }
          }}
          className="num w-16 bg-transparent text-sm text-fg outline-none"
        />
      </span>
    )
  return (
    <button
      type="button"
      onClick={() => {
        setDraft(budget ? String(budget) : '')
        setEditing(true)
      }}
      className="flex h-8 items-center gap-1.5 rounded-sm px-2 text-sm text-fg-2 ring-1 ring-inset ring-line transition-colors duration-150 hover:bg-white/6 hover:text-fg"
    >
      <Wallet size={14} strokeWidth={1.8} aria-hidden />
      {budget ? <span className="num text-fg">{usd(budget)}</span> : 'Set a budget'}
    </button>
  )
}

export default function CommandBar() {
  const stage = useApp((s) => s.stage)
  const plan = useApp((s) => s.plan)
  const placed = useApp((s) => s.placed)
  const activeSlot = useApp((s) => s.activeSlot)
  const audit = useApp((s) => s.audit)
  const selected = useApp((s) => s.selectedSlot)
  const cartOpen = useApp((s) => s.cartOpen)
  const runError = useApp((s) => s.runError)
  const budget = useApp((s) => s.budget)
  const [text, setText] = useState('')
  const live = useApp((s) => wantsLive(s.server.ready))
  const runMode = useApp((s) => s.runMode)

  // In replay mode the words are the ones the recorded run was given, so what you read matches what ran.
  // Live, the words are yours and the agent acts on them.
  const planId = plan?.plan_id
  useEffect(() => {
    if (plan && stage !== 'running') setText(live ? '' : plan.style.style_text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId, live])
  useEffect(() => {
    if (stage === 'ready') focusCommand()
  }, [stage])

  if (!plan) return null
  const total = plan.items.length
  const inCart = plan.items.filter((i) => placed[i.slot] === 'in_cart').length
  const sum = plan.items.filter((i) => placed[i.slot]).reduce((n, i) => n + (i.price_usd ?? 0), 0)
  const claims = plan.items.reduce((n, i) => n + (placed[i.slot] && i.senso ? i.senso.claims.filter((c) => c.verdict === 'verified').length : 0), 0)
  const rejected = plan.items.reduce((n, i) => n + (placed[i.slot] ? (i.rejected?.length ?? 0) : 0), 0)
  const allFit = plan.items.every((i) => i.fit.verdict === 'fits')
  const over = budget !== null && sum > budget
  // Sit in the free space between the audit trail (left) and whichever side panel is open (right).
  const left = stage === 'running' || stage === 'done' ? 348 : 0
  const right = cartOpen ? 432 : selected ? 396 : 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 14, x: (left - right) / 2 }}
      animate={{ opacity: 1, y: 0, x: (left - right) / 2 }}
      transition={{ type: 'spring', stiffness: 380, damping: 36 }}
      className="pointer-events-none absolute inset-x-0 bottom-4 z-20 flex justify-center px-3"
    >
      <div
        className="glass pointer-events-auto w-full rounded-lg transition-shadow duration-150 focus-within:ring-1 focus-within:ring-ice/45"
        style={{ maxWidth: `min(660px, calc(100vw - ${left + right + 24}px))` }}
      >
        {stage === 'ready' && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (text.trim()) startRun(text.trim())
            }}
            className="flex items-center gap-2 p-2 pl-4"
          >
            <input
              id={INPUT_ID}
              value={text}
              onChange={(e) => setText(e.target.value)}
              name="style"
              placeholder={live ? 'Describe the room you want… warm minimal living room with a TV' : 'Describe the room you want…'}
              aria-label="Describe the room you want"
              autoComplete="off"
              spellCheck={false}
              className="h-9 min-w-0 flex-1 bg-transparent text-base text-fg outline-none"
            />
            <Budget />
            <button type="submit" disabled={!text.trim()} className="btn btn-primary h-9 pl-3 pr-2">
              Furnish
              <span className="flex h-5 w-5 items-center justify-center rounded-[4px] bg-black/10">
                <CornerDownLeft size={12} strokeWidth={2.2} aria-hidden />
              </span>
            </button>
          </form>
        )}

        {stage === 'running' && (
          <div className="flex items-center gap-3 p-2 pl-4">
            <span className="relative flex h-2 w-2" aria-hidden>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-fg/50" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-fg" />
            </span>
            <div className="min-w-0 flex-1" role="status" aria-live="polite">
              <div className="truncate text-base text-fg">
                {activeSlot ? `Working on the ${slotLabel(activeSlot).toLowerCase()}…` : 'Reading the room…'}
              </div>
              <div className="num text-xs text-fg-3">
                {inCart} of {runMode === 'live' ? 5 : total} in the cart, {audit.length} steps logged
                {runMode === 'live' ? ', live' : ''}
              </div>
            </div>
            <div className="flex h-1 w-28 overflow-hidden rounded-full bg-white/8" aria-hidden>
              <div
                className="h-full rounded-full bg-fg transition-[width] duration-500 ease-out"
                style={{ width: `${Math.max(4, Math.min(100, (audit.length / (runMode === 'live' ? 75 : Math.max(1, plan.audit.length))) * 100))}%` }}
              />
            </div>
            {runMode === 'mock' && (
              <button type="button" onClick={skipRun} className="btn btn-ghost h-9">
                Skip to the result
              </button>
            )}
          </div>
        )}

        {stage === 'done' && (
          <div className="flex items-center gap-3 p-2 pl-4">
            <div className="min-w-0 flex-1">
              <div className="truncate text-base text-fg">
                {total} pieces, <span className="num">{usd(sum)}</span>
              </div>
              <div className="truncate text-xs text-fg-2">
                {budget !== null && (
                  <span className={cn(over ? 'text-nofit' : 'text-fits')}>
                    {over ? `${usd(sum - budget)} over` : `${usd(budget - sum)} under`} your budget.{' '}
                  </span>
                )}
                {allFit ? 'Every piece fits. ' : `${plan.items.filter((i) => i.fit.verdict !== 'fits').length} need attention. `}
                <span className="num">{claims}</span> claims verified by Senso
                {rejected > 0 && (
                  <>
                    , <span className="num">{rejected}</span> rejected
                  </>
                )}
              </div>
            </div>
            <Budget />
            <Tip label="Describe it again" side="top">
              <button
                type="button"
                onClick={() => useApp.setState({ stage: 'ready', selectedSlot: null, cartOpen: false })}
                className="btn btn-ghost h-9 w-9 px-0"
                aria-label="Describe it again"
              >
                <RotateCcw size={14} strokeWidth={1.9} />
              </button>
            </Tip>
            <button type="button" onClick={() => useApp.getState().setCartOpen(true)} className="btn btn-primary h-9">
              <ShoppingBag size={14} strokeWidth={2} aria-hidden />
              Review the cart
            </button>
          </div>
        )}

        {runError && stage === 'ready' && (
          <p className="flex items-center justify-between gap-3 border-t border-line px-4 py-2 text-xs text-nofit" role="alert">
            <span className="min-w-0">The live agent stopped: {runError}</span>
            <button type="button" onClick={startReplay} className="shrink-0 text-fg underline">
              Play the recorded run
            </button>
          </p>
        )}

        <div className="flex items-center gap-4 border-t border-line px-4 py-1.5 text-2xs text-fg-3">
          <span className="flex items-center gap-1.5">
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
            describe
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>←</Kbd>
            <Kbd>→</Kbd>
            step through pieces
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>1</Kbd>
            <Kbd>2</Kbd>
            <Kbd>3</Kbd>
            views
          </span>
          <span className="ml-auto flex items-center gap-1.5">
            <Kbd>esc</Kbd>
            close
          </span>
        </div>
      </div>
    </motion.div>
  )
}
