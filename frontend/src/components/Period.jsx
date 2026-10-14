import { PERIODS } from "../format"

/** Two-way period switch: radio inputs, so arrow keys move between them. Selected = accent fill. */
export function PeriodSwitch({ period, onChange }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm text-muted">Reviews from</legend>
      <div className="inline-flex h-11 overflow-hidden rounded-ctl border border-line-strong">
        {PERIODS.map((p) => (
          <label key={p.id} className={`cursor-pointer px-4 inline-flex items-center text-[15px] has-[:focus-visible]:outline-2 has-[:focus-visible]:-outline-offset-2 has-[:focus-visible]:outline-focus ${period.id === p.id ? "bg-accent text-on-accent font-medium" : "text-muted hover:text-ink"}`}>
            <input type="radio" name="period" value={p.id} checked={period.id === p.id} onChange={() => onChange(p.id)} className="sr-only" />
            {p.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}
