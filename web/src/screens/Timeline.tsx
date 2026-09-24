/** Event Timeline — what happened, step by step, in the order the engine logged it.
 *
 * This is the screen that answers "did the system actually notice?" without asking anyone
 * to read a chart. Every row is an event the *engine* emitted (`TimelineEvent`), not
 * something the browser inferred from frames: a detection, a change point, a memory recall,
 * a periodicity discovery, a budget threshold, an archive gap. The browser only filters and
 * sorts them.
 *
 * Clicking a row scrubs the shared cursor to that step, so the belief map and the decision
 * inspector jump to the moment being read about.
 */

import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  BatteryLow,
  BrainCircuit,
  Crosshair,
  Flag,
  Gauge,
  Radio,
  Repeat,
  Search,
  ShieldAlert,
  SignalZero,
  Split,
  Target,
  Telescope,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { EventKind, Severity, TimelineEvent } from "@/api/types";
import { isEpisodeResult } from "@/api/types";
import { NoRun } from "@/components/run/NoRun";
import { RunStatusBar } from "@/components/run/RunStatusBar";
import { Badge, EmptyState, Panel, Tabs } from "@/components/ui";
import { cn } from "@/lib/cn";
import { int, num } from "@/lib/format";
import { SEVERITY_COLORS } from "@/lib/palette";
import { useLive } from "@/state/LiveProvider";
import { useSession } from "@/state/session";

const ICONS: Record<EventKind, LucideIcon> = {
  experiment_started: Flag,
  detection: Target,
  burst_detected: Radio,
  miss: Crosshair,
  high_uncertainty: Search,
  change_detected: Split,
  memory_recalled: BrainCircuit,
  periodicity_discovered: Repeat,
  exploration_increased: Telescope,
  budget_threshold: Gauge,
  budget_exhausted: BatteryLow,
  phase_changed: ShieldAlert,
  archive_gap: SignalZero,
  experiment_completed: Flag,
};

type Filter = "all" | "detection" | "adaptation" | "problem";

/** Which kinds belong to which reading. Adaptation is the closed loop reacting. */
const GROUPS: Record<Exclude<Filter, "all">, EventKind[]> = {
  detection: ["detection", "burst_detected"],
  adaptation: [
    "change_detected",
    "memory_recalled",
    "periodicity_discovered",
    "exploration_increased",
    "phase_changed",
  ],
  problem: ["miss", "high_uncertainty", "budget_threshold", "budget_exhausted", "archive_gap"],
};

export default function Timeline() {
  const { state } = useLive();
  const experimentId = useSession((session) => session.experimentId);
  const setCursor = useSession((session) => session.setCursor);
  const cursor = useSession((session) => session.cursor);
  const [filter, setFilter] = useState<Filter>("all");

  // While streaming the socket's own list is newest-first and already capped. Once a run is
  // over, the stored result carries the complete timeline, which is the longer of the two.
  const events = useMemo<TimelineEvent[]>(() => {
    const stored = isEpisodeResult(state.result) ? state.result.timeline : null;
    if (stored && stored.length >= state.timeline.length) return [...stored].reverse();
    return state.timeline;
  }, [state.result, state.timeline]);

  const counts = useMemo(() => {
    const out = { all: events.length, detection: 0, adaptation: 0, problem: 0 };
    for (const event of events) {
      for (const [group, kinds] of Object.entries(GROUPS)) {
        if (kinds.includes(event.kind)) out[group as keyof typeof GROUPS] += 1;
      }
    }
    return out;
  }, [events]);

  const shown = filter === "all" ? events : events.filter((e) => GROUPS[filter].includes(e.kind));

  if (!experimentId) {
    return (
      <div className="p-4">
        <Panel className="min-h-96">
          <NoRun what="event timeline" />
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <RunStatusBar />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_300px]">
        <Panel
          flush
          title="Event timeline"
          subtitle="emitted by the engine as it ran · newest first · click a row to scrub there"
          actions={
            <Tabs
              value={filter}
              onChange={setFilter}
              tabs={[
                { value: "all", label: "All", count: counts.all },
                { value: "detection", label: "Detections", count: counts.detection },
                { value: "adaptation", label: "Adaptation", count: counts.adaptation },
                { value: "problem", label: "Problems", count: counts.problem },
              ]}
            />
          }
          className="min-h-0"
          bodyClassName="overflow-y-auto"
        >
          {shown.length === 0 ? (
            <EmptyState
              title={events.length === 0 ? "No events logged yet" : "Nothing in this filter"}
              detail={
                events.length === 0
                  ? "Events appear as the run produces them. A quiet band genuinely produces few."
                  : "Switch filters to see the events this run did log."
              }
            />
          ) : (
            <ul className="divide-y divide-line/60">
              <AnimatePresence initial={false}>
                {shown.map((event, index) => (
                  <EventRow
                    key={`${event.step}:${event.kind}:${index}`}
                    event={event}
                    active={cursor === event.step}
                    onClick={() => setCursor(event.step)}
                  />
                ))}
              </AnimatePresence>
            </ul>
          )}
        </Panel>

        <div className="flex flex-col gap-3">
          <Panel title="Severity mix" subtitle="how the run's events break down">
            <SeverityBreakdown events={events} />
          </Panel>
          <Panel title="Reading this screen" className="shrink-0">
            <p className="text-[11px] leading-relaxed text-muted">
              These rows are the engine's own log, not a browser reconstruction. A{" "}
              <span className="text-mag">memory recall</span> row means the Hopfield read
              crossed its recognition threshold and the memory term entered the score; a{" "}
              <span className="text-warn">change detected</span> row means Page-Hinkley
              fired and exploration was boosted. An{" "}
              <span className="text-faint">archive gap</span> row is the recording having no
              data at that step — the receiver measured nothing, and the run says so.
            </p>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function EventRow({
  event,
  active,
  onClick,
}: {
  event: TimelineEvent;
  active: boolean;
  onClick: () => void;
}) {
  const Icon = ICONS[event.kind] ?? AlertTriangle;
  const colour = SEVERITY_COLORS[event.severity as Severity] ?? SEVERITY_COLORS.info;
  const detail = Object.entries(event.data ?? {})
    .filter(([, value]) => typeof value === "number" || typeof value === "string")
    .slice(0, 4);

  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.18 }}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "flex w-full items-start gap-3 px-4 py-2 text-left transition-colors",
          active ? "bg-accent/8" : "hover:bg-panel-2/50",
        )}
      >
        <span
          className="mono mt-0.5 w-14 shrink-0 text-right text-[10px] tabular-nums"
          style={{ color: colour }}
        >
          {int(event.step)}
        </span>
        <Icon className="mt-0.5 size-3.5 shrink-0" style={{ color: colour }} />
        <span className="min-w-0 flex-1">
          <span className="block text-[11.5px] leading-snug text-ink-dim">{event.message}</span>
          {detail.length > 0 && (
            <span className="mono mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[9.5px] text-faint">
              {detail.map(([key, value]) => (
                <span key={key}>
                  {key.replace(/_/g, " ")}{" "}
                  <span className="text-muted">
                    {typeof value === "number" ? num(value, 3) : String(value)}
                  </span>
                </span>
              ))}
            </span>
          )}
        </span>
        <span className="mono shrink-0 text-[9px] text-faint">{event.kind.replace(/_/g, " ")}</span>
      </button>
    </motion.li>
  );
}

function SeverityBreakdown({ events }: { events: TimelineEvent[] }) {
  const order: Severity[] = ["critical", "warning", "insight", "success", "info"];
  const tally = new Map<Severity, number>();
  for (const event of events) {
    tally.set(event.severity as Severity, (tally.get(event.severity as Severity) ?? 0) + 1);
  }
  const total = events.length;
  if (total === 0) return <p className="text-[11px] text-faint">nothing logged yet</p>;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-2 overflow-hidden rounded-full bg-line">
        {order.map((severity) => {
          const count = tally.get(severity) ?? 0;
          if (count === 0) return null;
          return (
            <div
              key={severity}
              style={{ width: `${(count / total) * 100}%`, background: SEVERITY_COLORS[severity] }}
              title={`${severity}: ${count}`}
            />
          );
        })}
      </div>
      <ul className="flex flex-col gap-1">
        {order.map((severity) => {
          const count = tally.get(severity) ?? 0;
          if (count === 0) return null;
          return (
            <li key={severity} className="flex items-center justify-between text-[11px]">
              <span className="flex items-center gap-2">
                <span
                  className="size-2 rounded-full"
                  style={{ background: SEVERITY_COLORS[severity] }}
                />
                <span className="text-muted capitalize">{severity}</span>
              </span>
              <Badge tone="neutral">{count}</Badge>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
