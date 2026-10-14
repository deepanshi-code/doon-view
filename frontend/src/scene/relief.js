// The Mussoorie ridge as a 3D relief, with one pin per hotel coloured by its net verdict. Plain three.js
// (WebGLRenderer), loaded lazily by components/Relief.jsx. Colours come from the page's CSS tokens, so the scene
// follows the theme. Procedural terrain: no model files to download.
import {
  BufferAttribute, Color, CylinderGeometry, DirectionalLight, Fog, HemisphereLight, Mesh, MeshBasicMaterial,
  MeshStandardMaterial, OctahedronGeometry, PerspectiveCamera, PlaneGeometry, Scene, WebGLRenderer,
} from "three"

function hash(x, y) { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s) }
function noise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf)
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}
function fbm(x, y) { let s = 0, amp = 0.5, f = 1; for (let i = 0; i < 5; i++) { s += amp * noise(x * f, y * f); f *= 2; amp *= 0.5 } return s }
const ridgeZ = (x) => -1.2 + 0.9 * Math.sin(x * 0.32) + 0.35 * Math.sin(x * 0.85 + 1.3)
function height(x, z) {
  const d = z - ridgeZ(x)
  const ridge = Math.exp(-(d * d) / 3.2) * (2.1 + 1.4 * fbm(x * 0.35 + 3, 1.7))
  const back = Math.exp(-((z + 5) ** 2) / 6) * (2.8 + 2.2 * fbm(x * 0.2, 9))   // the higher range behind
  return ridge + back + 0.55 * fbm(x * 0.6, z * 0.6) - 0.3
}

/** Read the theme from CSS custom properties on <html>. */
function palette() {
  const css = getComputedStyle(document.documentElement)
  const v = (n) => css.getPropertyValue(n).trim()
  const dark = document.documentElement.classList.contains("dark")
  return {
    dark, bg: v("--bg"), ahead: v("--success"), behind: v("--danger"), neutral: v("--muted"), accent: v("--accent"),
    terrain: dark ? ["#0b1222", "#1f2b45", "#b9c3d8"] : ["#aab4c4", "#dfe4ec", "#ffffff"],
  }
}

/**
 * Start the scene on `canvas`. hotels: [{ id, leads, lags }] in ridge order; focus: a hotel id to highlight (others
 * dim). framing "hero" fills a viewport; "band" is a short strip behind a page title. still: draw one frame only.
 * Returns stop(), which releases the GPU resources. Throws if WebGL is unavailable.
 */
export function startRelief(canvas, { hotels, focus = null, framing = "hero", still = false }) {
  const p = palette()
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, innerWidth < 768 ? 1.5 : 2))
  const scene = new Scene()
  scene.background = new Color(p.bg)
  scene.fog = new Fog(p.bg, 12, 30)
  const camera = new PerspectiveCamera(38, 1, 0.1, 100)

  const segX = innerWidth < 768 ? 140 : 240
  const geo = new PlaneGeometry(30, 18, segX, Math.round(segX * 0.6))
  geo.rotateX(-Math.PI / 2)
  const pos = geo.attributes.position
  const colours = new Float32Array(pos.count * 3)
  const [c0, c1, c2] = p.terrain.map((c) => new Color(c))
  const tmp = new Color()
  let maxH = 0
  for (let i = 0; i < pos.count; i++) { const h = height(pos.getX(i), pos.getZ(i)); pos.setY(i, h); maxH = Math.max(maxH, h) }
  for (let i = 0; i < pos.count; i++) {
    const t = Math.max(0, pos.getY(i)) / maxH
    if (t < 0.62) tmp.copy(c0).lerp(c1, t / 0.62)
    else tmp.copy(c1).lerp(c2, Math.min(1, (t - 0.62) / 0.3))
    colours.set([tmp.r, tmp.g, tmp.b], i * 3)
  }
  geo.setAttribute("color", new BufferAttribute(colours, 3))
  geo.computeVertexNormals()
  const surface = new MeshStandardMaterial({ vertexColors: true, roughness: 0.95, metalness: 0 })
  scene.add(new Mesh(geo, surface))
  const wire = p.dark ? new MeshBasicMaterial({ color: p.accent, wireframe: true, transparent: true, opacity: 0.09, depthWrite: false }) : null
  if (wire) scene.add(new Mesh(geo, wire))
  scene.add(new HemisphereLight(p.dark ? 0x8aa0c8 : 0xffffff, p.dark ? 0x05070d : 0x9aa6b8, p.dark ? 0.9 : 1.3))
  const sun = new DirectionalLight(p.dark ? 0xc9d6ff : 0xfff6ea, p.dark ? 1.6 : 2.4)
  sun.position.set(-8, 6, 2)
  scene.add(sun)

  const disposables = [geo, surface, wire].filter(Boolean)
  const step = hotels.length > 1 ? 10.8 / (hotels.length - 1) : 0
  hotels.forEach((h, i) => {
    const x = -5.4 + i * step, z = ridgeZ(x) + 0.35, y = height(x, z)
    const net = h.leads - h.lags
    const colour = net > 0 ? p.ahead : net < 0 ? p.behind : p.neutral
    const dim = focus && focus !== h.id
    const big = focus === h.id
    const mat = new MeshBasicMaterial({ color: colour, transparent: true, opacity: dim ? 0.35 : 0.95 })
    const stemGeo = new CylinderGeometry(big ? 0.014 : 0.008, big ? 0.014 : 0.008, big ? 1.5 : 1.1, 6)
    const headGeo = new OctahedronGeometry((big ? 0.13 : 0.075) + 0.01 * Math.abs(net), 0)
    const stem = new Mesh(stemGeo, mat), head = new Mesh(headGeo, mat)
    stem.position.set(x, y + (big ? 0.75 : 0.55), z)
    head.position.set(x, y + (big ? 1.52 : 1.12), z)
    scene.add(stem, head)
    disposables.push(mat, stemGeo, headGeo)
  })

  const pointer = { x: 0, y: 0 }
  const onPointer = (e) => { pointer.x = e.clientX / innerWidth - 0.5; pointer.y = e.clientY / innerHeight - 0.5 }
  const size = () => {
    const r = canvas.getBoundingClientRect()
    if (!r.width || !r.height) return
    renderer.setSize(r.width, r.height, false)
    camera.aspect = r.width / r.height
    camera.updateProjectionMatrix()
  }
  const frame = (ms) => {
    const s = still ? 0 : ms / 1000
    if (framing === "band") {
      camera.position.set(Math.sin(s * 0.05) * 0.8 + pointer.x * 0.5, 6.2 - pointer.y * 0.2, 13.5)
      camera.lookAt(0.3, 1.9, -3.2)
    } else {
      camera.position.set(Math.sin(s * 0.06) * 1.2 + pointer.x * 0.7, 6.2 - pointer.y * 0.4, 13.5)
      camera.lookAt(0.4, 0.2, -3.2)
    }
    renderer.render(scene, camera)
  }
  size()
  addEventListener("resize", size)
  let visible = true
  const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting })
  io.observe(canvas)
  if (still) frame(0)
  else {
    addEventListener("pointermove", onPointer, { passive: true })
    renderer.setAnimationLoop((ms) => { if (visible && !document.hidden) frame(ms) })
  }

  return function stop() {
    renderer.setAnimationLoop(null)
    removeEventListener("resize", size)
    removeEventListener("pointermove", onPointer)
    io.disconnect()
    disposables.forEach((d) => d.dispose())
    renderer.dispose()
  }
}
