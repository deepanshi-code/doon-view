import { pct } from "../format"

/** Satisfaction with its 95% range, and optionally the rest of the market as a tick. The text says it all too. */
export function RangeBar({ value, interval, market, label }) {
  const [low, high] = interval
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 min-w-0">
      <div className="relative h-2.5 flex-1 min-w-32 rounded-full bg-line" aria-hidden="true">
        <div className="absolute inset-y-0 rounded-full bg-band" style={{ left: `${low * 100}%`, width: `${Math.max(1, (high - low) * 100)}%` }} />
        {value != null && <div className="absolute -inset-y-1 w-1 rounded-full bg-accent" style={{ left: `calc(${value * 100}% - 2px)` }} />}
        {market != null && <div className="absolute -inset-y-1.5 w-0.5 bg-ink" style={{ left: `${market * 100}%` }} />}
      </div>
      <span className="text-sm tabular whitespace-nowrap">
        <span className="sr-only">{label}: </span><strong className="font-semibold">{pct(value)}</strong>
        <span className="ml-1 text-xs text-muted">({pct(low)}–{pct(high)}{market != null ? `, market ${pct(market)}` : ""})</span>
      </span>
    </div>
  )
}

/** Quarterly complaint rate. Decorative: the sentence beside it carries the meaning. */
export function Spark({ points }) {
  const pts = points.filter((p) => p.complaint_rate != null)
  if (pts.length < 2) return null
  const w = 160, h = 36
  const line = pts.map((p, i) => `${(i / (pts.length - 1)) * w},${h - p.complaint_rate * h}`).join(" ")
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-40 h-9 shrink-0 text-highlight" aria-hidden="true">
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.75" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
