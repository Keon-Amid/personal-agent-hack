// Price against rating for every catalog product in this slot, from fit.options.
// Form: scatter (two measures, one relationship). Verdict is carried by shape as well as colour.
import { useMemo, useState } from 'react'
import { splitName, usd } from '../lib/format'
import type { Option } from '../types'

const W = 344
const H = 196
const M = { top: 14, right: 16, bottom: 30, left: 34 }
const SURFACE = '#191a1e'

const niceStep = (span: number) => {
  const raw = span / 3
  const pow = 10 ** Math.floor(Math.log10(raw))
  const n = raw / pow
  return (n < 1.5 ? 1 : n < 3.5 ? 2.5 : n < 7.5 ? 5 : 10) * pow
}

export default function AltChart({
  options,
  currentId,
  pickedId,
  onPick,
}: {
  options: Option[]
  currentId: string
  pickedId: string | null
  onPick: (id: string) => void
}) {
  const [hover, setHover] = useState<string | null>(null)
  const pts = useMemo(
    () => options.filter((o) => o.price_usd !== null && o.rating !== null) as (Option & { price_usd: number; rating: number })[],
    [options],
  )
  const unplotted = options.length - pts.length
  if (pts.length < 2) return null

  const maxPrice = Math.max(...pts.map((p) => p.price_usd))
  const xMax = maxPrice * 1.08
  const yMin = Math.min(3.5, Math.floor(Math.min(...pts.map((p) => p.rating)) * 2) / 2)
  const yMax = 5
  const maxReviews = Math.max(1, ...pts.map((p) => p.review_count))
  const x = (v: number) => M.left + (v / xMax) * (W - M.left - M.right)
  const y = (v: number) => M.top + (1 - (v - yMin) / (yMax - yMin)) * (H - M.top - M.bottom)
  const r = (n: number) => 4.5 + Math.sqrt(n / maxReviews) * 6.5

  const step = niceStep(xMax)
  const xTicks: number[] = []
  for (let v = 0; v <= xMax; v += step) xTicks.push(v)
  const yTicks: number[] = []
  for (let v = yMin; v <= yMax + 1e-6; v += 0.5) yTicks.push(v)

  const frontier = pts.filter((p) => p.best_value).sort((a, b) => a.price_usd - b.price_usd)
  const active = pts.find((p) => p.id === hover) ?? pts.find((p) => p.id === pickedId) ?? null
  // Largest first so small dots stay clickable on top.
  const ordered = [...pts].sort((a, b) => b.review_count - a.review_count)

  return (
    <figure className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Price against customer rating for each alternative. The list below has the same data." className="block overflow-visible">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="rgb(255 255 255 / 0.07)" strokeWidth={1} />
            <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="num" fontSize={10} fill="#8b8882">
              {t.toFixed(1)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={x(t)} y={H - M.bottom + 15} textAnchor="middle" className="num" fontSize={10} fill="#8b8882">
            {t === 0 ? '$0' : `$${t >= 1000 ? `${(t / 1000).toFixed(t % 1000 === 0 ? 0 : 1)}k` : t}`}
          </text>
        ))}
        <text x={M.left - 26} y={M.top - 4} fontSize={10} fill="#8b8882">
          Rating
        </text>
        <text x={W - M.right} y={H - 2} textAnchor="end" fontSize={10} fill="#8b8882">
          Price
        </text>

        {frontier.length > 1 && (
          <polyline
            points={frontier.map((p) => `${x(p.price_usd)},${y(p.rating)}`).join(' ')}
            fill="none"
            stroke="#aeaaa3"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            strokeLinecap="round"
          />
        )}

        {ordered.map((p) => {
          const cx = x(p.price_usd)
          const cy = y(p.rating)
          const rad = r(p.review_count)
          const isCurrent = p.id === currentId
          const isPicked = p.id === pickedId
          const lit = hover === p.id || isPicked
          return (
            <g key={p.id}>
              {(isCurrent || isPicked) && (
                <circle cx={cx} cy={cy} r={rad + 4} fill="none" stroke={isCurrent ? '#9fe3f0' : '#eeeae3'} strokeWidth={1.5} />
              )}
              {p.fit === 'fits' && (
                <circle cx={cx} cy={cy} r={rad} fill={lit || isCurrent ? '#eeeae3' : '#c9c5bd'} stroke={SURFACE} strokeWidth={2} />
              )}
              {p.fit === 'unsure' && (
                <circle cx={cx} cy={cy} r={rad - 0.75} fill={SURFACE} stroke="#f2b95a" strokeWidth={1.5} strokeDasharray="2.5 2.5" />
              )}
              {p.fit === 'no_fit' && (
                <g stroke="#ff6b5e" strokeWidth={1.5} strokeLinecap="round">
                  <circle cx={cx} cy={cy} r={rad - 0.75} fill={SURFACE} />
                  <path d={`M${cx - rad * 0.38} ${cy - rad * 0.38}L${cx + rad * 0.38} ${cy + rad * 0.38}M${cx + rad * 0.38} ${cy - rad * 0.38}L${cx - rad * 0.38} ${cy + rad * 0.38}`} />
                </g>
              )}
              <circle
                cx={cx}
                cy={cy}
                r={Math.max(rad + 6, 13)}
                fill="transparent"
                style={{ cursor: 'pointer' }}
                onPointerEnter={() => setHover(p.id)}
                onPointerLeave={() => setHover((h) => (h === p.id ? null : h))}
                onClick={() => onPick(p.id)}
              >
                <title>{`${p.name}: ${usd(p.price_usd)}, rated ${p.rating} by ${p.review_count}`}</title>
              </circle>
            </g>
          )
        })}

        {frontier[0] && (
          <text
            x={x(frontier[0].price_usd) + r(frontier[0].review_count) + 6}
            y={y(frontier[0].rating) + 14}
            fontSize={10}
            fill="#aeaaa3"
          >
            best value
          </text>
        )}
      </svg>

      {active && (
        <div
          className="glass-solid pointer-events-none absolute z-10 w-[190px] rounded-sm px-2.5 py-2"
          style={{
            left: Math.min(Math.max(8, (x(active.price_usd) / W) * 100 - 26), 46) + '%',
            top: y(active.rating) > H / 2 ? 0 : undefined,
            bottom: y(active.rating) > H / 2 ? undefined : 34,
          }}
        >
          <div className="truncate text-xs font-semibold text-fg">{splitName(active.name)[0]}</div>
          <div className="num mt-0.5 text-xs text-fg-2">
            {usd(active.price_usd)}, {active.rating.toFixed(1)} from {active.review_count}
          </div>
          <div className="mt-1 text-2xs leading-snug text-fg-3">{active.why || active.fit}</div>
        </div>
      )}

      <figcaption className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-fg-3">
        <span className="flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden>
            <circle cx="5" cy="5" r="4" fill="#c9c5bd" />
          </svg>
          fits
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="10" height="10" aria-hidden>
            <circle cx="5" cy="5" r="3.5" fill="none" stroke="#ff6b5e" strokeWidth="1.5" />
            <path d="M3.5 3.5l3 3M6.5 3.5l-3 3" stroke="#ff6b5e" strokeWidth="1.2" />
          </svg>
          does not fit
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="12" height="12" aria-hidden>
            <circle cx="6" cy="6" r="5" fill="none" stroke="#9fe3f0" strokeWidth="1.5" />
          </svg>
          in the room now
        </span>
        <span>bigger dot, more reviews</span>
        {unplotted > 0 && <span>{unplotted} without a rating or price are in the list</span>}
      </figcaption>
    </figure>
  )
}
