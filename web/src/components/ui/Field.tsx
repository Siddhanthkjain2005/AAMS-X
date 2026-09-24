import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-1.5", className)}>
      <span className="eyebrow">{label}</span>
      {children}
      {hint && <span className="text-[10px] leading-snug text-faint">{hint}</span>}
    </label>
  );
}

const CONTROL =
  "h-9 w-full rounded-md border border-line-bright bg-panel-2 px-2.5 text-xs text-ink " +
  "transition-colors hover:border-accent-dim focus:border-accent focus:outline-none";

export function Select<T extends string>({
  value,
  onChange,
  options,
  disabled,
  className,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; disabled?: boolean }[];
  disabled?: boolean;
  className?: string;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value as T)}
      className={cn(CONTROL, "mono cursor-pointer disabled:opacity-50", className)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value} disabled={option.disabled}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled,
  className,
}: {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      onChange={(event) => {
        const next = Number(event.target.value);
        if (Number.isFinite(next)) onChange(next);
      }}
      className={cn(CONTROL, "mono tabular-nums disabled:opacity-50", className)}
    />
  );
}

/**
 * A weight slider that shows its value. Used for the reward and MAG-NTS weights, which
 * the build brief requires to be visible and editable rather than buried in a config.
 */
export function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.01,
  colour,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  colour?: string;
  disabled?: boolean;
}) {
  const fraction = max === min ? 0 : (value - min) / (max - min);
  return (
    <div className={cn("flex flex-col gap-1", disabled && "opacity-50")}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[11px] text-ink-dim">{label}</span>
        <span className="mono text-[11px] tabular-nums text-ink">{value.toFixed(2)}</span>
      </div>
      <div className="relative h-4">
        <div className="absolute inset-x-0 top-1.5 h-1 rounded-full bg-line" />
        <div
          className="absolute top-1.5 h-1 rounded-full transition-[width] duration-100"
          style={{
            width: `${Math.max(0, Math.min(1, fraction)) * 100}%`,
            background: colour ?? "var(--color-accent)",
          }}
        />
        <input
          type="range"
          value={value}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onChange={(event) => onChange(Number(event.target.value))}
          aria-label={label}
          className="absolute inset-0 h-4 w-full cursor-pointer appearance-none bg-transparent
            [&::-webkit-slider-thumb]:size-3.5 [&::-webkit-slider-thumb]:appearance-none
            [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border
            [&::-webkit-slider-thumb]:border-void [&::-webkit-slider-thumb]:bg-ink"
        />
      </div>
    </div>
  );
}

export function Toggle({
  label,
  checked,
  onChange,
  hint,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "group flex items-start gap-2.5 rounded-md border px-2.5 py-2 text-left transition-colors",
        checked
          ? "border-accent/45 bg-accent/8 hover:border-accent/70"
          : "border-line bg-panel-2/60 hover:border-line-bright",
        disabled && "cursor-not-allowed opacity-45",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-4 w-7 shrink-0 items-center rounded-full border transition-colors",
          checked ? "border-accent/60 bg-accent/25" : "border-line-bright bg-void",
        )}
      >
        <span
          className={cn(
            "size-3 rounded-full transition-transform duration-150",
            checked ? "translate-x-3.5 bg-accent" : "translate-x-0.5 bg-faint",
          )}
        />
      </span>
      <span className="min-w-0">
        <span className={cn("block text-[11px] font-medium", checked ? "text-ink" : "text-muted")}>
          {label}
        </span>
        {hint && <span className="mt-0.5 block text-[10px] leading-snug text-faint">{hint}</span>}
      </span>
    </button>
  );
}
