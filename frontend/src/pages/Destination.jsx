import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { ArrowDown, ArrowUp, Equal, HelpCircle, Users } from "lucide-react"
import { api } from "../api"
import { PERIODS, headline, monthLabel, pct } from "../format"
import { useFetch } from "../useFetch"
import { RangeBar, Spark } from "../components/Charts"

// Reading order: 1. headline finding, 2. what visitors say per aspect (with how sure we are), 3. one property
// against the rest of its market.

const VERDICT = {
  lags: { label: "Behind the market", icon: ArrowDown, tone: "text-danger" },
  leads: { label: "Ahead of the market", icon: ArrowUp, tone: "text-success" },
  in_line: { label: "In line with the market", icon: Equal, tone: "text-muted" },
  too_few: { label: "Too few mentions to tell", icon: HelpCircle, tone: "text-muted" },
}

function PeriodSwitch({ period, onChange }) {
  return (
    <fieldset className="inline-flex rounded-xl border border-line bg-surface p-1">
      <legend className="sr-only">Reviews from</legend>
      {PERIODS.map((p) => (
        <label key={p.id} className={`cursor-pointer min-h-10 px-4 inline-flex items-center rounded-lg text-sm font-semibold has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-focus ${period.id === p.id ? "bg-accent text-on-accent" : "text-muted hover:text-ink"}`}>
          <input type="radio" name="period" value={p.id} checked={period.id === p.id} onChange={() => onChange(p.id)} className="sr-only" />
          {p.label}
        </label>
      ))}
    </fieldset>
  )
}

function Trend({ trend }) {
  const tp = trend?.turning_point
  const em = trend?.emerging
  return (
    <div className="flex items-center gap-4">
      <Spark points={trend.points} />
      <div className="text-sm space-y-1">
        {!tp && !em && <p className="text-muted">No significant change in this period.</p>}
        {em && <p className="font-semibold text-danger">Emerging: complaints at {pct(em.recent_rate)} since {monthLabel(em.since)}, up from {pct(em.earlier_rate)} the year before.</p>}
        {tp && <p>Changed in <strong>{monthLabel(tp.month)}</strong>: complaints went from {pct(tp.complaints_before)} to {pct(tp.complaints_after)} ({tp.direction}). What happened that month?</p>}
      </div>
    </div>
  )
}

function Quotes({ items, tone }) {
  if (!items?.length) return <p className="text-sm text-muted">No clear one-sentence example.</p>
  return (
    <ul className="space-y-2">
      {items.map((q) => <li key={q} className={`text-sm leading-relaxed border-l-2 pl-3 ${tone}`}>&ldquo;{q}&rdquo;</li>)}
    </ul>
  )
}

function Benchmark({ slug, properties, period }) {
  const [chosen, setChosen] = useState(null)
  const pid = properties.some((p) => p.id === chosen) ? chosen : properties[0]?.id
  const { data, error, loading } = useFetch(
    () => (pid ? api.benchmark(slug, pid, period) : Promise.resolve(null)), `${slug}/${pid}/${period.id}`)
  return (
    <section aria-labelledby="bench-h" className="mt-20">
      <h2 id="bench-h" className="font-display text-3xl font-extrabold tracking-tight">One property against its market</h2>
      <p className="mt-2 max-w-2xl text-muted">A verdict only when the property&rsquo;s whole range sits above or below the other properties&rsquo; rate. Few mentions, no verdict.</p>
      {properties.length === 0 ? <p className="mt-6 text-muted">No property has reviews in this period.</p> : (
        <>
          <label htmlFor="bench-prop" className="mt-6 block text-sm font-semibold">Property</label>
          <select id="bench-prop" value={pid} onChange={(e) => setChosen(e.target.value)}
            className="mt-2 w-full sm:w-96 min-h-11 rounded-xl border border-line-strong bg-surface px-3 text-ink">
            {properties.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.reviews} reviews)</option>)}
          </select>
          <div className="mt-6" aria-live="polite" aria-busy={loading}>
            {loading && <p className="text-muted">Comparing…</p>}
            {error && <p role="alert" className="text-danger">Couldn&rsquo;t load this property: {error.message}</p>}
            {data && (
              <ul className="rounded-2xl border border-line bg-surface divide-y divide-line">
                {data.aspects.map((a) => {
                  const v = VERDICT[a.verdict]
                  const Icon = v.icon
                  return (
                    <li key={a.aspect} className="p-5 grid gap-3 md:grid-cols-[13rem_minmax(0,1fr)]">
                      <div>
                        <p className="font-semibold">{a.label}</p>
                        <p className={`mt-1 inline-flex items-center gap-1 text-sm font-semibold ${v.tone}`}><Icon size={15} aria-hidden="true" />{v.label}</p>
                        {a.shared_issue && <p className="mt-1 text-xs text-muted">The whole market complains about this</p>}
                      </div>
                      <div className="space-y-3 min-w-0">
                        <RangeBar value={a.satisfaction} interval={a.interval} market={a.market_satisfaction} label={`${a.label} satisfaction`} />
                        <p className="text-xs text-muted tabular">{a.mentions} mentions</p>
                        {a.verdict !== "too_few" && <Trend trend={a.trend} />}
                        {a.complaint_quotes.length > 0 && <Quotes items={a.complaint_quotes.slice(0, 2)} tone="border-danger" />}
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  )
}

export default function Destination() {
  const { slug } = useParams()
  const [params, setParams] = useSearchParams()
  const period = PERIODS.find((p) => p.id === params.get("period")) ?? PERIODS[0]
  const setPeriod = (id) => setParams(id === PERIODS[0].id ? {} : { period: id }, { replace: true })
  const { data, error, loading } = useFetch(() => api.destination(slug, period), `${slug}/${period.id}`)
  const top = data && headline(data.aspects)

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
      <p className="text-sm font-semibold"><Link to="/" className="text-accent underline underline-offset-4">Home</Link></p>
      {loading && <p className="mt-8 text-muted" aria-live="polite">Reading the reviews…</p>}
      {error && <p role="alert" className="mt-8 text-danger">{error.status === 404 ? "No reviews for this destination yet." : `Couldn’t load it: ${error.message}`}</p>}
      {data && (
        <>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h1 className="font-display text-4xl sm:text-5xl font-extrabold tracking-[-0.03em] text-balance">{data.name}</h1>
              <p className="mt-2 text-muted tabular">
                {data.properties.length} properties · {data.reviews.toLocaleString()} reviews
                {data.reviews > 0 && ` · ${monthLabel(data.from)} to ${monthLabel(data.to)}`}
              </p>
            </div>
            <PeriodSwitch period={period} onChange={setPeriod} />
          </div>

          {data.reviews === 0 ? (
            <p className="mt-10 rounded-2xl border border-line bg-surface p-6">
              No reviews from this period yet. <button type="button" onClick={() => setPeriod("all")} className="font-semibold text-accent underline underline-offset-4">Show all time</button>
            </p>
          ) : (
            <>
              <div className="mt-8 rounded-2xl border border-line bg-surface p-6 sm:p-8 border-l-4 border-l-accent">
                <p className="text-sm font-semibold text-highlight">Headline finding</p>
                {top ? (
                  <p className="mt-2 font-display text-xl sm:text-2xl leading-snug text-balance">
                    Visitors complain most about <strong>{top.aspect.toLowerCase()}</strong>: {top.per100} complaints per 100 reviews. {top.scope}
                  </p>
                ) : <p className="mt-2 font-display text-xl">No aspect draws complaints in this period.</p>}
              </div>

              <section aria-labelledby="say-h" className="mt-16">
                <h2 id="say-h" className="font-display text-3xl font-extrabold tracking-tight">What visitors say</h2>
                <p className="mt-2 max-w-2xl text-muted">Satisfaction is the share of an aspect&rsquo;s mentions that are positive; the shaded band is where it could really be (95%). Most complaints first. Open one for quotes and trend.</p>
                <ul className="mt-6 space-y-3">
                  {data.aspects.map((a) => (
                    <li key={a.aspect} className="rounded-2xl border border-line bg-surface">
                      <details>
                        <summary className="cursor-pointer list-none p-5 grid gap-3 md:grid-cols-[13rem_minmax(0,1fr)_12rem] md:items-center rounded-2xl">
                          <span className="font-semibold">{a.label}</span>
                          <RangeBar value={a.satisfaction} interval={a.interval} label={`${a.label} satisfaction`} />
                          <span className="text-sm md:text-right tabular">
                            {a.complaints_per_100_reviews} complaints / 100
                            {a.shared_issue && <span className="ml-2 inline-flex items-center gap-1 text-xs font-semibold text-highlight"><Users size={13} aria-hidden="true" />Market-wide</span>}
                          </span>
                        </summary>
                        <div className="px-5 pb-6 pt-5 border-t border-line grid gap-6 md:grid-cols-2">
                          <div className="space-y-3"><p className="text-sm font-semibold">Complaints</p><Quotes items={a.complaint_quotes} tone="border-danger" /></div>
                          <div className="space-y-3"><p className="text-sm font-semibold">Praise</p><Quotes items={a.praise_quotes} tone="border-success" /></div>
                          <div className="md:col-span-2"><Trend trend={a.trend} /></div>
                          <p className="md:col-span-2 text-xs text-muted tabular">{a.mentions.toLocaleString()} mentions · {a.properties_that_differ} of {a.properties_judged} properties with enough mentions differ clearly from the rest</p>
                        </div>
                      </details>
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-xs text-muted">{data.trend_note}</p>
              </section>

              <Benchmark slug={slug} properties={data.properties} period={period} />
            </>
          )}
          <p className="mt-16 text-xs text-muted">Source: {data.source} Labels by a fine-tuned review model (Gemini for short or Hindi-English reviews); quotes are single sentences with reviewer names removed.</p>
        </>
      )}
    </div>
  )
}
