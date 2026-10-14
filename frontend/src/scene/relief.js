// The Mussoorie ridge at dusk: the town's ridge in front, a sea of cloud filling the Doon valley below it, the
// snow range behind, and the seven hotels as lights along the ridge, coloured by their net verdict.
//
// Plain three.js (WebGLRenderer) with small custom shaders. Atmosphere follows the analytic tier of the
// atmosphere/aerial-perspective guidance: sky, terrain haze and cloud haze share ONE sun direction and ONE set of
// scattering colours, so the land fades into exactly the sky colour behind it. Colours come from CSS tokens, so
// the scene follows the theme. Procedural: no model or texture downloads. Deterministic: fixed noise, no Math.random.
import {
  AdditiveBlending, BackSide, CanvasTexture, Color, Mesh, PerspectiveCamera, PlaneGeometry, Scene, ShaderMaterial,
  SphereGeometry, Sprite, SpriteMaterial, Vector3, WebGLRenderer,
} from "three"

// ---------------------------------------------------------------- terrain field (CPU, deterministic)
function hash(x, y) { const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return s - Math.floor(s) }
function noise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf)
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1)
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
}
function fbm(x, y, o = 5) { let s = 0, amp = 0.5, f = 1; for (let i = 0; i < o; i++) { s += amp * noise(x * f, y * f); f *= 2; amp *= 0.5 } return s }
const ridgeZ = (x) => 1.2 + 0.7 * Math.sin(x * 0.28) + 0.3 * Math.sin(x * 0.8 + 1.3)
/** Height: the town ridge (near), the valley floor (under the clouds), the snow range (far). */
function height(x, z) {
  const d = z - ridgeZ(x)
  const ridge = Math.exp(-(d * d) / 2.6) * (1.9 + 1.2 * fbm(x * 0.35 + 3, 1.7))
  const spurs = Math.exp(-(d * d) / 9) * 0.9 * fbm(x * 0.9, z * 0.9)
  const far = Math.exp(-((z + 16) ** 2) / 22) * (4.6 + 3.4 * fbm(x * 0.11, 9, 6)) * (0.75 + 0.5 * fbm(x * 0.05, 3))
  const valley = -1.8 * Math.exp(-((z - 8) ** 2) / 22)                    // the Doon valley in front, under the cloud sea
  return ridge + spurs + far + valley + 0.5 * fbm(x * 0.5, z * 0.5) - 0.9
}

// ---------------------------------------------------------------- shared atmosphere (one model for all materials)
const ATMOS = /* glsl */ `
  uniform vec3 uSunDir; uniform vec3 uZenith; uniform vec3 uHorizon; uniform vec3 uSunCol; uniform float uDensity;
  vec3 skyColour(vec3 dir) {
    float h = clamp(dir.y, -0.2, 1.0);
    vec3 base = mix(uHorizon, uZenith, pow(max(h, 0.0), 0.55));
    float s = max(dot(dir, uSunDir), 0.0);
    return base + uSunCol * (0.35 * pow(s, 10.0) + 0.8 * pow(s, 120.0));
  }
  // Analytic aerial perspective: transmittance falls with distance (denser near the ground), and the lost light is
  // replaced by the sky colour seen along the same direction, so haze and sky always agree.
  vec3 aerial(vec3 colour, vec3 worldPos, vec3 camPos, float scale) {
    vec3 v = worldPos - camPos; float dist = length(v);
    float heightFactor = exp(-max(worldPos.y, 0.0) * 0.18);
    float t = exp(-dist * uDensity * heightFactor * scale);
    return mix(skyColour(normalize(v)), colour, t);
  }
`

function palette() {
  const css = getComputedStyle(document.documentElement)
  const v = (n) => css.getPropertyValue(n).trim()
  const dark = document.documentElement.classList.contains("dark")
  return dark ? {
    dark, ambient: 3.2, zenith: "#101b33", horizon: "#4a4f6e", sun: "#ffb27a", sunDir: [-0.55, 0.12, -0.83], density: 0.032,
    forest: "#16263a", rock: "#3b4660", snow: "#d9e2f1", cloudLit: "#f0d2c4", cloudShade: "#5a6084", 
    ahead: v("--success"), behind: v("--danger"), neutral: "#c9cfdb", glow: 1.0,
  } : {
    dark, ambient: 1.4, zenith: "#9fb6d6", horizon: "#e9ecf2", sun: "#fff1d6", sunDir: [-0.5, 0.32, -0.8], density: 0.026,
    forest: "#4f6f63", rock: "#7d8696", snow: "#ffffff", cloudLit: "#ffffff", cloudShade: "#c6cfdc", 
    ahead: v("--success"), behind: v("--danger"), neutral: "#5d6679", glow: 0.55,
  }
}

function glowTexture() {
  const c = document.createElement("canvas"); c.width = c.height = 64
  const g = c.getContext("2d"), r = g.createRadialGradient(32, 32, 0, 32, 32, 32)
  r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.08, "rgba(255,255,255,0.95)"); r.addColorStop(0.18, "rgba(255,255,255,0.35)")
  r.addColorStop(0.5, "rgba(255,255,255,0.08)"); r.addColorStop(1, "rgba(255,255,255,0)")
  g.fillStyle = r; g.fillRect(0, 0, 64, 64)
  return new CanvasTexture(c)
}

/**
 * Start the scene on `canvas`. hotels: [{ id, leads, lags }] in ridge order. focus: a hotel id to raise (others dim).
 * framing: "hero" (full viewport, camera pushes in as the hero scrolls) or "band" (strip behind a page title).
 * still: one frame, no motion (reduced motion). Returns stop(). Throws if WebGL is unavailable.
 */
export function startRelief(canvas, { hotels, focus = null, framing = "hero", still = false }) {
  const p = palette()
  const mobile = innerWidth < 768
  const renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, mobile ? 1.25 : 2))
  const scene = new Scene()
  const camera = new PerspectiveCamera(framing === "band" ? 30 : 34, 1, 0.1, 400)
  const disposables = []
  const track = (x) => { disposables.push(x); return x }

  const shared = {
    uSunDir: { value: new Vector3(...p.sunDir).normalize() }, uZenith: { value: new Color(p.zenith) },
    uHorizon: { value: new Color(p.horizon) }, uSunCol: { value: new Color(p.sun) }, uDensity: { value: p.density },
  }

  // Sky dome
  scene.add(new Mesh(track(new SphereGeometry(200, 32, 16)), track(new ShaderMaterial({
    side: BackSide, depthWrite: false, uniforms: shared,
    vertexShader: "varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: `${ATMOS} varying vec3 vDir; void main(){ gl_FragColor = vec4(skyColour(normalize(vDir)), 1.0); }`,
  }))))

  // Terrain: forest below, rock on steep and high ground, snow on the far range; faint gold contour lines
  const seg = mobile ? 160 : 260
  const geo = track(new PlaneGeometry(70, 44, seg, Math.round(seg * 0.63)))
  geo.rotateX(-Math.PI / 2)
  geo.translate(0, 0, -4)
  const pos = geo.attributes.position
  for (let i = 0; i < pos.count; i++) pos.setY(i, height(pos.getX(i), pos.getZ(i)))
  geo.computeVertexNormals()
  scene.add(new Mesh(geo, track(new ShaderMaterial({
    uniforms: { ...shared, uForest: { value: new Color(p.forest) }, uRock: { value: new Color(p.rock) },
      uSnow: { value: new Color(p.snow) }, uAmbient: { value: p.ambient } },
    vertexShader: `varying vec3 vWorld; varying vec3 vNormal;
      void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vWorld = w.xyz; vNormal = normalize(mat3(modelMatrix) * normal);
        gl_Position = projectionMatrix * viewMatrix * w; }`,
    fragmentShader: `${ATMOS}
      uniform vec3 uForest; uniform vec3 uRock; uniform vec3 uSnow; uniform float uAmbient;
      varying vec3 vWorld; varying vec3 vNormal;
      void main(){
        vec3 n = normalize(vNormal); float slope = 1.0 - n.y;
        vec3 albedo = mix(uForest, uRock, smoothstep(0.25, 0.55, slope) * 0.8 + smoothstep(2.4, 4.0, vWorld.y) * 0.4);
        float snow = smoothstep(4.2, 5.6, vWorld.y + n.y * 1.2) * (1.0 - smoothstep(0.35, 0.65, slope));
        albedo = mix(albedo, uSnow, snow);
        float sun = max(dot(n, uSunDir), 0.0);
        vec3 lit = albedo * (uZenith * uAmbient + uHorizon * 0.45 * (0.5 + 0.5 * n.y)) + albedo * uSunCol * sun * 0.9;
        gl_FragColor = vec4(aerial(lit, vWorld, cameraPosition, 1.0), 1.0);
      }`,
  }))))

  // Cloud sea in the valley: two drifting fbm layers, lit by the low sun, faded by the same aerial perspective
  const cloudMat = track(new ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: { ...shared, uTime: { value: 0 }, uLit: { value: new Color(p.cloudLit) }, uShade: { value: new Color(p.cloudShade) } },
    vertexShader: "varying vec3 vWorld; void main(){ vec4 w = modelMatrix * vec4(position, 1.0); vWorld = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }",
    fragmentShader: `${ATMOS}
      uniform float uTime; uniform vec3 uLit; uniform vec3 uShade; varying vec3 vWorld;
      float h(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      float n(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
        return mix(mix(h(i), h(i + vec2(1, 0)), u.x), mix(h(i + vec2(0, 1)), h(i + vec2(1, 1)), u.x), u.y); }
      float fbm(vec2 p){ float s = 0.0, a = 0.5; for (int i = 0; i < 5; i++){ s += a * n(p); p *= 2.03; a *= 0.5; } return s; }
      void main(){
        vec2 p = vWorld.xz * 0.16;
        float d = fbm(p + vec2(uTime * 0.012, uTime * 0.004)) * 0.65 + fbm(p * 2.3 - vec2(uTime * 0.02, 0.0)) * 0.35;
        float a = smoothstep(0.30, 0.60, d);
        float edge = (1.0 - smoothstep(16.0, 28.0, abs(vWorld.x))) * smoothstep(-1.0, 2.5, vWorld.z) * (1.0 - smoothstep(13.0, 16.0, vWorld.z));
        vec3 c = mix(uShade, uLit, smoothstep(0.35, 0.85, d)) + uSunCol * 0.18 * smoothstep(0.6, 0.9, d);
        gl_FragColor = vec4(aerial(c, vWorld, cameraPosition, 0.35), a * edge * 0.95);
      }`,
  }))
  const clouds = new Mesh(track(new PlaneGeometry(64, 20)), cloudMat)
  clouds.rotation.x = -Math.PI / 2
  clouds.position.set(0, 0.6, 6.5)
  scene.add(clouds)

  // Hotels: points of light along the ridge, coloured by net verdict; the focused hotel gets a beam
  const tex = track(glowTexture())
  const span = mobile ? 6 : 12                                   // phones: closer together, so all fit
  const step = hotels.length > 1 ? span / (hotels.length - 1) : 0
  const lights = hotels.map((h, i) => {
    const x = -span / 2 + i * step, z = ridgeZ(x) - 0.15, y = height(x, z) + 0.08
    const net = h.leads - h.lags
    const colour = new Color(net > 0 ? p.ahead : net < 0 ? p.behind : p.neutral)
    const dim = focus && focus !== h.id
    const big = focus === h.id
    const core = new Sprite(track(new SpriteMaterial({ map: tex, color: colour, blending: AdditiveBlending, depthWrite: false,
      transparent: true, opacity: (dim ? 0.35 : 1) * (p.dark ? 1 : 0.9) })))
    const s = (big ? 1.1 : 0.7) + 0.05 * Math.abs(net)
    core.scale.set(s, s, 1)
    core.position.set(x, y + 0.12, z)
    scene.add(core)
    if (big) {
      const beam = new Sprite(track(new SpriteMaterial({ map: tex, color: colour, blending: AdditiveBlending, depthWrite: false,
        transparent: true, opacity: 0.55 })))
      beam.scale.set(0.12, 2.6, 1)
      beam.position.set(x, y + 1.4, z)
      scene.add(beam)
    }
    return { core, base: s, phase: i * 1.7 }
  })

  // Camera: an authored shot. Hero: wide establishing view that pushes toward the ridge as the hero scrolls away.
  // Band: a lower, tighter view so the ridge and lights sit in the strip under the header.
  const shots = framing === "band"
    ? { from: { pos: new Vector3(0, 3.3, 17), look: new Vector3(0.4, 1.0, -4) }, to: null }
    : mobile
      ? { from: { pos: new Vector3(0, 3.2, 21), look: new Vector3(0.4, -0.2, -4) }, to: { pos: new Vector3(0.3, 3.0, 17), look: new Vector3(0.4, 0.2, -4) } }
      : { from: { pos: new Vector3(0, 2.8, 17), look: new Vector3(0.4, 1.0, -4) }, to: { pos: new Vector3(0.5, 2.6, 13), look: new Vector3(0.4, 1.3, -4) } }
  const pointer = { x: 0, y: 0 }, eased = { x: 0, y: 0, push: 0 }
  const onPointer = (e) => { pointer.x = e.clientX / innerWidth - 0.5; pointer.y = e.clientY / innerHeight - 0.5 }
  const size = () => {
    const r = canvas.getBoundingClientRect()
    if (!r.width || !r.height) return
    renderer.setSize(r.width, r.height, false)
    camera.aspect = r.width / r.height
    camera.fov = (framing === "band" ? 30 : 34) * (camera.aspect < 1 ? 1.35 : 1)   // keep the ridge wide on phones
    camera.updateProjectionMatrix()
  }
  const posV = new Vector3(), lookV = new Vector3()
  let last = 0
  const frame = (ms) => {
    const t = still ? 0 : ms / 1000
    const dt = Math.min(0.1, (ms - last) / 1000 || 0.016)
    last = ms
    // Scroll push read from layout each frame (no scroll listener): 0 at the top, 1 when the hero has scrolled away
    const r = canvas.getBoundingClientRect()
    const push = shots.to && !still ? Math.min(1, Math.max(0, -r.top / Math.max(1, r.height * 0.8))) : 0
    const k = 1 - Math.exp(-dt * 4)                    // frame-rate independent smoothing, one stage only
    eased.x += (pointer.x - eased.x) * k; eased.y += (pointer.y - eased.y) * k; eased.push += (push - eased.push) * k
    const a = shots.from, b = shots.to ?? shots.from
    posV.lerpVectors(a.pos, b.pos, eased.push)
    lookV.lerpVectors(a.look, b.look, eased.push)
    posV.x += Math.sin(t * 0.05) * 0.9 + eased.x * 0.9
    posV.y += -eased.y * 0.35
    camera.position.copy(posV)
    camera.lookAt(lookV)
    cloudMat.uniforms.uTime.value = t
    for (const l of lights) { const s = l.base * (1 + 0.06 * Math.sin(t * 1.3 + l.phase) * p.glow); l.core.scale.set(s, s, 1) }
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
