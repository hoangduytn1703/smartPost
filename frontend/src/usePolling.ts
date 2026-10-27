import { useEffect } from "react";

/** Re-run `load` every `ms` while `active` is true. */
export function usePolling(load: () => unknown, active: boolean, ms = 3000) {
  useEffect(() => {
    if (!active) return;
    const id = setInterval(load, ms);
    return () => clearInterval(id);
  }, [load, active, ms]);
}
