import { useEffect, useState } from "react";

export const WIDE = "(min-width: 1024px)"; // Tailwind's lg

/** Whether the wide layout is shown. Parts with state of their own (e.g. a typed answer)
 * are rendered in one layout only, so their state exists once. */
export function useWide(): boolean {
  const [wide, setWide] = useState(() => window.matchMedia?.(WIDE).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.(WIDE);
    if (!media) return;
    const update = () => setWide(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return wide;
}
