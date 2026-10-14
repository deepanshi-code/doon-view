// The Doon View mark: one deodar cedar (Uttarakhand's hill forest) on a rounded square, in the accent colour.
// The favicon is the same drawing with resolved colours (public/favicon.svg).

function deodar(x, base, w, h) {
  const tier = (top, bottom, half) => `M${x} ${base - h * top} L${x - w * half} ${base - h * bottom} L${x + w * half} ${base - h * bottom} Z`
  return [tier(1, 0.55, 0.32), tier(0.78, 0.33, 0.42), tier(0.56, 0.1, 0.5),
    `M${x - w * 0.06} ${base - h * 0.1} h${w * 0.12} v${h * 0.1} h${-w * 0.12} Z`].join(" ")
}

export default function Mark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path d={deodar(16, 28, 26, 24)} fill="var(--on-accent)" />
    </svg>
  )
}
