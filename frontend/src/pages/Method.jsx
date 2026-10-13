// How the numbers are made, and what they can't tell you. Judges and officials should be able to check every claim.

const STEPS = [
  ["Collect", "Reviews for every property in a market (a hill town, a locality), with property, date and platform. Duplicates across platforms are counted once; reviewer names are removed."],
  ["Label", "A fine-tuned review model (DeBERTa-v3, run on CPU) labels sentiment and seven aspects. Reviews too short for it, or written in Hindi-English, go to Gemini, with names replaced by placeholders before they leave the server."],
  ["Compare", "Each property's satisfaction on each aspect, with a 95% range, against the rest of its market. Only recent reviews by default (2025–26), because a market changes."],
  ["Explain", "Shared weaknesses, turning points and emerging complaints, each with real one-sentence quotes as evidence."],
]

// The problem statement's categories, mapped onto what the model labels
const ASPECTS = [
  ["Food", "Food", "Meals and drinks: taste, variety, freshness, whether promised meals were served"],
  ["Room", "Amenities & room", "Size, comfort, beds, heating, hot water, whether things work"],
  ["Housekeeping, Cleanliness", "Cleanliness", "Hygiene of rooms, bathrooms and linen"],
  ["Staff", "Host & staff", "Behaviour, responsiveness, check-in and check-out"],
  ["Location", "Location", "Surroundings, views, access roads, parking, distance, outside noise"],
  ["Value for money", "Value for money", "Price against what was received, only when the guest links the two"],
  ["(extra)", "WiFi", "Connectivity and mobile signal: a frequent hill-station complaint"],
  ["Booking experience", "not yet", "Needs labelled examples; on the roadmap"],
]

const RULES = [
  ["Satisfaction", "Share of an aspect's mentions that are positive, with a Wilson 95% interval."],
  ["Ahead / behind", "Only when the property's whole interval sits above or below the rest of the market's rate."],
  ["Too few to tell", "Under 10 mentions of an aspect: no verdict, whatever the rate looks like."],
  ["Market-wide issue", "At least a quarter of mentions are complaints, and at most a fifth of properties differ significantly from the market."],
  ["Turning point", "The month that best splits an aspect's monthly complaint rate in two (likelihood ratio, significant at 1%)."],
  ["Emerging", "Complaints over the last three months clearly above the year before (z > 1.96)."],
]

export default function Method() {
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
      <p className="text-sm font-semibold text-highlight">Method</p>
      <h1 className="mt-3 font-display text-4xl sm:text-5xl font-extrabold tracking-[-0.03em] max-w-3xl text-balance">How every number on this site is made</h1>

      <ol className="mt-12 grid gap-6 md:grid-cols-2">
        {STEPS.map(([title, body], i) => (
          <li key={title} className="rounded-2xl border border-line bg-surface p-6">
            <p className="font-display text-4xl font-extrabold text-accent tabular" aria-hidden="true">{i + 1}</p>
            <h2 className="mt-2 font-display text-xl font-extrabold">{title}</h2>
            <p className="mt-2 text-muted leading-relaxed">{body}</p>
          </li>
        ))}
      </ol>

      <section aria-labelledby="aspects-h" className="mt-16">
        <h2 id="aspects-h" className="font-display text-3xl font-extrabold tracking-tight">Aspects</h2>
        <div className="mt-6 overflow-x-auto rounded-2xl border border-line bg-surface">
          <table className="w-full text-sm text-left">
            <thead className="text-muted"><tr><th scope="col" className="p-4">Problem statement</th><th scope="col" className="p-4">Labelled as</th><th scope="col" className="p-4">Covers</th></tr></thead>
            <tbody className="divide-y divide-line">
              {ASPECTS.map(([ps, ours, covers]) => (
                <tr key={ps}><td className="p-4 font-semibold">{ps}</td><td className="p-4">{ours}</td><td className="p-4 text-muted">{covers}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="rules-h" className="mt-16">
        <h2 id="rules-h" className="font-display text-3xl font-extrabold tracking-tight">The statistics</h2>
        <dl className="mt-6 grid gap-x-10 gap-y-6 md:grid-cols-2">
          {RULES.map(([term, def]) => (
            <div key={term} className="border-t border-line pt-4"><dt className="font-semibold">{term}</dt><dd className="mt-1 text-muted leading-relaxed">{def}</dd></div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="limits-h" className="mt-16 rounded-2xl border border-line bg-surface p-6 sm:p-8">
        <h2 id="limits-h" className="font-display text-2xl font-extrabold">What it can&rsquo;t tell you</h2>
        <ul className="mt-4 space-y-2 text-muted leading-relaxed list-disc pl-5">
          <li>Why a number moved. A turning point shows when; the operator knows what happened that month.</li>
          <li>Accuracy on Indian reviews is not yet measured against human labels; the model learned from international hotel reviews.</li>
          <li>Destination trends mix every property, so a change can come from which places were reviewed.</li>
          <li>Labels are per review, so a quote can occasionally sit under the wrong aspect.</li>
        </ul>
      </section>
    </div>
  )
}
