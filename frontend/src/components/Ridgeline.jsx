// Layered Himalayan ridgelines: the theme's signature. Decorative only (aria-hidden), drawn in a band below the
// text so nothing sits on top of it, and static (no motion to reduce).

function ridge(base, amp, seed, width = 1200, height = 200) {
  let d = `M0 ${height} L0 ${base}`
  for (let x = 0; x <= width; x += 24) {
    const y = base - amp * Math.abs(Math.sin(x * 0.0055 * seed + seed)) - amp * 0.35 * Math.sin(x * 0.021 + seed)
    d += ` L${x} ${y.toFixed(1)}`
  }
  return `${d} L${width} ${height} Z`
}

const LAYERS = [
  { d: ridge(150, 95, 1.3), fill: "var(--ridge-1)", opacity: 0.1 },
  { d: ridge(170, 70, 2.1), fill: "var(--ridge-2)", opacity: 0.12 },
  { d: ridge(188, 40, 3.7), fill: "var(--ridge-1)", opacity: 0.16 },
]

export default function Ridgeline({ className = "" }) {
  return (
    <svg viewBox="0 0 1200 200" preserveAspectRatio="none" aria-hidden="true" className={className}>
      {LAYERS.map((l) => <path key={l.d.length + l.opacity} d={l.d} fill={l.fill} fillOpacity={l.opacity} />)}
    </svg>
  )
}

/** A three-peak mark for the header and favicon. */
export function Mark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--ink)" />
      <path d="M4 24 L11 13 L15 18 L20 9 L28 24 Z" fill="var(--accent)" />
      <path d="M4 24 L11 17 L16 21 L20 15 L28 24 Z" fill="var(--highlight)" fillOpacity=".85" />
    </svg>
  )
}
