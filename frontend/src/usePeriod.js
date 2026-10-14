import { useSearchParams } from "react-router-dom"
import { PERIODS } from "./format"

/** The period lives in the URL (?period=all), so a hotel link, a reload or a shared link keeps it. */
export function usePeriod() {
  const [params, setParams] = useSearchParams()
  const period = PERIODS.find((p) => p.id === params.get("period")) ?? PERIODS[0]
  const setPeriod = (id) => setParams(id === PERIODS[0].id ? {} : { period: id }, { replace: true })
  const search = period.id === PERIODS[0].id ? "" : `?period=${period.id}`
  return { period, setPeriod, search }
}
