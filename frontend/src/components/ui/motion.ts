import { useEffect, useRef, useState } from "react";

const NO_PREFERENCE = "(prefers-reduced-motion: no-preference)";

/**
 * True only when the environment positively says motion is welcome.
 *
 * Asking for ``no-preference`` (instead of "not reduce") means a missing or stubbed matchMedia —
 * jsdom/vitest, old browsers — gets the final state immediately, and so does anyone with
 * prefers-reduced-motion: reduce.
 */
export function prefersMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function")
    return false;
  if (typeof window.requestAnimationFrame !== "function") return false;
  try {
    return window.matchMedia(NO_PREFERENCE).matches === true;
  } catch {
    return false;
  }
}

/** React view of {@link prefersMotion}; follows changes of the OS setting. */
export function usePrefersMotion(): boolean {
  const [allowed, setAllowed] = useState(prefersMotion);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(NO_PREFERENCE);
    if (typeof mql?.addEventListener !== "function") return;
    const onChange = () => setAllowed(prefersMotion());
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return allowed;
}

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;

/**
 * Animate a number from its previous value to ``target``. Returns ``target`` itself (not an
 * intermediate) whenever motion is not allowed, so tests and reduced-motion users see the final value
 * on the first render.
 */
export function useCountUp(target: number, duration = 700): number {
  const animate = usePrefersMotion();
  const [shown, setShown] = useState(() => (animate ? 0 : target));
  const fromRef = useRef(animate ? 0 : target);

  useEffect(() => {
    if (!animate || !Number.isFinite(target)) {
      fromRef.current = target;
      setShown(target);
      return;
    }
    const from = fromRef.current;
    if (from === target) {
      setShown(target);
      return;
    }
    let frame = 0;
    let current = from;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      current = t >= 1 ? target : from + (target - from) * easeOutCubic(t);
      setShown(current);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      // An interrupted animation continues from where it was, not from zero.
      fromRef.current = current;
    };
  }, [target, duration, animate]);

  return animate ? shown : target;
}
