import { lazy, Suspense } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"
import Shell from "./components/Shell"
import Home from "./pages/Home"

// Home ships in the main bundle (first paint); the other pages are their own chunks
const Destination = lazy(() => import("./pages/Destination"))
const Hotel = lazy(() => import("./pages/Hotel"))
const Method = lazy(() => import("./pages/Method"))

function NotFound() {
  return <div className="max-w-[1240px] mx-auto px-4 sm:px-6 pt-32 pb-24"><h1 className="text-4xl font-semibold tracking-tight">Page not found</h1></div>
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<p className="p-8 text-muted">Loading…</p>}>
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Home />} />
            <Route path="d/:slug" element={<Destination />} />
            <Route path="d/:slug/h/:pid" element={<Hotel />} />
            <Route path="method" element={<Method />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
