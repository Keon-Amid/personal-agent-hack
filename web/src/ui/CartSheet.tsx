import { useState } from 'react'
import { ArrowUpRight, Check, Download, ShieldCheck, X } from 'lucide-react'
import { motion } from 'motion/react'
import { clock, cn, slotLabel, splitName, usd } from '../lib/format'
import { approveCart } from '../run'
import { placedItems, useApp } from '../store'
import { Kbd, ProductPhoto, Ticker, VerdictIcon } from './bits'

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function CartSheet() {
  const plan = useApp((s) => s.plan)
  const placed = useApp((s) => s.placed)
  const audit = useApp((s) => s.audit)
  const budget = useApp((s) => s.budget)
  const setCartOpen = useApp((s) => s.setCartOpen)
  const select = useApp((s) => s.select)
  const stage = useApp((s) => s.stage)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  if (!plan) return null
  const approval = plan.cart.approval?.approved ? plan.cart.approval : null
  const blocked = stage !== 'done' ? 'The agent is still working. Approve when it finishes.' : null
  const approve = async () => {
    setBusy(true)
    setProblem(null)
    try {
      await approveCart()
    } catch (e) {
      setProblem(e instanceof Error ? e.message : 'The approval did not go through.')
    } finally {
      setBusy(false)
    }
  }
  const items = placedItems({ plan, placed })
  const total = Math.round(items.reduce((n, i) => n + (i.price_usd ?? 0), 0) * 100) / 100
  const unpriced = items.filter((i) => i.price_usd === null).length
  const over = budget !== null && total > budget
  const pct = budget ? Math.min(100, (total / budget) * 100) : 0
  const claims = items.reduce((n, i) => n + (i.senso?.claims.length ?? 0), 0)
  const verified = items.reduce((n, i) => n + (i.senso?.claims.filter((c) => c.verdict === 'verified').length ?? 0), 0)

  return (
    <motion.aside
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20, transition: { duration: 0.14 } }}
      transition={{ type: 'spring', stiffness: 380, damping: 36 }}
      aria-label="Cart"
      className="glass absolute bottom-4 right-3 top-16 z-10 flex w-[420px] flex-col overflow-hidden rounded-lg"
    >
      <div className="flex h-11 shrink-0 items-center justify-between pl-4 pr-2">
        <h2 className="text-base font-semibold text-fg">
          Cart <span className="num ml-1 text-sm font-normal text-fg-3">{items.length} pieces</span>
        </h2>
        <button type="button" onClick={() => setCartOpen(false)} className="btn btn-quiet h-7 gap-1.5 px-1.5" aria-label="Close the cart">
          <X size={15} />
          <Kbd className="h-4 px-1">esc</Kbd>
        </button>
      </div>
      <div className="hairline" />

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {items.length === 0 ? (
          <p className="p-4 text-sm leading-relaxed text-fg-2">
            Nothing here yet. Describe the room you want and the agent adds each piece once it passes the fit check and Senso.
          </p>
        ) : (
          <ul className="divide-y divide-line px-4">
            {items.map((i) => {
              const [fam, rest] = splitName(i.name)
              return (
                <li key={i.slot} className="flex items-center gap-3 py-3">
                  <button type="button" onClick={() => select(i.slot)} className="shrink-0 rounded-[7px]" aria-label={`Show ${fam} in the room`}>
                    <ProductPhoto src={i.image_url} alt="" className="h-14 w-14" />
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="truncate text-sm font-semibold text-fg">{fam}</span>
                      <span className="num shrink-0 text-sm text-fg">{usd(i.price_usd)}</span>
                    </div>
                    <div className="truncate text-xs text-fg-3">
                      {slotLabel(i.slot)}, {rest.replace(/^[^,]*,\s*/, '')}
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <span className="flex items-center gap-3 text-xs text-fg-2">
                        <span className="flex items-center gap-1">
                          <VerdictIcon verdict={i.fit.verdict} size={12} />
                          {i.fit.verdict === 'fits' ? 'Fits' : i.fit.verdict === 'unsure' ? 'Measure first' : 'Does not fit'}
                        </span>
                        {i.senso ? (
                          <span className="flex items-center gap-1">
                            <ShieldCheck size={12} strokeWidth={2.2} className="text-fits" aria-hidden />
                            Senso verified
                          </span>
                        ) : (
                          <span className="text-unsure">Senso not run</span>
                        )}
                      </span>
                      <a
                        href={i.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex shrink-0 items-center gap-0.5 text-xs text-fg underline decoration-line-2 hover:decoration-fg"
                      >
                        Open on IKEA
                        <ArrowUpRight size={12} strokeWidth={2} aria-hidden />
                      </a>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div className="shrink-0 border-t border-line bg-black/20 p-4">
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-fg-2">Total</span>
          <Ticker value={total} className="text-xl font-medium text-fg" />
        </div>
        {unpriced > 0 && <p className="mt-1 text-xs text-unsure">{unpriced} piece has no price on its IKEA page, so it isn't in the total.</p>}
        {budget !== null && (
          <div className="mt-2.5">
            <div className="h-1 overflow-hidden rounded-full bg-white/8">
              <div className={cn('h-full rounded-full', over ? 'bg-nofit' : 'bg-fits')} style={{ width: `${pct}%` }} />
            </div>
            <p className={cn('num mt-1.5 text-xs', over ? 'text-nofit' : 'text-fg-2')}>
              {over ? `${usd(total - budget)} over your ${usd(budget)} budget` : `${usd(budget - total)} under your ${usd(budget)} budget`}
            </p>
          </div>
        )}
        <dl className="mt-3 space-y-1 text-xs text-fg-2">
          <div className="flex justify-between gap-3">
            <dt>Delivery</dt>
            <dd>{plan.cart.delivery_note ?? 'Shown on IKEA.com'}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt>Proof</dt>
            <dd className="num">
              {verified} of {claims} claims verified
            </dd>
          </div>
        </dl>
        {approval ? (
          <div className="mt-3 rounded-sm bg-fits/8 px-2.5 py-2 ring-1 ring-inset ring-fits/25" role="status">
            <p className="flex items-center gap-1.5 text-sm font-medium text-fg">
              <Check size={14} strokeWidth={2.4} className="text-fits" aria-hidden />
              You approved this cart at <span className="num">{clock(approval.approved_at).slice(0, 5)}</span>
            </p>
            <p className="mt-1 text-xs leading-relaxed text-fg-2">
              It is in the audit trail. Nothing is ordered until you pay on IKEA.com.
            </p>
          </div>
        ) : (
          <p className="mt-3 rounded-sm bg-white/4 px-2.5 py-2 text-xs leading-relaxed text-fg-2 ring-1 ring-inset ring-line">
            Approving records your OK in the audit trail. No order is placed: you pay on IKEA.com.
          </p>
        )}
        {problem && (
          <p className="mt-2 text-xs text-nofit" role="alert">
            {problem} Try again.
          </p>
        )}
        {approval ? (
          <button
            type="button"
            onClick={() => items.forEach((i) => window.open(i.source_url, '_blank', 'noopener'))}
            className="btn btn-primary mt-3 w-full"
            title="Opens each product page in a new tab. Your browser may ask to allow pop-ups."
          >
            Open all {items.length} on IKEA
            <ArrowUpRight size={14} strokeWidth={2} aria-hidden />
          </button>
        ) : (
          <button type="button" onClick={approve} disabled={busy || !!blocked || items.length === 0} title={blocked ?? undefined} className="btn btn-primary mt-3 w-full">
            {busy ? 'Approving…' : `Approve ${items.length} pieces for ${usd(total)}`}
          </button>
        )}
        <button
          type="button"
          onClick={() => download(`audit-${plan.plan_id}.json`, { plan_id: plan.plan_id, room: plan.room, style: plan.style, cart: { ...plan.cart, total_usd: total }, items, audit })}
          className="btn btn-ghost mt-2 w-full"
        >
          <Download size={14} strokeWidth={2} aria-hidden />
          Download the audit trail, <span className="num">{audit.length}</span> records
        </button>
      </div>
    </motion.aside>
  )
}
