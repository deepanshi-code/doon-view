import Relief from "./Relief"

/**
 * Top of an inner page: a band of the 3D ridge behind the title panel, fading into the page. With `focus`, that
 * hotel's pin is raised and the others dim, so the band says which hotel this page is about.
 */
export default function PageBand({ hotels, focus = null, children }) {
  return (
    <div className="relative isolate">
      <Relief hotels={hotels} focus={focus} framing="band"
        className="absolute inset-x-0 top-0 -z-10 h-[420px] sm:h-[480px] [mask-image:linear-gradient(to_bottom,black_55%,transparent)]" />
      <div className="mx-auto max-w-[1240px] px-4 sm:px-6 pt-[200px] sm:pt-[250px]">{children}</div>
    </div>
  )
}
