/** Element size via ResizeObserver — every canvas here sizes itself to its panel. */

import { useEffect, useRef, useState } from "react";

export interface Size {
  width: number;
  height: number;
}

export function useMeasure<T extends HTMLElement = HTMLDivElement>(): [
  React.RefObject<T | null>,
  Size,
] {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (!box) return;
      // Round: a fractional canvas width produces a blurry one-pixel column.
      setSize({ width: Math.round(box.width), height: Math.round(box.height) });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, size];
}

/** Honour the OS reduced-motion setting; the 3D scenes fall back to a static camera. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return reduced;
}
