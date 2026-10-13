// Security headers for Cloudflare Pages, generated at build time so the CSP always matches the built index.html.
//
// Writes dist/_headers (https://developers.cloudflare.com/pages/configuration/headers/) and applies the same headers
// to `vite preview`. Inline <script>s (the theme script that prevents a flash of the wrong theme) are allowed by
// their SHA-256 hash, never by 'unsafe-inline'. CSP_ENFORCE=1 enforces the policy in production; otherwise it ships
// report-only (violations show in the console). Preview always enforces, so local testing is strict.
import { createHash } from "node:crypto"
import { readFileSync, existsSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"

// The API's origin, from the same variable the app reads (VITE_API_URL); empty when the API is same-origin
function apiOrigin() {
  try {
    return process.env.VITE_API_URL ? new URL(process.env.VITE_API_URL).origin : ""
  } catch {
    return ""
  }
}

// Cloudflare Web Analytics injects its beacon from static.cloudflareinsights.com (a path prefix, so the trailing
// slash matters) and reports to cloudflareinsights.com
function cspFor(scriptHashes) {
  const hashes = scriptHashes.map((h) => `'sha256-${h}'`).join(" ")
  return [
    "default-src 'self'",
    `script-src 'self' ${hashes} https://static.cloudflareinsights.com/`,
    // style attributes (React style={{...}}) need 'unsafe-inline' for styles; scripts stay strict
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    `connect-src 'self' ${apiOrigin()} https://cloudflareinsights.com`.replace(/\s+/g, " "),
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
  ].join("; ")
}

function inlineScriptHashes(html) {
  return [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
    // Browsers hash the script text after HTML newline normalisation (CRLF and CR become LF)
    .map((m) => m[1].replace(/\r\n?/g, "\n"))
    .filter((body) => body.trim())
    .map((body) => createHash("sha256").update(body, "utf8").digest("base64"))
}

export function headersFor(html, { enforce }) {
  return {
    [enforce ? "Content-Security-Policy" : "Content-Security-Policy-Report-Only"]: cspFor(inlineScriptHashes(html)),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
  }
}

export default function securityHeaders() {
  let outDir = "dist"
  return {
    name: "security-headers",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir)
    },
    // After the files are written: hash the inline scripts of index.html exactly as served
    writeBundle() {
      const file = resolve(outDir, "index.html")
      if (!existsSync(file)) return
      const lines = Object.entries(headersFor(readFileSync(file, "utf8"), { enforce: process.env.CSP_ENFORCE === "1" }))
        .map(([name, value]) => `  ${name}: ${value}`)
      const source = [
        "/*", ...lines,
        // Content-hashed files never change: cache them for a year. HTML keeps Pages' default (revalidate).
        "/assets/*", "  Cache-Control: public, max-age=31536000, immutable", "",
      ].join("\n")
      writeFileSync(resolve(outDir, "_headers"), source)
    },
    configurePreviewServer(server) {
      const file = resolve(outDir, "index.html")
      if (!existsSync(file)) return
      const headers = headersFor(readFileSync(file, "utf8"), { enforce: true })
      server.middlewares.use((_req, res, next) => {
        for (const [name, value] of Object.entries(headers)) res.setHeader(name, value)
        next()
      })
    },
  }
}
