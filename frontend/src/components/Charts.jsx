import { VERDICT } from "../verdicts"

/**
 * A hotel's gap to the market on one aspect, in percentage points, as a bar from a zero line: left is below the
 * market, right is above. The scale is fixed at +-50 points so bars compare across rows. The signed number sits
 * on the other side of the zero line, so it never runs off a narrow screen. Decorative: the row text has it all.
 */
export function GapBar({ aspect }) {
  const { verdict, satisfaction, market_satisfaction: market } = aspect
  if (verdict === "too_few" || satisfaction == null || market == null) {
    return <div className="relative h-7" aria-hidden="true"><span className="absolute left-1/2 inset-y-0 w-px bg-line-strong" /></div>
  }
  const gap = Math.round((satisfaction - market) * 100)
  const width = `${Math.min(50, Math.abs(gap))}%`
  const below = gap < 0
  return (
    <div className="relative h-7" aria-hidden="true">
      <span className="absolute left-1/2 inset-y-0 w-px bg-line-strong" />
      <span className={`absolute top-[9px] h-2.5 ${verdict === "in_line" ? "bg-neutral" : VERDICT[verdict].fill}`}
        style={below ? { right: "50%", width } : { left: "50%", width }} />
      <span className={`absolute top-1 text-[13px] font-semibold tabular ${VERDICT[verdict].tone}`}
        style={below ? { left: "calc(50% + 8px)" } : { right: "calc(50% + 8px)" }}>
        {gap > 0 ? "+" : ""}{gap}
      </span>
    </div>
  )
}

/** Satisfaction as a dot with its 95% range as a line, on 0-100%. No background track. Decorative. */
export function RangeDot({ value, interval }) {
  const [low, high] = interval
  return (
    <div className="relative h-6" aria-hidden="true">
      <span className="absolute top-[11px] h-0.5 bg-band" style={{ left: `${low * 100}%`, width: `${Math.max(0.5, (high - low) * 100)}%` }} />
      {value != null && <span className="absolute top-[7px] size-2.5 -ml-[5px] rounded-full bg-accent" style={{ left: `${value * 100}%` }} />}
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
    <svg viewBox={`0 0 ${w} ${h}`} className="w-40 h-9 shrink-0 text-muted" aria-hidden="true">
      <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
