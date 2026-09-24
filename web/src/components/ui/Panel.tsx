import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface PanelProps {
  title?: string;
  subtitle?: string;
  /** Right-aligned controls in the header — filters, a seed box, a live badge. */
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** No inner padding: for a panel whose child is a canvas that must reach the edge. */
  flush?: boolean;
}

/** The single container in this app. Everything measured sits inside one of these. */
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  flush,
}: PanelProps) {
  return (
    <section className={cn("panel lit flex min-h-0 flex-col overflow-hidden", className)}>
      {(title || actions) && (
        <header className="hairline flex shrink-0 items-center justify-between gap-3 px-4 py-2.5">
          <div className="min-w-0">
            {title && <h2 className="eyebrow truncate">{title}</h2>}
            {subtitle && <p className="mt-0.5 truncate text-[11px] text-faint">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", flush ? "" : "p-4", bodyClassName)}>{children}</div>
    </section>
  );
}
