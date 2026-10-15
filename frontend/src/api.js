// Read-only API client. VITE_API_URL points at the API in production; in dev, Vite proxies /api.
const BASE = (() => {
  const url = import.meta.env.VITE_API_URL
  if (!url) return "/api"
  return url.endsWith("/api") ? url : `${url.replace(/\/$/, "")}/api`
})()

// The API runs on a free host that sleeps when idle and takes up to a minute to wake. While it wakes, requests
// can fail to connect or get a 502/503/504; those are retried quietly, and any request still pending after
// SLOW_MS is reported to onSlow() so the page can say what is happening instead of showing a silent skeleton.
export const SLOW_MS = 4000
const WAKE_MS = 75000
const RETRY_MS = 3000
const WAKING = new Set([502, 503, 504])
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const listeners = new Set()
let slow = 0
const setSlow = (delta) => { slow += delta; listeners.forEach((fn) => fn(slow > 0)) }

/** Call fn(true) while any request is slow, fn(false) when none are; returns an unsubscribe function. */
export function onSlow(fn) {
  listeners.add(fn)
  fn(slow > 0)
  return () => listeners.delete(fn)
}

async function get(path) {
  let flagged = false
  const timer = setTimeout(() => { flagged = true; setSlow(1) }, SLOW_MS)
  const started = Date.now()
  try {
    for (;;) {
      let res
      try {
        res = await fetch(`${BASE}${path}`)
      } catch (error) {
        if (Date.now() - started < WAKE_MS) { await sleep(RETRY_MS); continue }
        throw error
      }
      if (WAKING.has(res.status) && Date.now() - started < WAKE_MS) { await sleep(RETRY_MS); continue }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw Object.assign(new Error(typeof body.detail === "string" ? body.detail : res.statusText), { status: res.status })
      }
      return await res.json()
    }
  } finally {
    clearTimeout(timer)
    if (flagged) setSlow(-1)
  }
}

/** ?since=&until= for a period; since="" asks the API for all time. */
export function periodQuery({ since, until }) {
  const q = new URLSearchParams({ since: since ?? "" })
  if (until) q.set("until", until)
  return `?${q}`
}

// Static mode (VITE_STATIC_DATA=1): the site runs without the API, reading the responses that
// backend/scripts/export_static.py wrote for each period the UI offers. Same data, same errors.
export const STATIC = import.meta.env.VITE_STATIC_DATA === "1"

const notFound = (detail) => Object.assign(new Error(detail), { status: 404 })

/** The file export_static.py wrote for this request; "all" stands for since="" (all time). */
export function staticPath(path, { since } = {}) {
  if (path === "/clusters") return "/data/clusters.json"
  const [, slug, rest] = path.match(/^\/clusters\/([^/]+)(\/.*)?$/) ?? []
  if (!slug) throw notFound("Not found")
  const period = encodeURIComponent(since || "all")
  return rest ? `/data/clusters/${slug}/${period}${rest}.json` : `/data/clusters/${slug}/${period}.json`
}

async function getStatic(path, period) {
  const res = await fetch(staticPath(path, period))
  // A missing file comes back as the SPA's index.html (Pages) or a 404: either way, the API would have said 404
  if (!res.ok || !(res.headers.get("content-type") || "").includes("json")) throw notFound("Not found")
  const body = await res.json()
  if (body && body.error) throw Object.assign(new Error(body.error.detail), { status: body.error.status })
  return body
}

const read = (path, period) => (STATIC ? getStatic(path, period) : get(period ? `${path}${periodQuery(period)}` : path))

export const api = {
  clusters: () => read("/clusters"),
  destination: (slug, period) => read(`/clusters/${encodeURIComponent(slug)}`, period),
  grid: (slug, period) => read(`/clusters/${encodeURIComponent(slug)}/grid`, period),
  benchmark: (slug, id, period) =>
    read(`/clusters/${encodeURIComponent(slug)}/properties/${encodeURIComponent(id)}`, period),
}
