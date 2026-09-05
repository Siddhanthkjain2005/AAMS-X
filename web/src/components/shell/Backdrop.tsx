/** The room the instruments sit in.
 *
 * One fixed, pointer-transparent layer behind the whole console: a slow parallax grid, a
 * horizontal sweep line, and two large radial glows. It is decoration, so it is the one
 * place in this app where colour carries no measurement — and it is deliberately cheap:
 * three composited elements with CSS animations, no canvas, no per-frame JavaScript, so
 * it cannot compete with the waterfall for the main thread.
 */

import { usePrefersReducedMotion } from "@/hooks/useMeasure";

export function Backdrop() {
  const reduced = usePrefersReducedMotion();
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-abyss">
      <div className="grid-floor absolute inset-0 opacity-[0.55]" />
      <div
        className="absolute -left-1/4 top-[-20%] h-[70vh] w-[70vw] rounded-full opacity-30 blur-[120px]"
        style={{ background: "radial-gradient(circle, #14544f 0%, transparent 65%)" }}
      />
      <div
        className="absolute -right-1/4 bottom-[-25%] h-[60vh] w-[60vw] rounded-full opacity-25 blur-[120px]"
        style={{ background: "radial-gradient(circle, #1b3f63 0%, transparent 65%)" }}
      />
      {!reduced && (
        <div className="absolute inset-x-0 top-0 h-full">
          <div
            className="absolute inset-x-0 h-px animate-[scanline_9s_linear_infinite]"
            style={{
              background:
                "linear-gradient(to right, transparent, rgb(79 209 197 / 0.5), transparent)",
            }}
          />
        </div>
      )}
      <div className="absolute inset-0 bg-gradient-to-b from-void/60 via-transparent to-void/80" />
    </div>
  );
}
