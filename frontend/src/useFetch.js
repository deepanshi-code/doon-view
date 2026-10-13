import { useEffect, useState } from "react"

/** Load once per `key`; until the result for the current key arrives, it's loading. */
export function useFetch(load, key) {
  const [state, setState] = useState({ key: null, data: null, error: null })
  useEffect(() => {
    let live = true
    load().then((data) => live && setState({ key, data, error: null }))
      .catch((error) => live && setState({ key, data: null, error }))
    return () => { live = false }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps -- `load` is rebuilt each render; `key` names it
  const loading = state.key !== key
  return { data: loading ? null : state.data, error: loading ? null : state.error, loading }
}
