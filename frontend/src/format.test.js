import { describe, expect, it } from "vitest"
import { headline, monthLabel, pct } from "./format"
import { periodQuery } from "./api"

describe("format", () => {
  it("formats rates and months, with a dash for missing values", () => {
    expect(pct(0.645)).toBe("65%")
    expect(pct(null)).toBe("–")
    expect(monthLabel("2025-03")).toBe("Mar 2025")
    expect(monthLabel(null)).toBe("–")
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
})
