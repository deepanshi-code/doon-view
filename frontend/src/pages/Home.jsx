import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { ArrowRight } from "lucide-react"
import { api } from "../api"
import { PERIODS, listJoin } from "../format"
import { useFetch } from "../useFetch"
import { VERDICT } from "../verdicts"
import DemoNotice from "../components/DemoNotice"
import Relief from "../components/Relief"
import Tilt from "../components/Tilt"

// Reading order: 1. the owner's question; 2. what Doon View does, in one sentence; 3. the way in (pick your
// hotel, compare); 4. the seven hotels at a glance. Behind it all, the ridge with one pin per hotel: the same
// seven, coloured by their net verdict.

const FOCUS = "mussoorie"

function Pick({ hotels }) {
  const navigate = useNavigate()
  const [id, setId] = useState("")
  const [error, setError] = useState(false)
  const submit = (e) => {
    e.preventDefault()
    if (!id) { setError(true); return }
    navigate(`/d/${FOCUS}/h/${id}`)
  }
  return (
    <form onSubmit={submit} noValidate className="mt-7">
      <label htmlFor="pick" className="mb-1.5 block text-sm text-muted">Your hotel</label>
      <div className="flex flex-wrap gap-2.5">
        <select id="pick" value={id} onChange={(e) => { setId(e.target.value); setError(false) }}
          aria-invalid={error} aria-describedby={error ? "pick-err" : undefined}
          className={`h-12 min-w-0 flex-1 basis-56 rounded-ctl border bg-surface px-3.5 text-ink ${error ? "border-danger border-[1.5px]" : "border-line-strong"}`}>
          <option value="">Choose a hotel</option>
          {hotels.map((h) => <option key={h.id} value={h.id}>{h.name}</option>)}
        </select>
        <button type="submit" className="h-12 px-5 rounded-ctl bg-accent text-on-accent font-semibold shadow-[0_10px_24px_-12px_var(--accent)] motion-safe:transition-transform hover:-translate-y-px active:translate-y-px">
          Compare
        </button>
      </div>
      {error && <p id="pick-err" role="alert" className="mt-2 text-sm text-danger">Choose a hotel to compare it with the other {hotels.length - 1}.</p>}
    </form>
  )
}

function HotelsCard({ grid }) {
  return (
    <Tilt as="section" aria-labelledby="hotels-h" className="glass rise rise-2 rounded-panel p-5 sm:p-6 lg:justify-self-end w-full lg:max-w-[30rem]">
      <h2 id="hotels-h" className="text-[17px] font-semibold tracking-tight">Mussoorie hotels, 2025-26</h2>
      <p className="text-[13px] text-muted">Seven aspects each, against the other {grid.properties.length - 1} hotels</p>
      <ul className="mt-3">
        {grid.properties.map((p) => (
          <li key={p.id} className="border-t border-line">
            <Link to={`/d/${FOCUS}/h/${p.id}`} className="group grid grid-cols-[minmax(0,1fr)_auto_7.5rem] items-center gap-3 py-2.5 text-ink">
              <span className="truncate font-medium group-hover:text-accent transition-colors">{p.name}</span>
              <span className="text-[13px] tabular">
                {p.leads ? <span className="font-semibold text-success">{p.leads} ahead</span>
                  : p.lags ? <span className="font-semibold text-danger">{p.lags} behind</span> : <span className="text-muted">in line</span>}
              </span>
              <span aria-hidden="true" className="grid grid-cols-7 gap-[3px]">
                {grid.aspects.map((a) => {
                  const v = p.cells[a.aspect]?.verdict ?? "too_few"
                  return <i key={a.aspect} className={`block h-3.5 rounded-[3px] ${v === "in_line" ? "bg-line" : VERDICT[v].fill}`} />
                })}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <Link to={`/d/${FOCUS}`} className="mt-3 inline-flex items-center gap-1.5 min-h-10 text-sm font-medium text-accent">
        Compare all hotels <ArrowRight size={15} aria-hidden="true" />
      </Link>
    </Tilt>
  )
}

/**
 * The difference from a star rating (or plain sentiment), on real data: the market's weakest hotel, what its
 * stars say, and what Doon View says about the same reviews. Picked from the data, never hard-coded.
 */
function StarsVersusUs({ grid }) {
  // The lowest-rated hotel: where "the stars say something is wrong" is true, and the lever matters most
  const weakest = [...grid.properties].filter((p) => p.rating != null).sort((a, b) => a.rating - b.rating)[0]
  const { data: b } = useFetch(() => (weakest ? api.benchmark(FOCUS, weakest.id, PERIODS[0]) : Promise.resolve(null)), `home-example/${weakest?.id}`)
  if (!b?.impact?.rating) return null
  const first = b.impact.aspects[0]
  const lags = b.aspects.filter((a) => a.verdict === "lags").map((a) => a.label.toLowerCase())
  const shared = b.aspects.filter((a) => a.shared_issue && a.verdict !== "lags").map((a) => a.label.toLowerCase())
  return (
    <section aria-labelledby="diff-h" className="mx-auto max-w-[1240px] px-4 sm:px-6 pt-16 sm:pt-24">
      <h2 id="diff-h" className="text-3xl sm:text-4xl font-semibold leading-tight tracking-[-0.02em] text-balance">What a star rating can&rsquo;t tell you</h2>
      <p className="mt-2 text-lg text-muted">{b.property.name}, the lowest-rated hotel in town in 2025-26, read two ways.</p>
      <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="glass rounded-panel p-6 sm:p-8">
          <p className="text-sm text-muted">Its stars say</p>
          <p className="mt-2 tabular"><span className="text-5xl font-semibold tracking-tight">{b.impact.rating.toFixed(2)}</span> <span className="text-lg text-muted">against {b.impact.market_rating.toFixed(2)} in town</span></p>
          <p className="mt-4 text-lg text-muted">
            {b.impact.rating < b.impact.market_rating ? "Something is wrong." : "Doing fine on average."} Not what, not whether the whole town has it too, not what to fix first.
          </p>
        </div>
        <div className="glass rounded-panel p-6 sm:p-8">
          <p className="text-sm text-muted">Doon View says, from the same {b.property.reviews} reviews</p>
          <ul className="mt-3 space-y-3 text-lg leading-snug">
            {first && <li><span className="font-semibold text-accent">Fix {first.label.toLowerCase()} first.</span> Getting no more complaints than the market is worth about {first.gain.toFixed(2)} stars, more than anything else.</li>}
            {lags.length > 0 && <li><span className="font-semibold text-danger">Yours to fix:</span> {listJoin(lags)}, each clearly below the other hotels.</li>}
            {shared.length > 0 && <li><span className="font-semibold">Not yours alone:</span> {listJoin(shared)} is a complaint the whole town shares.</li>}
          </ul>
          <Link to={`/d/${FOCUS}/h/${b.property.id}`} className="mt-5 inline-flex items-center gap-1.5 min-h-10 font-medium text-accent">
            Open {b.property.name} <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </div>
    </section>
  )
}

export default function Home() {
  const clusters = useFetch(() => api.clusters(), "clusters")
  const focus = clusters.data?.find((c) => c.slug === FOCUS)
  const grid = useFetch(() => (focus ? api.grid(FOCUS, PERIODS[0]) : Promise.resolve(null)), `home-grid/${focus ? "y" : "n"}`)
  const hotels = grid.data?.properties ?? []
  return (
    <>
      <section className="relative isolate min-h-dvh overflow-hidden">
        <Relief hotels={hotels} className="absolute inset-0 -z-10 [mask-image:linear-gradient(to_bottom,black_78%,transparent)]" />
        <div className="mx-auto grid min-h-dvh max-w-[1240px] items-end gap-6 px-4 sm:px-6 pt-[42vh] lg:pt-32 pb-8 sm:pb-10 lg:grid-cols-[minmax(0,32rem)_minmax(0,1fr)]">
          <div className="glass rise rounded-panel p-6 sm:p-8">
            <h1 className="text-[2.4rem] sm:text-[3.4rem] font-semibold leading-[1.02] tracking-[-0.035em] text-balance">Is this issue ours, or the market&rsquo;s?</h1>
            <p className="mt-4 max-w-[36ch] text-lg text-muted">
              Every recent review of every hotel in Mussoorie, sorted into your problems, the town&rsquo;s problems and your strengths.
            </p>
            {hotels.length > 0 && <Pick hotels={hotels} />}
            <Link to="/method" className="mt-4 inline-flex items-center min-h-10 text-[15px] text-accent underline underline-offset-3">How it works</Link>
            {focus?.demo && <div className="mt-4"><DemoNotice /></div>}
          </div>
          <div aria-live="polite" aria-busy={clusters.loading || Boolean(focus && grid.loading)} className="lg:justify-self-end w-full lg:max-w-[30rem]">
            {(clusters.loading || (focus && grid.loading)) && <div aria-hidden="true" className="glass h-80 rounded-panel motion-safe:animate-pulse" />}
            {clusters.error && <p role="alert" className="glass rounded-panel p-5">Couldn&rsquo;t reach the API: {clusters.error.message}</p>}
            {clusters.data && !focus && (
              <p className="glass rounded-panel p-5"><strong className="font-semibold">Mussoorie&rsquo;s 2025-26 reviews are being collected.</strong> <span className="text-muted">The hotels appear here once they&rsquo;re in.</span></p>
            )}
            {grid.error && <p role="alert" className="glass rounded-panel p-5">Couldn&rsquo;t load the hotels: {grid.error.message}</p>}
            {grid.data && <HotelsCard grid={grid.data} />}
          </div>
        </div>
      </section>

      {grid.data && <StarsVersusUs grid={grid.data} />}

      <section aria-labelledby="town-h" className="mx-auto grid max-w-[1240px] gap-8 px-4 sm:px-6 py-16 sm:py-20 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-center">
        <figure className="m-0">
          <img src="/img/mussoorie-valley-1600.webp" srcSet="/img/mussoorie-valley-800.webp 800w, /img/mussoorie-valley-1600.webp 1600w"
            sizes="(min-width: 1024px) 700px, 100vw" width="1600" height="1200" loading="lazy" decoding="async"
            alt="Forested ridges around Mussoorie under low cloud" className="block w-full h-auto aspect-[4/3] object-cover rounded-panel" />
          <figcaption className="mt-2 text-xs text-muted">
            Photo: <a href="https://commons.wikimedia.org/wiki/File:Mussoorie_5.jpg" className="underline underline-offset-2">Gannu03</a>,{" "}
            <a href="https://creativecommons.org/licenses/by-sa/4.0/" className="underline underline-offset-2">CC BY-SA 4.0</a>, resized
          </figcaption>
        </figure>
        <div>
          <h2 id="town-h" className="text-3xl sm:text-4xl font-semibold leading-tight tracking-[-0.02em] text-balance">One town, read as a market</h2>
          <p className="mt-4 max-w-[46ch] text-lg text-muted">
            Seven Mall Road hotels, {focus ? focus.reviews.toLocaleString("en-IN") : "thousands of"} reviews on five platforms. A complaint every hotel hears is a gap
            in the market; one only you hear is yours to fix.
          </p>
          <Link to={`/d/${FOCUS}`} className="mt-6 inline-flex items-center gap-2 h-11 px-5 rounded-ctl border border-line-strong font-medium text-ink hover:border-accent hover:text-accent transition-colors">
            Compare all hotels <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
      </section>
    </>
  )
}
