import { Link } from "react-router-dom"
import { ASPECT_SHORT, pct } from "../format"
import { VERDICT } from "../verdicts"

// Every hotel against the rest of the market on every aspect, best to worst. Desktop: a real table; each cell is
// the rate, a square in the verdict colour and the verdict word, so it reads in grayscale. Phones: one strip of
// squares per hotel under shared column labels, so nothing scrolls sideways. A hotel's name opens its page.

function Cell({ cell }) {
  if (!cell) return <span className="text-muted">-</span>
  const v = VERDICT[cell.verdict]
  const strong = cell.verdict === "leads" || cell.verdict === "lags"
  return (
    <span className="block">
      <span className="block font-medium tabular">{cell.verdict === "too_few" ? "-" : pct(cell.satisfaction)}</span>
      <span className={`inline-flex items-center gap-1.5 text-xs ${strong ? `font-medium ${v.tone}` : "text-muted"}`}>
        <i aria-hidden="true" className={`inline-block size-2 ${v.fill} ${strong ? "" : "outline outline-line-strong"}`} />{v.word}
      </span>
    </span>
  )
}

export default function MarketGrid({ grid, slug, search }) {
  const shared = new Set(grid.shared_issues)
  const href = (id) => `/d/${slug}/h/${id}${search}`
  return (
    <section aria-labelledby="grid-h">
      <h2 id="grid-h" className="text-2xl font-semibold tracking-tight">Who leads, who lags</h2>
      <p className="mt-1.5 max-w-[68ch] text-muted">
        Each hotel against the other {grid.properties.length - 1}, best first. The number is the share of mentions that
        are positive; ahead or behind only when the gap holds at 95%.
      </p>

      <table className="mt-7 hidden md:table w-full text-[15px]">
        <caption className="sr-only">Verdict per hotel and aspect, hotels ordered from most aspects ahead to most behind</caption>
        <thead>
          <tr className="border-b border-line-strong text-left align-bottom text-[13px] text-muted">
            <th scope="col" className="pb-2.5 pr-4 font-normal">Hotel</th>
            {grid.aspects.map((a) => (
              <th key={a.aspect} scope="col" className="pb-2.5 px-2 font-normal">
                {a.label}{shared.has(a.aspect) && <span className="block text-ink font-medium">shared by the town</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.properties.map((p) => (
            <tr key={p.id} className="align-top">
              <th scope="row" className="py-3 pr-4 text-left font-normal">
                <Link to={href(p.id)} className="inline-flex min-h-6 items-center font-medium text-ink hover:underline underline-offset-3">{p.name}</Link>
                <span className="block text-xs text-muted tabular">{p.leads} ahead, {p.lags} behind</span>
              </th>
              {grid.aspects.map((a) => <td key={a.aspect} className={`py-3 px-2 ${shared.has(a.aspect) ? "bg-hatch" : ""}`}><Cell cell={p.cells[a.aspect]} /></td>)}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-6 md:hidden">
        <div aria-hidden="true" className="grid grid-cols-7 gap-1 border-b border-line-strong pb-2 text-center text-[11px] text-muted">
          {grid.aspects.slice(0, 7).map((a) => <span key={a.aspect}>{ASPECT_SHORT[a.aspect] ?? a.label}</span>)}
        </div>
        <ul>
          {grid.properties.map((p) => (
            <li key={p.id} className="py-3">
              <Link to={href(p.id)} className="flex min-h-11 items-baseline justify-between gap-3 font-medium text-ink underline-offset-3 hover:underline">
                {p.name}<span className="shrink-0 text-xs font-normal text-muted tabular">{p.leads} ahead, {p.lags} behind</span>
              </Link>
              <ul className="mt-1 grid grid-cols-7 gap-1">
                {grid.aspects.slice(0, 7).map((a) => {
                  const v = VERDICT[p.cells[a.aspect]?.verdict ?? "too_few"]
                  return <li key={a.aspect}><span className="sr-only">{a.label}: {v.word}</span><i aria-hidden="true" className={`block h-5 ${v.fill}`} /></li>
                })}
              </ul>
            </li>
          ))}
        </ul>
      </div>
      {shared.size > 0 && (
        <p className="mt-4 text-[13px] text-muted">Shaded column: a complaint the whole town shares. A quarter or more of its mentions are complaints and hardly any hotel differs, so whoever fixes it first stands out.</p>
      )}
    </section>
  )
}
