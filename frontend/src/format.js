// Small pure helpers, unit-tested in format.test.js

export const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`)

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

/** "2025-03" -> "Mar 2025" */
export function monthLabel(ym) {
  if (!ym) return "–"
  const [y, m] = ym.split("-").map(Number)
  return MONTHS[m - 1] ? `${MONTHS[m - 1]} ${y}` : ym
}

// The periods offered on a destination. "since" is inclusive; an empty since means all time.
export const PERIODS = [
  { id: "recent", label: "2025–26", since: "2025-01" },
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
