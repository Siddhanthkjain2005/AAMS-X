/** A colour ramp with its units.
 *
 * The gradient is rebuilt *from the LUT bytes*, not from the stop list, so it inherits the
 * spectrum ramp's gamma. A legend drawn from the stops would be subtly wrong for the one
 * ramp that is not linear in its input — which is the ramp that matters most.
 */

import { useMemo } from "react";

import { cn } from "@/lib/cn";

export function RampLegend({
  lut,
  min,
  max,
  unit,
  label,
  className,
  ticks = 3,
}: {
  lut: Uint8ClampedArray;
  min: number;
  max: number;
  unit?: string;
  label?: string;
  className?: string;
  ticks?: number;
}) {
  const gradient = useMemo(() => cssFromLut(lut), [lut]);
  const marks = useMemo(() => {
    const out: string[] = [];
    for (let i = 0; i < ticks; i += 1) {
      const value = min + ((max - min) * i) / (ticks - 1);
      out.push(Number.isInteger(value) ? String(value) : value.toFixed(1));
    }
    return out;
  }, [min, max, ticks]);

  return (
    <div className={cn("flex min-w-0 items-center gap-2", className)}>
      {label && <span className="eyebrow shrink-0 text-[9px]">{label}</span>}
      <div className="min-w-16 flex-1">
        <div className="h-1.5 w-full rounded-full" style={{ background: gradient }} />
        <div className="mono mt-0.5 flex justify-between text-[9px] leading-none text-faint">
          {marks.map((mark, index) => (
            <span key={mark + index}>{mark}</span>
          ))}
        </div>
      </div>
      {unit && <span className="mono shrink-0 text-[9px] text-faint">{unit}</span>}
    </div>
  );
}

/** Sixteen samples is enough for a 200 px strip and keeps the style string short. */
function cssFromLut(lut: Uint8ClampedArray, samples = 16): string {
  const stops: string[] = [];
  for (let i = 0; i < samples; i += 1) {
    const offset = Math.round((i / (samples - 1)) * 255) * 4;
    stops.push(`rgb(${lut[offset]} ${lut[offset + 1]} ${lut[offset + 2]}) ${(i / (samples - 1)) * 100}%`);
  }
  return `linear-gradient(to right, ${stops.join(", ")})`;
}
