import { useState } from "react"
import { Link, NavLink, Outlet } from "react-router-dom"
import { Moon, Sun } from "lucide-react"
import { Mark } from "./Ridgeline"

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"))
  const toggle = () => {
    const next = !dark
    document.documentElement.classList.toggle("dark", next)
    document.getElementById("theme-color-meta")?.setAttribute("content", next ? "#12131c" : "#f4f2ef")
    try { localStorage.setItem("theme", next ? "dark" : "light") } catch { /* private mode: not remembered */ }
    setDark(next)
  }
  const Icon = dark ? Sun : Moon
  return (
    <button type="button" onClick={toggle} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="size-11 inline-flex items-center justify-center rounded-xl border border-line hover:border-line-strong text-ink">
      <Icon size={18} aria-hidden="true" />
    </button>
  )
}

const navClass = ({ isActive }) =>
  `px-3 py-2 rounded-lg text-sm font-semibold ${isActive ? "text-ink bg-surface" : "text-muted hover:text-ink"}`

export default function Shell() {
  return (
    <div className="min-h-dvh flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:m-3 focus:p-3 focus:bg-surface focus:rounded-lg">Skip to content</a>
      <header className="border-b border-line">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2.5 font-display font-extrabold text-lg tracking-tight text-ink">
            <Mark /> <span className="max-sm:sr-only">Doon View</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1">
            <NavLink to="/" end className={navClass}>Mussoorie</NavLink>
            <NavLink to="/method" className={navClass}>Method</NavLink>
            <ThemeToggle />
          </nav>
        </div>
      </header>
      <main id="main" className="flex-1"><Outlet /></main>
      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 text-sm text-muted flex flex-col sm:flex-row gap-2 justify-between">
          <p>Doon View: review intelligence for Mussoorie&rsquo;s hotels. Built for the AI&ndash;Tourism Hackathon.</p>
          <p>Aggregates and short quotes only; reviewer names removed.</p>
        </div>
      </footer>
    </div>
  )
}
