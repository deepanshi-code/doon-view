import { useState } from "react"
import { useParams } from "react-router-dom"
import { api } from "../api"
import { headline, labelNote, monthLabel, pct, rateText } from "../format"
import { useFetch } from "../useFetch"
import { usePeriod } from "../usePeriod"
import { RangeDot, Spark } from "../components/Charts"
import { PeriodSwitch } from "../components/Period"
import DemoNotice from "../components/DemoNotice"
import MarketGrid from "../components/MarketGrid"
import PageBand from "../components/PageBand"

// The town, for whoever looks after it (and an owner sizing up rivals). Reading order: 1. the town; 2. its
// headline finding in one sentence; 3. who leads and who lags (a hotel's name opens its page); 4. what visitors
// say about each aspect across the town, with how sure we are.

function Quotes({ title, items, tone }) {
  return (
    <div>
      <h3 className="text-sm text-muted">{title}</h3>
      {items?.length ? (
        <ul className="mt-2 space-y-3">
          {items.map((q) => <li key={q} className={`border-l-2 pl-3 leading-snug ${tone}`}>&ldquo;{q}&rdquo;</li>)}
        </ul>
      ) : <p className="mt-2 text-muted">No clear one-sentence example.</p>}
    </div>
  )
}

const COLS = "md:grid-cols-[13rem_minmax(0,1fr)_7rem_9rem]"

function Aspects({ data }) {
  const [open, setOpen] = useState(() => new Set())
  const toggle = (k) => setOpen((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n })
  return (
    <section aria-labelledby="say-h">
      <h2 id="say-h" className="text-2xl font-semibold tracking-tight">What visitors say</h2>
      <p className="mt-1.5 max-w-[68ch] text-muted">Across the whole town, most complaints first. The dot is the share of mentions that are positive; the line is where it could really be (95%).</p>
      <div className={`mt-7 hidden md:grid gap-x-6 border-b border-line-strong pb-2.5 text-[13px] text-muted ${COLS}`} aria-hidden="true">
        <span>Aspect</span><span className="flex justify-between"><span>0%</span><span>100% positive</span></span>
        <span className="text-right">Positive</span><span className="text-right">Complaints per 100</span>
      </div>
      <ul>
        {data.aspects.map((a) => {
          const isOpen = open.has(a.aspect)
          const tp = a.trend?.turning_point
          const em = a.trend?.emerging
          return (
            <li key={a.aspect} className="py-3">
              <div className={`grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1.5 items-center ${COLS}`}>
                <div>
                  <p className="font-medium">{a.label}</p>
                  {a.shared_issue && <p className="text-[13px]">shared by the town</p>}
                  <button type="button" onClick={() => toggle(a.aspect)} aria-expanded={isOpen} aria-controls={`say-${a.aspect}`}
                    className="mt-0.5 min-h-6 text-sm text-accent underline underline-offset-3">{isOpen ? "Hide quotes" : "Quotes and trend"}</button>
                </div>
                <div className="col-span-2 row-start-2 md:col-span-1 md:row-start-auto"><RangeDot value={a.satisfaction} interval={a.interval} /></div>
                <p className="hidden md:block text-right tabular"><span className="font-semibold">{pct(a.satisfaction)}</span></p>
                <p className="col-start-2 row-start-1 md:col-start-auto md:row-start-auto text-right tabular">
                  <span className="font-semibold">{a.complaints_per_100_reviews}</span><span className="md:hidden text-[13px] text-muted"> complaints per 100</span>
                </p>
              </div>
              {isOpen && (
                <div id={`say-${a.aspect}`} className="mt-4 pb-3 grid gap-6 md:grid-cols-2">
                  <Quotes title="Complaints" items={a.complaint_quotes} tone="border-danger" />
                  <Quotes title="Praise" items={a.praise_quotes} tone="border-success" />
                  <div className="md:col-span-2 flex flex-wrap items-center gap-4 text-sm">
                    <Spark points={a.trend.points} />
                    <div className="space-y-1">
                      {!tp && !em && <p className="text-muted">Complaints held steady over the period.</p>}
                      {em && <p className="font-medium text-danger">Rising: complaints at {pct(em.recent_rate)} since {monthLabel(em.since)}, up from {pct(em.earlier_rate)} the year before.</p>}
                      {tp && <p>Changed in {monthLabel(tp.month)}: complaints went from {pct(tp.complaints_before)} to {pct(tp.complaints_after)}.</p>}
                    </div>
                  </div>
                  <p className="md:col-span-2 text-[13px] text-muted tabular">
                    Positive {rateText(a.satisfaction, a.interval)} of {a.mentions.toLocaleString("en-IN")} mentions. {a.properties_that_differ} of {a.properties_judged} hotels with enough mentions differ clearly from the rest.
                  </p>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      <p className="mt-4 max-w-[75ch] text-[13px] text-muted">{data.trend_note}</p>
    </section>
  )
}

export default function Destination() {
  const { slug } = useParams()
  const { period, setPeriod, search } = usePeriod()
  const { data, error, loading } = useFetch(() => api.destination(slug, period), `${slug}/${period.id}`)
  const grid = useFetch(() => api.grid(slug, period), `grid/${slug}/${period.id}`)
  const top = data && data.reviews > 0 && headline(data.aspects)

  return (
    <div className="pb-20">
      <PageBand hotels={grid.data?.properties ?? []}>
        <div className="glass rise rounded-panel p-5 sm:p-7 grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <h1 className="text-[2.1rem] sm:text-5xl font-semibold leading-[1.05] tracking-[-0.03em]">{data?.name ?? "Mussoorie hotels"}</h1>
            {data && (
              <p className="mt-3 text-muted tabular">
                {data.properties.length} hotels and {data.reviews.toLocaleString("en-IN")} reviews{data.reviews > 0 && `, ${monthLabel(data.from)} to ${monthLabel(data.to)}`}.
              </p>
            )}
          </div>
          <PeriodSwitch period={period} onChange={setPeriod} />
        </div>
      </PageBand>

      <div className="mx-auto max-w-[1240px] px-4 sm:px-6">
        <div aria-live="polite" aria-busy={loading}>
          {loading && <div aria-hidden="true" className="mt-5 space-y-5 motion-safe:animate-pulse"><div className="glass h-28 rounded-panel" /><div className="glass h-96 rounded-panel" /></div>}
          {error && <p role="alert" className="glass mt-5 rounded-panel p-6 text-lg">{error.status === 404 ? "No reviews for this destination yet." : `Couldn't load it: ${error.message}`}</p>}
        </div>

        {data && (
          <>
            {data.demo && <div className="mt-6"><DemoNotice /></div>}
            {data.reviews === 0 ? (
              <p className="glass mt-5 rounded-panel p-6 text-lg">
                No reviews from this period yet. <button type="button" onClick={() => setPeriod("all")} className="text-accent underline underline-offset-3">Show all years</button>
              </p>
            ) : (
              <>
                {top && (
                  <p className="glass rise rise-2 mt-5 rounded-panel p-6 sm:p-8 text-xl sm:text-[1.7rem] leading-snug tracking-[-0.012em]">
                    Visitors complain most about <span className="font-semibold text-accent">{top.aspect.toLowerCase()}</span>: {top.per100} complaints per 100 reviews. <span className="text-muted">{top.scope}</span>
                  </p>
                )}
                {grid.error && <p role="alert" className="glass mt-5 rounded-panel p-6 text-danger">Couldn&rsquo;t load the market table: {grid.error.message}</p>}
                {grid.data && grid.data.properties.length > 1 && (
                  <div className="glass rise rise-3 mt-5 rounded-panel p-5 sm:p-7"><MarketGrid grid={grid.data} slug={slug} search={search} /></div>
                )}
                <div className="glass mt-5 rounded-panel p-5 sm:p-7"><Aspects data={data} /></div>
              </>
            )}
            <p className="mt-8 max-w-[75ch] text-[13px] text-muted">Source: {data.source} {labelNote(data.label_sources)} Quotes are single sentences with reviewer names removed.</p>
          </>
        )}
      </div>
    </div>
  )
}

