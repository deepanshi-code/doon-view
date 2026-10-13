import { Link } from "react-router-dom"
import { ArrowRight } from "lucide-react"
import { api } from "../api"
import { monthLabel } from "../format"
import { useFetch } from "../useFetch"
import Ridgeline from "../components/Ridgeline"
import DemoNotice from "../components/DemoNotice"

const FOCUS = "mussoorie"

function DestinationCard({ c }) {
  return (
    <Link to={`/d/${c.slug}`} className="group block rounded-2xl border border-line bg-surface p-6 hover:border-line-strong">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-highlight">Hotels and homestays</p>
        {c.demo && <DemoNotice compact />}
      </div>
      <p className="mt-1 font-display text-2xl font-extrabold tracking-tight">{c.name}</p>
      <p className="mt-2 text-sm text-muted tabular">
        {c.properties} properties · {c.reviews.toLocaleString()} reviews · {monthLabel(c.from)} to {monthLabel(c.to)}
      </p>
      <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-accent">
        Open <ArrowRight size={15} aria-hidden="true" className="group-hover:translate-x-0.5 transition-transform motion-reduce:transition-none" />
      </span>
    </Link>
  )
}

export default function Home() {
  const { data, error, loading } = useFetch(() => api.clusters(), "clusters")
  const focus = data?.find((c) => c.slug === FOCUS)
  return (
    <>
      <section className="relative overflow-hidden">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-36 sm:pb-44">
          <p className="text-sm font-semibold text-highlight">Uttarakhand · hotels and homestays</p>
          <h1 className="mt-3 font-display text-[2.6rem] sm:text-6xl font-extrabold leading-[1.02] tracking-[-0.03em] max-w-3xl text-balance">
            Mussoorie, as its visitors see it.
          </h1>
          <p className="mt-5 text-lg text-muted max-w-2xl leading-relaxed">
            Every recent review of every hotel in the town, read together: where each property leads, where it lags,
            and which problems the whole destination shares.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
            {focus
              ? <Link to={`/d/${FOCUS}`} className="inline-flex items-center gap-2 min-h-11 px-5 rounded-xl bg-accent text-on-accent font-semibold">Open Mussoorie <ArrowRight size={16} aria-hidden="true" /></Link>
              : <Link to="/method" className="inline-flex items-center gap-2 min-h-11 px-5 rounded-xl bg-accent text-on-accent font-semibold">How it works <ArrowRight size={16} aria-hidden="true" /></Link>}
            {focus && <Link to="/method" className="font-semibold text-accent underline underline-offset-4">How it works</Link>}
          </div>
        </div>
        <Ridgeline className="absolute bottom-0 inset-x-0 w-full h-28 sm:h-36" />
      </section>

      <section aria-labelledby="dest-h" className="max-w-6xl mx-auto px-4 sm:px-6 py-16">
        <h2 id="dest-h" className="font-display text-3xl font-extrabold tracking-tight">Mussoorie</h2>
        <div className="mt-6" aria-live="polite" aria-busy={loading}>
          {loading && <p className="text-muted">Loading…</p>}
          {error && <p role="alert" className="text-danger">Couldn&rsquo;t reach the API: {error.message}</p>}
          {data && (focus ? <DestinationCard c={focus} /> : (
            <p className="rounded-xl border border-line bg-surface p-5">
              <strong>Mussoorie&rsquo;s 2025&ndash;26 reviews are being collected.</strong>{" "}
              <span className="text-muted">The analysis appears here as soon as they&rsquo;re in.</span>
            </p>
          ))}
        </div>
      </section>
    </>
  )
}
