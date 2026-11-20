// Everything the agent knows about one piece, and why it chose it.
import { useEffect, useState } from 'react'
import { ArrowUpRight, ChevronLeft, ChevronRight, Star, X } from 'lucide-react'
import { motion } from 'motion/react'
import { optionsFor, productById } from '../data'
import { checkLabel, cn, inches, slotLabel, splitName, usd } from '../lib/format'
import { refitOption } from '../lib/refit'
import { itemBySlot, placedItems, useApp } from '../store'
import type { FitResult } from '../types'
import { useModelManifest } from '../room3d/Model'
import AltChart from './AltChart'
import { Kbd, ProductPhoto, SectionTitle, SensoChip, VerdictChip, VerdictIcon } from './bits'

/** fit.options writes "no_fit: <math>"; say it in words. */
const sayWhy = (why: string) => why.replace(/^no_fit:\s*/, 'Does not fit: ').replace(/^unsure:\s*/, 'Too close to call: ')

function Fit({ r }: { r: FitResult }) {
  const margin = r.margin_in
  return (
    <li className="flex gap-2.5">
      <span className="mt-[3px] shrink-0">
        <VerdictIcon verdict={r.verdict} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-sm text-fg">{checkLabel[r.check] ?? r.check.replace(/_/g, ' ')}</span>
          {margin !== undefined && (
            <span className={cn('num shrink-0 text-xs', margin >= 0 ? 'text-fg-2' : 'text-nofit')}>
              {margin >= 0 ? `${inches(margin)} in to spare` : `${inches(-margin)} in too big`}
            </span>
          )}
        </div>
        <div className="num mt-0.5 text-xs leading-relaxed text-fg-3">{r.math}</div>
      </div>
    </li>
  )
}

export default function Inspector() {
  const plan = useApp((s) => s.plan)
  const slot = useApp((s) => s.selectedSlot)
  const placed = useApp((s) => s.placed)
  const stage = useApp((s) => s.stage)
  const select = useApp((s) => s.select)
  const swap = useApp((s) => s.swap)
  const overrides = useApp((s) => s.overrides)
  const modelStyle = useApp((s) => s.modelStyle)
  const manifest = useModelManifest('/models/index.json')
  const [allClaims, setAllClaims] = useState(false)
  const [pickedAlt, setPickedAlt] = useState<string | null>(null)
  useEffect(() => {
    setAllClaims(false)
    setPickedAlt(null)
  }, [slot])

  const item = itemBySlot(plan, slot)
  if (!plan || !slot || !item) return null
  const product = productById[item.product_id]
  const [fam, rest] = splitName(item.name)
  const phase = placed[slot]
  const items = placedItems({ plan, placed })
  const idx = items.findIndex((i) => i.slot === slot)
  const go = (d: number) => items.length > 1 && select(items[(idx + d + items.length) % items.length].slot)
  const roomPlanId = useApp.getState().roomPlanId
  const options = optionsFor(plan.plan_id, slot, roomPlanId).map((o) => refitOption(o, plan.room, overrides))
  const failing = item.fit.results.find((r) => r.verdict === item.fit.verdict && r.verdict !== 'fits')
  const fitting = options.filter((o) => o.fit === 'fits' && o.id !== item.product_id && o.price_usd !== null)
  const rescue = fitting.find((o) => o.best_value) ?? [...fitting].sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))[0] ?? null
  const claims = item.senso?.claims ?? []
  const verified = claims.filter((c) => c.verdict === 'verified').length
  const shownClaims = allClaims ? claims : claims.slice(0, 3)
  const alt = options.find((o) => o.id === pickedAlt && o.id !== item.product_id) ?? null
  const sorted = [...options].sort((a, b) => (a.price_usd ?? 1e9) - (b.price_usd ?? 1e9))

  return (
    <motion.aside
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20, transition: { duration: 0.14 } }}
      transition={{ type: 'spring', stiffness: 380, damping: 36 }}
      aria-label={`${slotLabel(slot)} details`}
      className="glass absolute bottom-4 right-3 top-16 z-10 flex w-[384px] flex-col overflow-hidden rounded-lg"
    >
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 pl-4 pr-2">
        <span className="text-sm text-fg-2">
          {slotLabel(slot)}
          {items.length > 1 && (
            <span className="num ml-2 text-xs text-fg-3">
              {idx + 1} of {items.length}
            </span>
          )}
        </span>
        <div className="flex items-center gap-0.5">
          <button type="button" onClick={() => go(-1)} disabled={items.length < 2} className="btn btn-quiet h-7 w-7 px-0" aria-label="Previous piece">
            <ChevronLeft size={15} />
          </button>
          <button type="button" onClick={() => go(1)} disabled={items.length < 2} className="btn btn-quiet h-7 w-7 px-0" aria-label="Next piece">
            <ChevronRight size={15} />
          </button>
          <button type="button" onClick={() => select(null)} className="btn btn-quiet h-7 gap-1.5 px-1.5" aria-label="Close">
            <X size={15} />
            <Kbd className="h-4 px-1">esc</Kbd>
          </button>
        </div>
      </div>
      <div className="hairline" />

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {failing && (
          <div className={cn('border-b p-4', item.fit.verdict === 'no_fit' ? 'border-nofit/25 bg-nofit/8' : 'border-unsure/25 bg-unsure/8')} role="alert">
            <div className="flex items-start gap-2.5">
              <span className="mt-[3px] shrink-0">
                <VerdictIcon verdict={item.fit.verdict} size={14} />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium text-fg">
                  {item.fit.verdict === 'no_fit' ? `${fam} doesn't fit this room.` : `${fam} is too close to call.`}
                </p>
                <p className="num mt-1 text-xs leading-relaxed text-fg-2">{failing.math}</p>
              </div>
            </div>
            {item.fit.verdict === 'no_fit' && rescue && (
              <button type="button" onClick={() => swap(slot, rescue.id)} className="btn btn-primary mt-3 w-full">
                Swap to {splitName(rescue.name)[0]} for {usd(rescue.price_usd)}
              </button>
            )}
            {item.fit.verdict === 'no_fit' && rescue && (
              <p className="mt-2 text-2xs leading-relaxed text-fg-3">
                {rescue.best_value ? 'The best-value piece that fits' : 'The best-rated piece that fits'}:{' '}
                <span className="num">{rescue.rating?.toFixed(1)}</span> from <span className="num">{rescue.review_count}</span> reviews.
              </p>
            )}
            {item.fit.verdict === 'no_fit' && !rescue && <p className="mt-2 text-xs text-fg-2">Nothing in this category fits. Try a different measurement or leave this slot empty.</p>}
            {item.fit.verdict === 'unsure' && <p className="mt-2 text-xs text-fg-2">Measure it with a tape (top left) and the answer becomes yes or no.</p>}
          </div>
        )}
        <div className="p-4 pb-5">
          <div className="flex gap-3.5">
            <ProductPhoto src={item.image_url} alt={item.name} className="h-[104px] w-[104px] shrink-0" />
            <div className="min-w-0 flex-1 py-0.5">
              <h2 className="text-lg font-semibold leading-tight tracking-[-0.01em] text-fg">{fam}</h2>
              <p className="mt-0.5 text-sm leading-snug text-fg-2">{rest}</p>
              <div className="num mt-2 text-lg font-medium leading-none text-fg">{usd(item.price_usd)}</div>
              {product?.rating != null && (
                <div className="mt-2 flex items-center gap-1 text-xs">
                  <Star size={12} className="fill-fg-2 text-fg-2" aria-hidden />
                  <span className="num text-fg">{product.rating.toFixed(1)}</span>
                  <span className="text-fg-3">
                    from <span className="num">{product.review_count}</span> reviews
                  </span>
                </div>
              )}
            </div>
          </div>
          <dl className="mt-3.5 grid grid-cols-3 divide-x divide-line rounded-sm bg-white/3 ring-1 ring-inset ring-line">
            {([['Width', item.dims_in.w], ['Depth', item.dims_in.d], ['Height', item.dims_in.h]] as const).map(([label, v]) => (
              <div key={label} className="px-3 py-2">
                <dt className="text-2xs text-fg-3">{label}</dt>
                <dd className="num mt-0.5 text-sm text-fg">
                  {inches(v)} <span className="text-fg-3">in</span>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-2xs leading-relaxed text-fg-3">
            {modelStyle === 'photo' && manifest[item.product_id]
              ? `In the room: a 3D model ${manifest[item.product_id].source.replace(/^AI-generated/, 'generated by AI')}, stretched to the listed size.`
              : 'In the room: a plain shape drawn at the listed width, depth and height.'}
          </p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <VerdictChip verdict={item.fit.verdict} />
            {item.senso ? (
              phase === 'picked' && stage === 'running' ? (
                <SensoChip pct={null} pending />
              ) : (
                <SensoChip pct={item.senso.accuracy_pct} />
              )
            ) : (
              <span className="inline-flex h-[22px] items-center rounded-full bg-unsure/10 px-2 text-xs font-medium text-unsure ring-1 ring-inset ring-unsure/30">
                Not checked by Senso yet
              </span>
            )}
          </div>
          <a href={item.source_url} target="_blank" rel="noreferrer" className="btn btn-ghost mt-3 w-full">
            Open on IKEA
            <ArrowUpRight size={14} strokeWidth={2} aria-hidden />
          </a>
        </div>

        <div className="hairline" />
        <section className="p-4">
          <SectionTitle
            aside={
              item.why_source?.kind === 'claude'
                ? Object.keys(overrides).length
                  ? 'Written by the agent, before you measured'
                  : 'Written by the agent'
                : item.why_source?.kind === 'fit'
                  ? 'From the fit check'
                  : undefined
            }
          >
            Why this one
          </SectionTitle>
          <p className="text-sm leading-relaxed text-fg-2">{item.why || 'The agent writes this when it adds the piece to the cart.'}</p>
          {item.style && (
            <p className="mt-2 text-xs leading-relaxed text-fg-3">
              Style match <span className="num text-fg-2">#{item.style.rank}</span> for “{plan.style.style_text}”, ranked by
              Superlinked.{' '}
              {item.style.product_styles.length > 0 && <>Its photo reads as {item.style.product_styles.slice(0, 3).join(', ')}.</>}
            </p>
          )}
        </section>

        <div className="hairline" />
        <section className="p-4">
          <SectionTitle aside={`${item.fit.results.filter((r) => r.verdict === 'fits').length} of ${item.fit.results.length} pass`}>
            Fit checks
          </SectionTitle>
          <ul className="space-y-2.5">
            {item.fit.results.map((r, i) => (
              <Fit key={`${r.check}-${i}`} r={r} />
            ))}
          </ul>
        </section>

        {(item.rejected?.length ?? 0) > 0 && (
          <>
            <div className="hairline" />
            <section className="p-4">
              <SectionTitle aside="Better style match, wrong size">Rejected first</SectionTitle>
              <ul className="space-y-2.5">
                {item.rejected.map((r) => (
                  <li key={r.product_id} className="flex gap-2.5">
                    <span className="mt-[3px] shrink-0">
                      <VerdictIcon verdict="no_fit" />
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm text-fg">{r.name}</div>
                      <div className="num mt-0.5 text-xs leading-relaxed text-nofit">{r.why}</div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}

        {item.senso && (
          <>
            <div className="hairline" />
            <section className="p-4">
              <SectionTitle aside={`${verified} of ${claims.length} claims verified`}>Checked against the catalog by Senso</SectionTitle>
              <ul className="space-y-3">
                {shownClaims.map((c, i) => (
                  <li key={i} className="flex gap-2.5">
                    <span className="mt-[3px] shrink-0">
                      <VerdictIcon verdict={c.verdict} />
                    </span>
                    <div className="min-w-0">
                      <div className="text-sm leading-snug text-fg">{c.claim}</div>
                      {c.quote && (
                        <blockquote className="mt-1 border-l border-line-2 pl-2.5 text-xs leading-relaxed text-fg-3">{c.quote.replace(/^-\s*/, '')}</blockquote>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {claims.length > 3 && (
                <button type="button" onClick={() => setAllClaims((v) => !v)} className="mt-3 text-xs text-fg-2 underline hover:text-fg">
                  {allClaims ? 'Show fewer' : `Show all ${claims.length} claims`}
                </button>
              )}
              <p className="num mt-3 text-2xs text-fg-3">Senso check {item.senso.check_id}</p>
            </section>
          </>
        )}

        {options.length > 1 && (
          <>
            <div className="hairline" />
            <section className="p-4">
              <SectionTitle aside={`${options.filter((o) => o.fit === 'fits').length} of ${options.length} fit`}>Alternatives</SectionTitle>
              <AltChart options={options} currentId={item.product_id} pickedId={pickedAlt} onPick={setPickedAlt} />
              <ul className="mt-3 divide-y divide-line">
                {sorted.map((o) => {
                  const current = o.id === item.product_id
                  const [f, d] = splitName(o.name)
                  return (
                    <li key={o.id}>
                      <button
                        type="button"
                        onClick={() => setPickedAlt(o.id === pickedAlt ? null : o.id)}
                        aria-pressed={o.id === pickedAlt}
                        className={cn(
                          '-mx-2 flex w-[calc(100%+1rem)] items-center gap-2.5 rounded-sm px-2 py-2 text-left transition-colors duration-150 hover:bg-white/5',
                          o.id === pickedAlt && 'bg-white/6',
                        )}
                      >
                        <ProductPhoto src={o.image_url} alt="" className="h-8 w-8 shrink-0 rounded-[5px]" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-fg">
                            {f} <span className="text-fg-3">{d.replace(/^[^,]*,\s*/, '')}</span>
                          </span>
                          <span className={cn('block truncate text-xs', o.fit === 'no_fit' ? 'text-nofit' : o.fit === 'unsure' ? 'text-unsure' : 'text-fg-3')}>
                            {current ? 'In the room now' : o.fit === 'fits' ? (o.best_value ? 'Fits, best value' : 'Fits') : sayWhy(o.why)}
                          </span>
                        </span>
                        <span className="shrink-0 text-right">
                          <span className="num block text-sm text-fg">{usd(o.price_usd)}</span>
                          <span className="num block text-xs text-fg-3">{o.rating != null ? `${o.rating.toFixed(1)} (${o.review_count})` : 'No rating'}</span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          </>
        )}
      </div>

      {alt && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className="shrink-0 border-t border-line bg-black/20 p-3"
        >
          {alt.fit === 'fits' ? (
            <>
              <button
                type="button"
                onClick={() => {
                  swap(slot, alt.id)
                  setPickedAlt(null)
                }}
                className="btn btn-primary w-full"
              >
                Swap to {splitName(alt.name)[0]} for {usd(alt.price_usd)}
              </button>
              <p className="mt-2 text-2xs leading-relaxed text-fg-3">
                The fit is already checked. Senso checks the new piece the next time the agent runs.
              </p>
            </>
          ) : (
            <p className="text-xs leading-relaxed text-fg-2">
              <span className="font-medium text-fg">{splitName(alt.name)[0]}</span> can't go in this room.{' '}
              <span className="num text-nofit">{sayWhy(alt.why)}</span>
            </p>
          )}
        </motion.div>
      )}
    </motion.aside>
  )
}
