import { FlaskConical } from "lucide-react"

/** Shown wherever synthetic data is on screen, so no number is mistaken for a finding about Mussoorie. */
export default function DemoNotice({ compact = false }) {
  if (compact) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-highlight px-2.5 py-0.5 text-xs font-semibold text-highlight">
        <FlaskConical size={13} aria-hidden="true" /> Demo data
      </span>
    )
  }
  return (
    <div role="note" className="flex items-start gap-3 rounded-2xl border border-highlight bg-surface p-4 text-sm">
      <FlaskConical size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-highlight" />
      <p>
        <strong>Demo data.</strong>{" "}
        <span className="text-muted">These are generated reviews of fictional properties, used to show how the prototype works. Nothing here is a finding about Mussoorie. Real reviews replace them once collected.</span>
      </p>
    </div>
  )
}
