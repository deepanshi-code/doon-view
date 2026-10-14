// Small pure helpers, unit-tested in format.test.js

export const pct = (x) => (x == null ? "-" : `${Math.round(x * 100)}%`)

/** "8% (2% to 35%)": a rate with its 95% range, as text. */
export const rateText = (value, [low, high]) => `${pct(value)} (${pct(low)} to ${pct(high)})`

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** "2025-03" -> "Mar 2025" */
export function monthLabel(ym) {
  if (!ym) return "-"
  const [y, m] = ym.split("-").map(Number)
  return MONTHS[m - 1] ? `${MONTHS[m - 1]} ${y}` : ym
}

// The periods offered on a destination. "since" is inclusive; an empty since means all time.
export const PERIODS = [
  { id: "recent", label: "2025-26", since: "2025-01" },
  { id: "all", label: "All time", since: "" },
]

/**
 * The headline for a destination: its most-complained-about aspect, and whether that is the whole market's
 * problem (an opportunity) or specific properties' problem. Null when nothing was complained about.
 */
export function headline(aspects) {
  const top = aspects.find((a) => a.complaints > 0)
  if (!top) return null
  const scope = top.shared_issue
    ? "The whole market shares it: a gap for whoever fixes it first."
    : top.properties_judged
      ? `It varies by property: ${top.properties_that_differ} of ${top.properties_judged} differ clearly from the rest.`
      : "Too few mentions per property yet to say who it affects."
  return { aspect: top.label, per100: top.complaints_per_100_reviews, scope }
}

const PLATFORMS = { google: "Google", makemytrip: "MakeMyTrip", tripadvisor: "Tripadvisor", booking: "Booking.com",
  agoda: "Agoda" }

/** "Google 152, Tripadvisor 98 and Agoda 40": where a property's reviews come from, largest first. */
export function sourcesLine(sources) {
  return listJoin(Object.entries(sources || {}).map(([k, n]) => `${PLATFORMS[k] || k} ${n.toLocaleString("en-IN")}`))
}

/** ["a", "b", "c"] -> "a, b and c" */
export function listJoin(items) {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`
}

/**
 * What a property should do, from its benchmark rows: lagging aspects first (its own problem), then market-wide
 * issues it doesn't already beat (fix first, stand out), then what it leads on (say it in listings).
 */
export function actions(aspects) {
  const gap = (a) => (a.market_satisfaction ?? 0) - (a.satisfaction ?? 0)
  return {
    actNow: aspects.filter((a) => a.verdict === "lags").sort((a, b) => gap(b) - gap(a)),
    market: aspects.filter((a) => a.shared_issue && a.verdict !== "leads" && a.verdict !== "lags"),
    edge: aspects.filter((a) => a.verdict === "leads").sort((a, b) => gap(a) - gap(b)),
  }
}

/** Column headers where seven aspects share a phone-width row. */
export const ASPECT_SHORT = { cleanliness: "Clean", location: "Place", wifi: "WiFi", host: "Staff", value: "Value",
  amenities: "Room", food: "Food", booking: "Book" }

const NOUN = { host: "staff", wifi: "WiFi", amenities: "rooms", value: "value for money" }
const noun = (a) => NOUN[a.aspect] ?? a.label.toLowerCase()
const gapPts = (a) => Math.round(((a.satisfaction ?? 0) - (a.market_satisfaction ?? 0)) * 100)

/**
 * A hotel's answer in one sentence, from actions(): what is its own problem, what the town shares, where it leads.
 * Returned as segments so the page can colour the three key phrases; `tone` is "lags", "leads", "market" or none.
 */
export function summary({ actNow, market, edge }) {
  const out = []
  if (actNow.length) {
    out.push({ text: actNow.length === 1 ? "One problem is yours" : `${actNow.length} problems are yours`, tone: "lags" })
    out.push({ text: `: ${listJoin(actNow.map((a) => `${noun(a)}, ${-gapPts(a)} points below the market`))}.` })
  } else out.push({ text: "Nothing is clearly yours to fix." })
  if (market.length) {
    out.push({ text: ` ${listJoin(market.map((a) => a.label))} is a complaint ` })
    out.push({ text: "the whole town shares", tone: "market" })
    out.push({ text: "." })
  }
  if (edge.length) {
    out.push({ text: " " })
    out.push({ text: "You lead", tone: "leads" })
    out.push({ text: ` on ${listJoin(edge.map(noun))}.` })
  }
  return out
}

const ORDINAL = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"]

/**
 * Where one property stands among the market on one aspect, from the market grid. Only properties with enough
 * mentions are placed; with fewer than three of them, or the property itself short of mentions, there is no place.
 */
export function standing(grid, aspect, pid) {
  const points = grid.properties
    .map((p) => ({ id: p.id, cell: p.cells[aspect] }))
    .filter((p) => p.cell && p.cell.verdict !== "too_few" && p.cell.satisfaction != null)
    .map((p) => ({ id: p.id, value: p.cell.satisfaction }))
    .sort((a, b) => b.value - a.value)
  const i = points.findIndex((p) => p.id === pid)
  const place = i >= 0 && points.length >= 3 ? ORDINAL[i] ?? `${i + 1}th` : null
  return { points, place, of: points.length }
}

const LABELLERS ={ model: "a fine-tuned review model", gemini: "Gemini", heuristic: "keyword rules" }

/** Who labelled the reviews, in the build's own counts, so the page never claims a labeller that wasn't used. */
export function labelNote(sources) {
  const parts = Object.entries(sources || {})
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `${LABELLERS[k] || k} (${n.toLocaleString("en-IN")})`)
  if (!parts.length) return "Labels by a fine-tuned review model."
  return `Labels by ${parts.length > 1 ? parts.slice(0, -1).join(", ") + " and " + parts.at(-1) : parts[0]}.`
}
