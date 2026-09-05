/** Console header: where we are, what the backend has, and what is running.
 *
 * The right-hand cluster is the honesty strip. It reports whether the API is reachable,
 * how many real recordings are actually cached, and the live socket's state — so nothing
 * on screen can be mistaken for data the backend does not have. If the cache is empty it
 * says so here, before a screen has a chance to render an empty chart.
 */

import { AnimatePresence, motion } from "framer-motion";
import { Activity, CircleSlash, Database, Layers3, Radio } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

import { useActive, useStatus } from "@/api/queries";
import { Badge, LiveDot } from "@/components/ui";
import { int, num } from "@/lib/format";
import { navFor } from "@/lib/nav";
import { useLive } from "@/state/LiveProvider";

export function TopBar() {
  const { pathname } = useLocation();
  const screen = navFor(pathname);
  const status = useStatus();
  const active = useActive();
  const { state } = useLive();

  const running = active.data?.active.filter((entry) => entry.status === "running").length ?? 0;
  const recordings = status.data?.recordings ?? 0;
  const windows = status.data?.windows_indexed ?? 0;

  return (
    <header className="relative z-10 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-line bg-panel/60 px-5 backdrop-blur-xl">
      <div className="min-w-0">
        <h1 className="truncate text-[15px] leading-tight font-semibold tracking-tight">
          {screen?.label ?? "AAMS-X"}
        </h1>
        <p className="truncate text-[11px] leading-tight text-faint">{screen?.blurb}</p>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <AnimatePresence>
          {state.status === "streaming" && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
            >
              <Badge tone="accent">
                <LiveDot active />
                {int(state.frameCount)} frames
              </Badge>
            </motion.div>
          )}
        </AnimatePresence>

        {running > 0 && (
          <Badge tone="signal">
            <Activity className="size-3" />
            {running} running
          </Badge>
        )}

        <Link to="/replay" className="focus-visible:outline-none">
          <Badge tone={recordings > 0 ? "neutral" : "warn"}>
            <Database className="size-3" />
            {recordings > 0 ? `${int(recordings)} recordings` : "no cache"}
          </Badge>
        </Link>

        {windows > 0 && (
          <Badge tone="neutral">
            <Layers3 className="size-3" />
            {compact(windows)} windows
          </Badge>
        )}

        <Badge tone={status.isError ? "bad" : status.data ? "good" : "neutral"}>
          {status.isError ? <CircleSlash className="size-3" /> : <Radio className="size-3" />}
          {status.isError ? "API unreachable" : status.data ? `v${status.data.version}` : "…"}
        </Badge>
      </div>
    </header>
  );
}

/** 1.2M rather than 1200000: the exact row count is on the Replay screen, not here. */
function compact(value: number): string {
  if (value >= 1_000_000) return `${num(value / 1_000_000, 1)}M`;
  if (value >= 1_000) return `${num(value / 1_000, 1)}k`;
  return int(value);
}
