/** Shown wherever synthetic data is on screen, so no number is mistaken for a finding about Mussoorie. */
export default function DemoNotice() {
  return (
    <p role="note" className="border-l-2 border-accent pl-4 text-sm">
      <strong className="font-semibold">Demo data.</strong>{" "}
      <span className="text-muted">Generated reviews of fictional properties, used to show how the prototype works. Nothing here is a finding about Mussoorie.</span>
    </p>
  )
}
