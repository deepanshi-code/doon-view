import { useState } from "react"
import { Link, NavLink, Outlet } from "react-router-dom"
import { Moon, Sun } from "lucide-react"
import Mark from "./Mark"

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"))
  const toggle = () => {
    const next = !dark
    document.documentElement.classList.toggle("dark", next)
    document.getElementById("theme-color-meta")?.setAttribute("content", next ? "#090d18" : "#f1f3f6")
    try { localStorage.setItem("theme", next ? "dark" : "light") } catch { /* private mode: not remembered */ }
    setDark(next)
  }
  const Icon = dark ? Sun : Moon
  return (
    <button type="button" onClick={toggle} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="size-10 inline-flex items-center justify-center rounded-ctl text-muted hover:text-ink hover:bg-line/50 transition-colors">
      <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
    </button>
  )
}

const navClass = ({ isActive }) =>
  `inline-flex items-center min-h-10 px-1 transition-colors ${isActive ? "text-ink" : "text-muted hover:text-ink"}`

// The header floats above the content as a frosted bar, sticky so it stays in reach; the 3D relief shows
// through it at the top of each page.
export default function Shell() {
  return (
    <div className="min-h-dvh flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:z-30 focus:m-3 focus:p-3 focus:rounded-ctl focus:bg-surface">Skip to content</a>
      <header className="sticky top-3 z-20 px-3 sm:px-4 -mb-[76px]">
        <div className="glass mx-auto max-w-[1240px] h-[60px] rounded-panel flex items-center gap-6 pl-4 pr-2 sm:pl-5">
          <Link to="/" className="flex items-center gap-2.5 font-semibold text-[17px] tracking-tight text-ink">
            <Mark size={24} /> Doon View
          </Link>
          <nav aria-label="Main" className="ml-auto flex items-center gap-4 sm:gap-6 text-[15px]">
            <NavLink to="/d/mussoorie" className={navClass}>Hotels</NavLink>
            <NavLink to="/method" className={navClass}>Method</NavLink>
            <ThemeToggle />
          </nav>
        </div>
      </header>
      <main id="main" className="flex-1 min-w-0 flex flex-col *:w-full"><Outlet /></main>
      <footer className="border-t border-line">
        <div className="max-w-[1240px] mx-auto px-4 sm:px-8 py-8 text-sm text-muted">
          <p>Doon View, review intelligence for Mussoorie&rsquo;s hotels, built for the AI-Tourism Hackathon. Aggregates and single-sentence quotes only; reviewer names are removed.</p>
        </div>
      </footer>
    </div>
  )
}
