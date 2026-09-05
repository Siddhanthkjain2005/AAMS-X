/** Screen navigation.
 *
 * Grouped by what the operator is trying to do — operate, explain, evaluate, evidence —
 * rather than alphabetically, because the demo runs in that order and a judge following
 * along should be able to see where the argument is going next. Collapses to icons so a
 * 1920×1080 projector gets the full width back for the waterfall.
 */

import { AnimatePresence, motion } from "framer-motion";
import { PanelLeftClose, PanelLeftOpen, Radio } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

import { cn } from "@/lib/cn";
import { GROUP_LABELS, NAV, type NavItem } from "@/lib/nav";
import { useLive } from "@/state/LiveProvider";

const GROUPS = ["operate", "explain", "evaluate", "evidence"] as const;

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { pathname } = useLocation();
  const { state } = useLive();
  const streaming = state.status === "streaming";

  return (
    <motion.aside
      animate={{ width: collapsed ? 68 : 248 }}
      transition={{ type: "spring", stiffness: 320, damping: 34 }}
      className="relative z-20 flex shrink-0 flex-col border-r border-line bg-panel/70 backdrop-blur-xl"
    >
      <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4">
        <span className="relative grid size-7 shrink-0 place-items-center rounded-md border border-accent/40 bg-accent/10">
          <Radio className="size-4 text-accent" />
          {streaming && (
            <span className="absolute inset-0 animate-pulse-ring rounded-md" aria-hidden />
          )}
        </span>
        <AnimatePresence initial={false}>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -6 }}
              className="min-w-0"
            >
              <p className="truncate text-[13px] leading-tight font-semibold tracking-tight">
                AAMS-X
              </p>
              <p className="mono truncate text-[9px] leading-tight text-faint">
                ACTIVE SENSING CONSOLE
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden py-3">
        {GROUPS.map((group) => {
          const items = NAV.filter((item) => item.group === group);
          if (!items.length) return null;
          return (
            <div key={group} className="mb-3">
              {!collapsed && (
                <p className="eyebrow px-4 pb-1.5 text-[9px]">{GROUP_LABELS[group]}</p>
              )}
              {collapsed && <div className="mx-4 mb-2 border-t border-line" />}
              <ul className="space-y-0.5 px-2">
                {items.map((item) => (
                  <li key={item.path}>
                    <SidebarLink item={item} collapsed={collapsed} active={pathname === item.path} />
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </nav>

      <button
        type="button"
        onClick={onToggle}
        className="flex h-10 shrink-0 items-center gap-2 border-t border-line px-4 text-[11px] text-muted transition-colors hover:bg-panel-2 hover:text-ink"
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
      >
        {collapsed ? (
          <PanelLeftOpen className="size-4" />
        ) : (
          <>
            <PanelLeftClose className="size-4" />
            <span>Collapse</span>
          </>
        )}
      </button>
    </motion.aside>
  );
}

function SidebarLink({
  item,
  collapsed,
  active,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.path}
      title={collapsed ? `${item.label} — ${item.blurb}` : undefined}
      className={cn(
        "group relative flex items-center gap-2.5 rounded-md px-2 py-2 transition-colors",
        active ? "text-ink" : "text-muted hover:bg-panel-2/70 hover:text-ink-dim",
      )}
    >
      {active && (
        <motion.span
          layoutId="nav-active"
          transition={{ type: "spring", stiffness: 420, damping: 36 }}
          className="absolute inset-0 rounded-md border border-accent/30 bg-accent/10"
        />
      )}
      <Icon className={cn("relative size-4 shrink-0", active && "text-accent")} />
      {!collapsed && (
        <span className="relative min-w-0 flex-1">
          <span className="block truncate text-[12.5px] leading-tight font-medium">
            {item.label}
          </span>
          <span className="block truncate text-[10px] leading-tight text-faint">{item.blurb}</span>
        </span>
      )}
    </NavLink>
  );
}
