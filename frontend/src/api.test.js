import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { api, onSlow } from "./api"

const ok = (body) => ({ ok: true, status: 200, json: async () => body })
const status = (code) => ({ ok: false, status: code, statusText: `HTTP ${code}`, json: async () => ({}) })

describe("API client while the host wakes", () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it("retries 503s and connection failures, flags the wait as slow, then clears it", async () => {
    const fetch = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(status(503))
      .mockResolvedValueOnce(ok([{ slug: "mussoorie" }]))
    vi.stubGlobal("fetch", fetch)
    const seen = []
    const stop = onSlow((v) => seen.push(v))
    const done = api.clusters()
    await vi.advanceTimersByTimeAsync(10000)
    await expect(done).resolves.toEqual([{ slug: "mussoorie" }])
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(seen).toEqual([false, true, false])
    stop()
  })

  it("does not retry a real error such as 404, and never flags a fast failure as slow", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(status(404)))
    const seen = []
    const stop = onSlow((v) => seen.push(v))
    await expect(api.clusters()).rejects.toMatchObject({ status: 404 })
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(seen).toEqual([false])
    stop()
  })

  it("keeps sending since= for all time to the API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok({})))
    await api.destination("mussoorie", { since: "" })
    expect(fetch).toHaveBeenCalledWith("/api/clusters/mussoorie?since=")
  })

  it("gives up after about 75 seconds when the host never answers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")))
    const done = api.clusters()
    const settled = expect(done).rejects.toThrow("Failed to fetch")
    await vi.advanceTimersByTimeAsync(80000)
    await settled
  })
})

describe("static mode (no API)", () => {
  const json = (body) => ({ ok: true, status: 200, headers: new Headers({ "content-type": "application/json" }), json: async () => body })
  const html = () => ({ ok: true, status: 200, headers: new Headers({ "content-type": "text/html" }), json: async () => { throw new SyntaxError("<") } })
  let s
  beforeEach(async () => {
    vi.stubEnv("VITE_STATIC_DATA", "1")
    vi.resetModules()
    s = await import("./api")
  })
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules() })

  it("maps each request onto the file export_static.py writes for that period", () => {
    expect(s.STATIC).toBe(true)
    expect(s.staticPath("/clusters")).toBe("/data/clusters.json")
    expect(s.staticPath("/clusters/mussoorie", { since: "" })).toBe("/data/clusters/mussoorie/all.json")
    expect(s.staticPath("/clusters/mussoorie/grid", { since: "2025-01" })).toBe("/data/clusters/mussoorie/2025-01/grid.json")
    expect(s.staticPath("/clusters/mussoorie/properties/hotel-deep", { since: "" }))
      .toBe("/data/clusters/mussoorie/all/properties/hotel-deep.json")
  })

  it("reads the static file and never calls the API", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ slug: "mussoorie" })))
    await expect(s.api.destination("mussoorie", { since: "2025-01" })).resolves.toEqual({ slug: "mussoorie" })
    expect(fetch).toHaveBeenCalledWith("/data/clusters/mussoorie/2025-01.json")
  })

  it("turns a stored API error into the same error the API gives", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: { status: 404, detail: "not in this period" } })))
    await expect(s.api.benchmark("mussoorie", "hotel-deep", { since: "2025-01" }))
      .rejects.toMatchObject({ status: 404, message: "not in this period" })
  })

  it("treats a missing file (the SPA's index.html, or a 404) as not found", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(html()).mockResolvedValueOnce({ ok: false, status: 404, headers: new Headers() }))
    await expect(s.api.destination("nowhere", { since: "" })).rejects.toMatchObject({ status: 404 })
    await expect(s.api.destination("nowhere", { since: "" })).rejects.toMatchObject({ status: 404 })
  })
})
