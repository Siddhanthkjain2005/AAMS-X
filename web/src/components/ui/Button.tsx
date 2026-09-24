import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "ghost" | "danger" | "subtle";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent/15 text-accent border-accent/50 hover:bg-accent/25 hover:border-accent " +
    "disabled:hover:bg-accent/15",
  ghost: "bg-transparent text-ink-dim border-line-bright hover:bg-panel-2 hover:text-ink",
  danger: "bg-bad/10 text-bad border-bad/40 hover:bg-bad/20 hover:border-bad",
  subtle: "bg-panel-2 text-ink-dim border-line hover:bg-line hover:text-ink",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-[11px] gap-1.5",
  md: "h-9 px-3.5 text-xs gap-2",
  lg: "h-11 px-5 text-sm gap-2.5",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}

export function Button({
  variant = "ghost",
  size = "md",
  icon,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center rounded-md border font-semibold tracking-wide",
        "transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}
