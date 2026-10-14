import { useRef } from "react"

/**
 * A panel that tilts a few degrees toward the pointer, like a card held in space. Transform only; off for touch
 * and under reduced motion (the CSS transition is gated, and pointer events are ignored when motion is reduced).
 */
export default function Tilt({ as: Tag = "div", max = 6, className = "", children, ...rest }) {
  const ref = useRef(null)
  const reduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches
  const move = (e) => {
    if (e.pointerType !== "mouse" || reduce() || !ref.current) return
    const r = ref.current.getBoundingClientRect()
    const x = (e.clientX - r.left) / r.width - 0.5
    const y = (e.clientY - r.top) / r.height - 0.5
    ref.current.style.transform = `perspective(1200px) rotateX(${(-y * max).toFixed(2)}deg) rotateY(${(x * max).toFixed(2)}deg) translateZ(0)`
  }
  const leave = () => { if (ref.current) ref.current.style.transform = "" }
  return (
    <Tag ref={ref} onPointerMove={move} onPointerLeave={leave}
      className={`motion-safe:transition-transform motion-safe:duration-500 motion-safe:ease-[cubic-bezier(0.2,0.8,0.2,1)] will-change-transform ${className}`} {...rest}>
      {children}
    </Tag>
  )
}
