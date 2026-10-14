import { useEffect, useRef, useState } from "react"

// The 3D relief behind the home hero and page titles. Decorative (aria-hidden): every pin's meaning is in the text.
// data-state on the wrapper says what is on screen: loading (poster), ready (moving), still (one frame, reduced
// motion), unavailable (poster; no WebGL). three.js is fetched only when this mounts.

function webglAvailable() {
  try {
    const c = document.createElement("canvas")
    return Boolean(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")))
  } catch {
    return false
  }
}

export default function Relief({ hotels, focus = null, framing = "hero", className = "" }) {
  const canvas = useRef(null)
  const [gl] = useState(webglAvailable)               // checked once: it can't change during a visit
  const [started, setState] = useState("loading")
  const state = gl ? started : "unavailable"
  const [theme, setTheme] = useState(() => document.documentElement.className)

  // Rebuild with the new colours when the theme toggles
  useEffect(() => {
    const mo = new MutationObserver(() => setTheme(document.documentElement.className))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    return () => mo.disconnect()
  }, [])

  const key = hotels.map((h) => `${h.id}:${h.leads}:${h.lags}`).join("|")
  useEffect(() => {
    if (!hotels.length || !gl) return undefined
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches
    let stop = null
    let cancelled = false
    import("../scene/relief.js")
      .then(({ startRelief }) => {
        if (cancelled || !canvas.current) return
        stop = startRelief(canvas.current, { hotels, focus, framing, still })
        setState(still ? "still" : "ready")
      })
      .catch(() => { if (!cancelled) setState("unavailable") })
    return () => { cancelled = true; stop?.() }
  }, [key, focus, framing, theme, gl]) // eslint-disable-line react-hooks/exhaustive-deps -- `key` stands for `hotels`

  const shown = state === "ready" || state === "still"
  return (
    <div aria-hidden="true" data-relief={state} className={`relief-poster ${className}`}>
      <canvas ref={canvas} className={`block size-full transition-opacity duration-700 motion-reduce:transition-none ${shown ? "opacity-100" : "opacity-0"}`} />
    </div>
  )
}
