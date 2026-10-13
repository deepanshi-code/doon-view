// Read-only API client. VITE_API_URL points at the API in production; in dev, Vite proxies /api.
const BASE = (() => {
  const url = import.meta.env.VITE_API_URL
  if (!url) return "/api"
  return url.endsWith("/api") ? url : `${url.replace(/\/$/, "")}/api`
})()

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw Object.assign(new Error(typeof body.detail === "string" ? body.detail : res.statusText), { status: res.status })
  }
  return res.json()
}

/** ?since=&until= for a period; since="" asks the API for all time. */
export function periodQuery({ since, until }) {
  const q = new URLSearchParams({ since: since ?? "" })
  if (until) q.set("until", until)
  return `?${q}`
}

export const api = {
  clusters: () => get("/clusters"),
  destination: (slug, period) => get(`/clusters/${encodeURIComponent(slug)}${periodQuery(period)}`),
  benchmark: (slug, id, period) =>
    get(`/clusters/${encodeURIComponent(slug)}/properties/${encodeURIComponent(id)}${periodQuery(period)}`),
}
