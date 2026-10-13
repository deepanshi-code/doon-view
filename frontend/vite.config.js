import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import securityHeaders from "./security-headers.js"

export default defineConfig({
  plugins: [react(), tailwindcss(), securityHeaders()],
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } } },
  // Production build: no source maps, hash-only file names, console/debugger stripped. This hides structure, not
  // secrets: everything shipped to the browser is public.
  build: {
    sourcemap: false,
    rolldownOptions: {
      output: {
        entryFileNames: "assets/[hash].js",
        chunkFileNames: "assets/[hash].js",
        assetFileNames: "assets/[hash][extname]",
        minify: { compress: { dropConsole: true, dropDebugger: true } },
      },
    },
  },
})
