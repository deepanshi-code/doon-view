import { describe, expect, it } from "vitest"
import { actions, headline, labelNote, monthLabel, pct, sourcesLine, standing, summary } from "./format"
import { periodQuery } from "./api"

describe("format", () => {
  it("formats rates and months, with a dash for missing values", () => {
    expect(pct(0.645)).toBe("65%")
    expect(pct(null)).toBe("-")
    expect(monthLabel("2025-03")).toBe("Mar 2025")
    expect(monthLabel(null)).toBe("-")
  })

  it("headline: first complained-about aspect, scoped as market-wide or property-specific", () => {
    const base = { label: "Food", complaints: 12, complaints_per_100_reviews: 9.5, properties_judged: 8,
      properties_that_differ: 3, shared_issue: false }
    expect(headline([{ ...base, complaints: 0, label: "WiFi" }, base])).toEqual({ aspect: "Food", per100: 9.5,
      scope: "It varies by property: 3 of 8 differ clearly from the rest." })
    expect(headline([{ ...base, shared_issue: true }]).scope).toMatch(/whole market/)
    expect(headline([{ ...base, properties_judged: 0 }]).scope).toMatch(/Too few/)
    expect(headline([{ ...base, complaints: 0 }])).toBeNull()
  })

  it("period query: empty since means all time, until only when set", () => {
    expect(periodQuery({ since: "2025-01" })).toBe("?since=2025-01")
    expect(periodQuery({ since: "" })).toBe("?since=")
    expect(periodQuery({ since: "2025-01", until: "2026-12" })).toBe("?since=2025-01&until=2026-12")
  })

  it("sorts a property's aspects into act now, market-wide and edge", () => {
    const a = (aspect, verdict, satisfaction, market, shared = false) =>
      ({ aspect, verdict, satisfaction, market_satisfaction: market, shared_issue: shared })
    const out = actions([a("host", "lags", 0.5, 0.9), a("rooms", "lags", 0.8, 0.85), a("value", "in_line", 0.5, 0.55, true),
      a("food", "leads", 0.98, 0.87), a("wifi", "too_few", 0, 0.5, true), a("clean", "lags", 0.3, 0.8, true)])
    expect(out.actNow.map((x) => x.aspect)).toEqual(["clean", "host", "rooms"])   // biggest gap first, shared or not
    expect(out.market.map((x) => x.aspect)).toEqual(["value", "wifi"])
    expect(out.edge.map((x) => x.aspect)).toEqual(["food"])
    expect(sourcesLine({ google: 1200, agoda: 3 })).toBe("Google 1,200 and Agoda 3")
    expect(sourcesLine({ google: 5, agoda: 3, booking: 1 })).toBe("Google 5, Agoda 3 and Booking.com 1")
    expect(sourcesLine(undefined)).toBe("")
  })

  it("places a property among those with enough mentions, and only when there are three or more", () => {
    const cell = (verdict, satisfaction) => ({ verdict, satisfaction })
    const grid = { properties: [
      { id: "a", cells: { food: cell("leads", 0.95), wifi: cell("too_few", 0) } },
      { id: "b", cells: { food: cell("in_line", 0.8), wifi: cell("lags", 0.1) } },
      { id: "c", cells: { food: cell("lags", 0.5), wifi: cell("too_few", 0.4) } },
      { id: "d", cells: { food: cell("too_few", 0.99) } },
    ] }
    expect(standing(grid, "food", "b")).toEqual({ points: [{ id: "a", value: 0.95 }, { id: "b", value: 0.8 },
      { id: "c", value: 0.5 }], place: "2nd", of: 3 })
    expect(standing(grid, "food", "d").place).toBeNull()        // its own mentions are too few
    expect(standing(grid, "wifi", "b")).toMatchObject({ place: null, of: 1 })   // one property is not a ranking
  })

  it("sums a hotel up in one sentence, naming its own problems, the town's and its lead", () => {
    const a = (aspect, label, satisfaction, market) => ({ aspect, label, satisfaction, market_satisfaction: market })
    const text = (s) => s.map((x) => x.text).join("")
    const wifi = a("wifi", "WiFi", 0.08, 0.57), value = a("value", "Value for money", 0.6, 0.56)
    const loc = a("location", "Location", 0.97, 0.89), staff = a("host", "Host & staff", 0.93, 0.89)
    expect(text(summary({ actNow: [wifi], market: [value], edge: [loc, staff] }))).toBe(
      "One problem is yours: WiFi, 49 points below the market. Value for money is a complaint the whole town shares. You lead on location and staff.")
    expect(text(summary({ actNow: [], market: [], edge: [] }))).toBe("Nothing is clearly yours to fix.")
    expect(summary({ actNow: [wifi, wifi], market: [], edge: [] })[0]).toEqual({ text: "2 problems are yours", tone: "lags" })
  })

  it("names only the labellers a build actually used", () => {
    expect(labelNote({ model: 1247, heuristic: 192, gemini: 0 }))
      .toBe("Labels by a fine-tuned review model (1,247) and keyword rules (192).")
    expect(labelNote({ gemini: 3, model: 10 })).toBe("Labels by a fine-tuned review model (10) and Gemini (3).")
    expect(labelNote(undefined)).toBe("Labels by a fine-tuned review model.")
  })
})
