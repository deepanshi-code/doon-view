// How the numbers are made, and what they can't tell you. Judges and officials should be able to check every claim.

const STEPS = [
  ["Collect", "Reviews for every hotel in a market from Google, MakeMyTrip, Tripadvisor, Booking.com and Agoda, with hotel, date and platform. Duplicates are counted once; reviewer names are removed."],
  ["Label", "A fine-tuned review model (DeBERTa-v3, run on CPU) labels sentiment and seven aspects. Reviews too short for it, or written in Hindi-English, go to Gemini when it is configured, with names replaced by placeholders first; otherwise to keyword rules. The page footer says which labelled the data you see."],
  ["Compare", "Each hotel's satisfaction on each aspect, with a 95% range, against the rest of its market, shown as one table of who leads and who lags. Only recent reviews by default (2025-26), because a market changes."],
  ["Explain", "Shared weaknesses, turning points and emerging complaints, each with real one-sentence quotes as evidence."],
  ["Prioritise", "Which complaint costs a hotel the most stars, from guests' own ratings, so the owner knows what to fix first. Sentiment alone can't say this: a rare complaint can be the worst-rated aspect and still cost almost nothing."],
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
  ["Booking experience", "Booking & check-in", "Reservation honoured, price as shown, check-in and check-out, refunds (in testing: shown once a model labels it reliably)"],
]

const RULES = [
  ["Satisfaction", "Share of an aspect's mentions that are positive, with a Wilson 95% interval."],
  ["Ahead / behind", "Only when the property's whole interval sits above or below the rest of the market's rate."],
  ["Too few to tell", "Under 10 mentions of an aspect: no verdict, whatever the rate looks like."],
  ["Market-wide issue", "At least a quarter of mentions are complaints, and at most a fifth of properties differ significantly from the market."],
  ["Turning point", "The month that best splits an aspect's monthly complaint rate in two (likelihood ratio, significant at 1%)."],
  ["Emerging", "Complaints over the last three months clearly above the year before (z > 1.96)."],
  ["Where your stars go", "A linear model of each guest's own star rating on whether the review complains about each aspect, with platform held apart (Google rates higher than Booking.com). Each aspect's coefficient is the stars a complaint goes with. A hotel's likely gain on an aspect is its extra complaints per review, against the rest of the market, times that cost. Only aspects whose cost is clearly above zero (95%) are ranked. It is an association: it says where the stars go, not that fixing one thing will move them by exactly that much."],
]

const LIMITS = [
  "Why a number moved. A turning point shows when; the operator knows what happened that month.",
  "Accuracy on Indian reviews is not yet measured against human labels; the model learned partly from international hotel reviews.",
  "Destination trends mix every property, so a change can come from which places were reviewed.",
  "Labels are per review, so a quote can occasionally sit under the wrong aspect.",
]

export default function Method() {
  return (
    <div className="max-w-[1240px] mx-auto px-4 sm:px-6 pt-28 sm:pt-32 pb-20">
      <h1 className="max-w-[20ch] text-[2.1rem] sm:text-5xl font-semibold leading-[1.05] tracking-[-0.025em] text-balance">How every number here is made</h1>

      <dl className="glass rise mt-8 rounded-panel p-6 sm:p-8 grid gap-x-12 gap-y-8 md:grid-cols-2">
        {STEPS.map(([title, body]) => (
          <div key={title}>
            <dt className="text-lg font-semibold tracking-tight">{title}</dt>
            <dd className="mt-1.5 max-w-[60ch] text-muted leading-relaxed">{body}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="aspects-h" className="glass mt-5 rounded-panel p-6 sm:p-8">
        <h2 id="aspects-h" className="text-2xl font-semibold tracking-tight">Aspects</h2>
        <div className="mt-6 overflow-x-auto" tabIndex={0} role="region" aria-label="Aspects table, scrolls sideways on small screens">
          <table className="w-full min-w-[36rem] text-[15px] text-left">
            <thead className="text-[13px] text-muted"><tr className="border-b border-line-strong"><th scope="col" className="py-2.5 pr-6 font-normal">Problem statement</th><th scope="col" className="py-2.5 pr-6 font-normal">Labelled as</th><th scope="col" className="py-2.5 font-normal">Covers</th></tr></thead>
            <tbody>
              {ASPECTS.map(([ps, ours, covers]) => (
                <tr key={ps} className="align-top"><td className="py-3 pr-6 font-medium">{ps}</td><td className="py-3 pr-6">{ours}</td><td className="py-3 text-muted">{covers}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="rules-h" className="glass mt-5 rounded-panel p-6 sm:p-8">
        <h2 id="rules-h" className="text-2xl font-semibold tracking-tight">The statistics</h2>
        <dl className="mt-6 grid gap-x-12 gap-y-6 md:grid-cols-2">
          {RULES.map(([term, def]) => (
            <div key={term}><dt className="font-semibold">{term}</dt><dd className="mt-1 max-w-[60ch] text-muted leading-relaxed">{def}</dd></div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="limits-h" className="glass mt-5 rounded-panel p-6 sm:p-8">
        <h2 id="limits-h" className="text-2xl font-semibold tracking-tight">What it can&rsquo;t tell you</h2>
        <ul className="mt-4 max-w-[70ch] space-y-2 text-muted leading-relaxed list-disc pl-5">
          {LIMITS.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </section>

      <section aria-labelledby="credits-h" className="mt-10 px-1">
        <h2 id="credits-h" className="text-2xl font-semibold tracking-tight">Credits</h2>
        <p className="mt-3 max-w-[70ch] text-muted leading-relaxed">
          Home page photo: &ldquo;Mussoorie SM-6-2026-04-07&rdquo; (Mall Road) by SMarndi, from{" "}
          <a href="https://commons.wikimedia.org/wiki/File:Mussoorie_SM-6-2026-04-07.jpg" className="text-accent underline underline-offset-3">Wikimedia Commons</a>, licensed{" "}
          <a href="https://creativecommons.org/licenses/by-sa/4.0/" className="text-accent underline underline-offset-3">CC BY-SA 4.0</a>; resized and re-encoded, shared under the same licence.
        </p>
      </section>
    </div>
  )
}

