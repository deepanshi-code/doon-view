import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { api } from "../api"
import { actions, listJoin, monthLabel, pct, rateText, standing, summary } from "../format"
import { useFetch } from "../useFetch"
import { usePeriod } from "../usePeriod"
import { VERDICT } from "../verdicts"
import { GapBar, Spark } from "../components/Charts"
import { PeriodSwitch } from "../components/Period"
import DemoNotice from "../components/DemoNotice"
import PageBand from "../components/PageBand"

// One hotel, for its owner. Reading order: 1. the hotel and what it is compared with; 2. the answer in one
// sentence; 3. one ledger of every aspect, grouped by what to do about it (yours to fix, the town's problem,
// your edge, in line), each row showing the gap to the market, the two rates and the hotel's rank.

const PLATFORMS = { google: "Google", makemytrip: "MakeMyTrip", tripadvisor: "Tripadvisor", booking: "Booking.com", agoda: "Agoda" }

const GROUPS = [
  { key: "actNow", title: "Yours to fix", note: "Clearly below the other hotels here." },
  { key: "market", title: "Everyone's problem", note: "The whole town hears this. Fix it first and it becomes your edge." },
  { key: "edge", title: "Your edge", note: "Clearly ahead. Say it in your listings and replies." },
  { key: "rest", title: "In line with the market", note: "No clear difference either way." },
]

const COLS = "md:grid-cols-[13rem_minmax(0,1fr)_4.5rem_4.5rem_5.5rem]"

function Row({ a, grid, pid, open, onToggle }) {
  const v = VERDICT[a.verdict]
  const s = grid ? standing(grid, a.aspect, pid) : { place: null }
  const quotes = a.complaint_quotes ?? []
  const tp = a.trend?.turning_point
  const em = a.trend?.emerging
  const id = `more-${a.aspect}`
  return (
    <li className="-mx-3 px-3 py-3 rounded-ctl transition-colors hover:bg-line/30">
      <div className={`grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 items-center ${COLS}`}>
        <div>
          <p className="font-medium">{a.label}</p>
          <p className="text-[13px] text-muted tabular">{a.mentions} mentions, <span className={a.verdict === "leads" || a.verdict === "lags" ? v.tone : ""}>{v.word}{a.verdict === "leads" || a.verdict === "lags" ? ", 95% sure" : ""}</span></p>
          <button type="button" onClick={onToggle} aria-expanded={open} aria-controls={id}
            className="mt-0.5 min-h-6 text-sm text-accent underline underline-offset-3">{open ? "Hide detail" : "Detail and quotes"}</button>
        </div>
        <div className="col-span-2 row-start-2 md:col-span-1 md:row-start-auto"><GapBar aspect={a} /></div>
        <p className="hidden md:block text-right font-semibold tabular">{a.verdict === "too_few" ? "-" : pct(a.satisfaction)}</p>
        <p className="hidden md:block text-right tabular">{pct(a.market_satisfaction)}</p>
        <p className="col-start-2 row-start-1 md:col-start-auto md:row-start-auto text-right tabular">
          {s.place ? <><span className="font-semibold">{s.place}</span> <span className="text-[13px] text-muted">of {s.of}</span></> : <span className="text-[13px] text-muted">no rank</span>}
        </p>
      </div>
      {open && (
        <div id={id} className="mt-3 grid gap-4 md:grid-cols-[13rem_minmax(0,1fr)] md:gap-x-6 pb-3">
          <div className="text-sm text-muted tabular space-y-1">
            <p>You: {a.verdict === "too_few" ? "too few mentions" : rateText(a.satisfaction, a.interval)}</p>
            <p>Market: {pct(a.market_satisfaction)}</p>
          </div>
          <div className="space-y-4 max-w-[62ch]">
            {quotes.length ? quotes.map((q) => <blockquote key={q} className="text-lg leading-snug">&ldquo;{q}&rdquo;</blockquote>)
              : <p className="text-muted">No complaint quotes for this aspect.</p>}
            {a.verdict !== "too_few" && a.trend && (
              <div className="flex flex-wrap items-center gap-4 text-sm">
                <Spark points={a.trend.points} />
                <div className="space-y-1">
                  {!tp && !em && <p className="text-muted">Complaints held steady over the period.</p>}
                  {em && <p className="font-medium text-danger">Rising: complaints at {pct(em.recent_rate)} since {monthLabel(em.since)}, up from {pct(em.earlier_rate)} the year before.</p>}
                  {tp && <p>Changed in {monthLabel(tp.month)}: complaints went from {pct(tp.complaints_before)} to {pct(tp.complaints_after)}. What happened that month?</p>}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </li>
  )
}

function Ledger({ aspects, grid, pid }) {
  const [open, setOpen] = useState(() => new Set())
  const toggle = (k) => setOpen((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })
  const g = actions(aspects)
  const placed = new Set([...g.actNow, ...g.market, ...g.edge])
  const groups = { ...g, rest: aspects.filter((a) => !placed.has(a)) }
  return (
    <div className="mt-4">
      <div className={`hidden md:grid gap-x-6 pb-2 text-[13px] text-muted ${COLS}`} aria-hidden="true">
        <span /><span className="flex justify-between"><span>Below the market</span><span>Above</span></span>
        <span className="text-right">You</span><span className="text-right">Market</span><span className="text-right">Rank</span>
      </div>
      {GROUPS.filter((x) => groups[x.key].length).map((x) => (
        <section key={x.key} aria-labelledby={`g-${x.key}`} className="border-t border-line pt-5 pb-2">
          <div className="flex flex-col sm:flex-row sm:items-baseline gap-x-3 gap-y-0.5">
            <h2 id={`g-${x.key}`} className="text-lg font-semibold tracking-tight">{x.title}</h2>
            <p className="text-[15px] text-muted">{x.note}</p>
          </div>
          <ul className="mt-2">
            {groups[x.key].map((a) => <Row key={a.aspect} a={a} grid={grid} pid={pid} open={open.has(a.aspect)} onToggle={() => toggle(a.aspect)} />)}
          </ul>
        </section>
      ))}
    </div>
  )
}

const signed = (x, d = 2) => `${x >= 0 ? "+" : "-"}${Math.abs(x).toFixed(d)}`

/**
 * Where the hotel's stars go: aspects it gets more complaints about than the market, ranked by the rating it would
 * likely gain by matching the market (extra complaints per review x stars a complaint goes with). The answer to
 * "what should I fix first?", which sentiment alone can't give: a rare complaint can matter less than a common one.
 */
function Impact({ impact, competitors }) {
  if (!impact || impact.rating == null) return null
  const big = impact.aspects.filter((a) => a.gain >= 0.01)
  const small = impact.aspects.filter((a) => a.gain < 0.01)
  const scale = Math.max(0.1, ...big.map((a) => a.gain_interval[1]))
  const diff = impact.rating - impact.market_rating
  return (
    <section aria-labelledby="impact-h" className="glass rise rise-3 mt-5 rounded-panel p-5 sm:p-7">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div>
          <h2 id="impact-h" className="text-xl font-semibold tracking-tight">Where your stars go</h2>
          <p className="mt-1 max-w-[60ch] text-[15px] text-muted">What to fix first: the rating you would likely gain by getting no more complaints than the other {competitors} hotels.</p>
        </div>
        <p className="tabular text-right">
          <span className="text-3xl font-semibold tracking-tight">{impact.rating.toFixed(2)}</span>
          <span className="text-muted"> stars, market {impact.market_rating.toFixed(2)}</span>
          <span className={`block text-sm ${diff < 0 ? "text-danger" : "text-success"}`}>{signed(diff)} against the market, {impact.rated_reviews} guests&rsquo; ratings</span>
        </p>
      </div>
      {big.length ? (
        <ol className="mt-5 space-y-4">
          {big.map((a, i) => (
            <li key={a.aspect} className="grid gap-x-6 gap-y-1.5 md:grid-cols-[13rem_minmax(0,1fr)_8rem] md:items-center">
              <p className="font-medium"><span className="text-muted tabular">{i + 1}.</span> {a.label}</p>
              <div className="relative h-3" aria-hidden="true">
                <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${(a.gain / scale) * 100}%` }} />
                <span className="absolute top-1/2 h-px -translate-y-1/2 bg-accent/60" style={{ left: `${(a.gain_interval[0] / scale) * 100}%`, width: `${((a.gain_interval[1] - a.gain_interval[0]) / scale) * 100}%` }} />
              </div>
              <p className="tabular md:text-right"><span className="text-lg font-semibold text-accent">{signed(a.gain)}</span> <span className="text-sm text-muted">stars</span></p>
              <p className="md:col-start-2 md:col-span-2 text-[13px] text-muted tabular">
                {a.complaints_per_100} complaints per 100 reviews against {a.market_complaints_per_100} in the market; each goes with {a.stars_per_complaint.toFixed(1)} fewer stars.
              </p>
            </li>
          ))}
        </ol>
      ) : <p className="mt-5 text-[15px]">No aspect costs you a noticeable share of your rating against the market.</p>}
      {small.length > 0 && <p className="mt-4 text-[13px] text-muted">Under 0.01 stars each: {small.map((a) => a.label).join(", ")}.</p>}
      <p className="mt-4 text-[13px] text-muted">Estimated from guests&rsquo; own star ratings across Mussoorie (a model of stars on complaints per aspect, platform held apart). It shows association, not proof of cause; the thin line is the 95% range of each estimate.</p>
    </section>
  )
}

function Skeleton() {
  return (
    <div aria-hidden="true" className="mt-5 space-y-5 motion-safe:animate-pulse">
      <div className="glass h-32 rounded-panel" />
      <div className="glass h-96 rounded-panel" />
    </div>
  )
}

export default function Hotel() {
  const { slug, pid } = useParams()
  const navigate = useNavigate()
  const { period, setPeriod, search } = usePeriod()
  const grid = useFetch(() => api.grid(slug, period), `grid/${slug}/${period.id}`)
  const bench = useFetch(() => api.benchmark(slug, pid, period), `${slug}/${pid}/${period.id}`)
  const b = bench.data
  const hotels = grid.data?.properties ?? []
  const name = b?.property.name ?? hotels.find((p) => p.id === pid)?.name ?? "Hotel"
  const sources = b ? Object.keys(b.property.sources || {}).map((k) => PLATFORMS[k] ?? k) : []

  return (
    <div className="pb-20">
      <PageBand hotels={hotels} focus={pid}>
        <div className="glass rise rounded-panel p-5 sm:p-7 grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <Link to={`/d/${slug}${search}`} className="inline-flex items-center min-h-10 text-sm text-accent underline underline-offset-3">All Mussoorie hotels</Link>
            <h1 className="mt-1 text-[2.1rem] sm:text-5xl font-semibold leading-[1.05] tracking-[-0.03em] text-balance">{name}</h1>
            {b && (
              <p className="mt-3 max-w-[62ch] text-muted">
                {b.property.reviews.toLocaleString("en-IN")} reviews{sources.length ? ` from ${listJoin(sources)}` : ""}, read against {b.competitors} other hotels in Mussoorie.
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {hotels.length > 0 && (
              <div className="w-full sm:w-72">
                <label htmlFor="hotel-pick" className="mb-1.5 block text-sm text-muted">Hotel</label>
                <select id="hotel-pick" value={pid} onChange={(e) => navigate(`/d/${slug}/h/${e.target.value}${search}`)}
                  className="h-11 w-full rounded-ctl border border-line-strong bg-surface px-3 font-medium text-ink">
                  {hotels.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
            )}
            <PeriodSwitch period={period} onChange={setPeriod} />
          </div>
        </div>
      </PageBand>

      <div className="mx-auto max-w-[1240px] px-4 sm:px-6">
        <div aria-live="polite" aria-busy={bench.loading}>
          {bench.loading && <><p className="sr-only">Comparing with the market</p><Skeleton /></>}
          {bench.error && (
            <p role="alert" className="glass mt-5 rounded-panel p-6 text-lg">
              {bench.error.status === 404 ? "This hotel isn't in this market." : `Couldn't load this hotel: ${bench.error.message}`}{" "}
              <Link to={`/d/${slug}${search}`} className="text-accent underline underline-offset-3">See all hotels</Link>
            </p>
          )}
        </div>

        {b && (
          <>
            {b.demo && <div className="mt-6"><DemoNotice /></div>}
            <p className="glass rise rise-2 mt-5 rounded-panel p-6 sm:p-8 text-xl sm:text-[1.7rem] leading-snug tracking-[-0.012em]">
              {summary(actions(b.aspects)).map((s, i) => (
                <span key={i} className={s.tone === "lags" ? "font-semibold text-danger" : s.tone === "leads" ? "font-semibold text-success" : s.tone === "market" ? "font-semibold text-accent" : ""}>{s.text}</span>
              ))}
            </p>
            <Impact impact={b.impact} competitors={b.competitors} />
            <div className="glass mt-5 rounded-panel px-5 sm:px-7 pb-4 pt-2">
              <Ledger aspects={b.aspects} grid={grid.data} pid={pid} />
            </div>
            <p className="mt-8 max-w-[75ch] text-sm text-muted">
              Reviews from {period.id === "all" ? "all years" : period.label}. Ahead or behind only when the hotel&rsquo;s whole 95% range
              sits above or below the other hotels&rsquo; rate; under 10 mentions, no verdict. Rank needs at least three hotels with
              enough mentions. <Link to="/method" className="text-accent underline underline-offset-3">How it works</Link>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
