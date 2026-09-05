/** The reproducibility registry — every run this install has executed, and what it would
 * take to reproduce one.
 *
 * This screen is the answer to "can you prove that number?". Everything on it is a stored
 * fact rather than a derived claim, and three of those facts are easy to misread, so they
 * are stated in the UI rather than left to a caveat in a paper:
 *
 * 1. **The config hash is not a result hash.** `config_hash` covers scenario + scheduler +
 *    seed + ablation flags only. Two rows sharing a hash were asked the same question; they
 *    answer identically only if `code_version` and `scheduler_version` also match. So the
 *    table groups by hash and marks a group as reproducible or divergent accordingly.
 *
 * 2. **Replay re-executes.** `POST /experiments/{id}/replay` rebuilds the stored
 *    `ScenarioSpec` and runs the episode again from the stored seed — it does not replay a
 *    cached picture, and it deliberately does not re-resolve `scenario_id`, because the
 *    window index can move underneath a preset. The route also 422s on anything whose
 *    stored `kind` is not `episode`, so batch rows show a disabled button that says why.
 *
 * 3. **Timestamps here are ISO text, not epoch seconds.** The registry stores them as
 *    TEXT; the live session summary uses floats. `isoClock`/`isoStamp` accept both.
 */

import {
  Boxes,
  CircleSlash,
  Clock,
  Copy,
  FileText,
  FlaskConical,
  GitCommitHorizontal,
  Hash,
  RotateCcw,
  Search,
  ShieldCheck,
  ShieldAlert,
  Telescope,
  X,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import {
  useActive,
  useCancelExperiment,
  useHistory,
  useReplayExperiment,
} from "@/api/queries";
import type { RegistryRecord, SessionSummary } from "@/api/types";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  LiveDot,
  LoadingState,
  Panel,
  ProgressBar,
  Select,
  Stat,
  Tabs,
} from "@/components/ui";
import {
  duration,
  int,
  isoClock,
  isoElapsed,
  isoStamp,
  metricLabel,
  num,
  policyLabel,
} from "@/lib/format";
import { PALETTE, policyColor } from "@/lib/palette";
import { cn } from "@/lib/cn";
import { useSession } from "@/state/session";

const KINDS = [
  { value: "", label: "All kinds" },
  { value: "episode", label: "Episode" },
  { value: "arena", label: "Arena" },
  { value: "ablation", label: "Ablation" },
];

const STATUSES = [
  { value: "", label: "Any status" },
  { value: "finished", label: "Finished" },
  { value: "running", label: "Running" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
];

const LIMITS = [
  { value: "50", label: "50 most recent" },
  { value: "120", label: "120 most recent" },
  { value: "300", label: "300 most recent" },
  { value: "500", label: "500 · registry cap" },
];

/** A hash group: every row that asked the identical question. */
interface HashGroup {
  hash: string;
  rows: RegistryRecord[];
  /** Same question *and* same code and scheduler versions throughout. */
  reproducible: boolean;
  versions: string[];
}

export default function Registry() {
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [limit, setLimit] = useState("120");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const historyQuery = { limit: Number(limit), ...(kind ? { kind } : {}) };
  const history = useHistory(historyQuery);
  const active = useActive();

  const experimentId = useSession((state) => state.experimentId);
  const reportSelection = useSession((state) => state.reportSelection);
  const setExperimentId = useSession((state) => state.setExperimentId);
  const toggleReportSelection = useSession(
    (state) => state.toggleReportSelection,
  );

  const replay = useReplayExperiment();
  const cancel = useCancelExperiment();
  const navigate = useNavigate();

  const rows = useMemo(() => {
    const all = history.data?.experiments ?? [];
    const needle = search.trim().toLowerCase();
    return all.filter((row) => {
      if (status && row.status !== status) return false;
      if (!needle) return true;
      return (
        row.experiment_id.toLowerCase().includes(needle) ||
        row.config_hash.toLowerCase().includes(needle) ||
        row.scenario_id.toLowerCase().includes(needle) ||
        row.scheduler.toLowerCase().includes(needle) ||
        row.ablation.toLowerCase().includes(needle) ||
        row.recordings.some((recording) =>
          recording.toLowerCase().includes(needle),
        )
      );
    });
  }, [history.data, search, status]);

  /** Grouping is over the *filtered* rows, so a group's count means "shown", not "stored". */
  const groups = useMemo<HashGroup[]>(() => {
    const byHash = new Map<string, RegistryRecord[]>();
    for (const row of rows) {
      const bucket = byHash.get(row.config_hash);
      if (bucket) bucket.push(row);
      else byHash.set(row.config_hash, [row]);
    }
    return [...byHash.entries()].map(([hash, bucket]) => {
      const versions = [
        ...new Set(
          bucket.map((row) => `${row.code_version} / ${row.scheduler_version}`),
        ),
      ];
      return {
        hash,
        rows: bucket,
        reproducible: versions.length === 1,
        versions,
      };
    });
  }, [rows]);

  const divergent = groups.filter(
    (group) => group.rows.length > 1 && !group.reproducible,
  );
  const repeated = groups.filter((group) => group.rows.length > 1);
  const failed = rows.filter((row) => row.status === "failed" || row.error);
  const running = active.data?.active ?? [];
  const codeVersions = [...new Set(rows.map((row) => row.code_version))];

  if (history.isLoading)
    return <LoadingState label="Reading the experiment registry" />;
  if (history.error) {
    return (
      <ErrorState
        error={history.error}
        onRetry={() => void history.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Reproducibility registry"
        subtitle="every run this install executed · SQLite, one row per experiment"
        actions={
          <div className="flex items-center gap-2">
            <Badge>
              <Boxes className="size-3" />
              {int(history.data?.count ?? 0)} stored
            </Badge>
            {reportSelection.length > 0 && (
              <Badge tone="mag">
                <FileText className="size-3" />
                {reportSelection.length} queued for report
              </Badge>
            )}
          </div>
        }
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <Field label="Kind" hint="filtered by the server">
            <Select value={kind} onChange={setKind} options={KINDS} />
          </Field>
          <Field label="Status" hint="filtered in the browser">
            <Select value={status} onChange={setStatus} options={STATUSES} />
          </Field>
          <Field label="Window" hint="most recent first">
            <Select value={limit} onChange={setLimit} options={LIMITS} />
          </Field>
          <Field label="Search" hint="id, hash, scenario, scheduler, recording">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-faint" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="a1b2c3…"
                spellCheck={false}
                className="mono h-9 w-full rounded-md border border-line bg-void pl-8 pr-8 text-xs text-ink placeholder:text-faint focus:border-accent/60 focus:outline-none"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  aria-label="Clear search"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-faint hover:text-ink"
                >
                  <X className="size-3.5" />
                </button>
              )}
            </div>
          </Field>
        </div>
      </Panel>

      <Panel flush>
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3.5 md:grid-cols-3 xl:grid-cols-6">
          <Stat
            label="Rows shown"
            value={int(rows.length)}
            hint={`of ${int(history.data?.count ?? 0)} stored`}
          />
          <Stat
            label="Distinct questions"
            value={int(groups.length)}
            hint="unique config hashes"
            tone="signal"
          />
          <Stat
            label="Repeated"
            value={int(repeated.length)}
            hint="hashes run more than once"
            tone={repeated.length ? "accent" : "ink"}
          />
          <Stat
            label="Version-divergent"
            value={int(divergent.length)}
            hint="same question, different code"
            tone={divergent.length ? "warn" : "good"}
          />
          <Stat
            label="Failed"
            value={int(failed.length)}
            hint="status failed or error set"
            tone={failed.length ? "bad" : "good"}
          />
          <Stat
            label="Code versions"
            value={codeVersions.length ? codeVersions.length : "—"}
            hint={codeVersions.slice(0, 2).join(", ") || "no rows"}
            tone={codeVersions.length > 1 ? "warn" : "ink"}
          />
        </div>
      </Panel>

      {running.length > 0 && (
        <Panel
          title="Running now"
          subtitle="live sessions held in server memory · they join the table when they finish"
          actions={
            <Badge tone="accent">
              <LiveDot active />
              {running.length} active
            </Badge>
          }
          flush
        >
          <ul className="divide-y divide-line">
            {running.map((session) => (
              <RunningRow
                key={session.experiment_id}
                session={session}
                selected={session.experiment_id === experimentId}
                cancelling={
                  cancel.isPending && cancel.variables === session.experiment_id
                }
                onInspect={() => {
                  setExperimentId(session.experiment_id);
                  navigate("/inspector");
                }}
                onCancel={() => cancel.mutate(session.experiment_id)}
              />
            ))}
          </ul>
        </Panel>
      )}

      <Panel
        title="Stored runs"
        subtitle="grouped by configuration hash · scenario + scheduler + seed + flags"
        actions={
          replay.isError ? (
            <Badge tone="bad">
              <CircleSlash className="size-3" />
              replay refused
            </Badge>
          ) : replay.isSuccess ? (
            <Badge tone="good">
              <RotateCcw className="size-3" />
              replay queued
            </Badge>
          ) : null
        }
        flush
      >
        {rows.length === 0 ? (
          <EmptyState
            icon={<FlaskConical className="size-5 text-faint" />}
            title={
              history.data?.count
                ? "No stored run matches these filters"
                : "Nothing has been run on this install yet"
            }
            detail={
              history.data?.count
                ? "Widen the window or clear the search — the registry keeps every run, so an empty view here is the filter, not the archive."
                : "Launch an episode from the Experiment Lab, or an arena from the Algorithm Arena. Every run is written to the registry the moment it starts, including the ones that fail."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1180px] border-collapse text-left">
              <thead>
                <tr className="hairline text-faint">
                  <Th className="w-[26px]" />
                  <Th>Experiment</Th>
                  <Th>Kind</Th>
                  <Th>Scenario</Th>
                  <Th>Policy</Th>
                  <Th className="text-right">Seed</Th>
                  <Th>Status</Th>
                  <Th className="text-right">Started</Th>
                  <Th className="text-right">Took</Th>
                  <Th>Versions</Th>
                  <Th className="text-right">Actions</Th>
                </tr>
              </thead>
              {groups.map((group) => (
                <GroupBody
                  key={group.hash}
                  group={group}
                  currentId={experimentId}
                  reportSelection={reportSelection}
                  expanded={expanded}
                  onExpand={(id) =>
                    setExpanded((prior) => (prior === id ? null : id))
                  }
                  onInspect={(id) => {
                    setExperimentId(id);
                    navigate("/inspector");
                  }}
                  onReplay={(id) => replay.mutate({ id })}
                  onToggleReport={toggleReportSelection}
                  replayingId={
                    replay.isPending ? (replay.variables?.id ?? null) : null
                  }
                />
              ))}
            </table>
          </div>
        )}
      </Panel>

      <ReplayNotice replay={replay} />
      <Provenance />
    </div>
  );
}

function Th({
  children,
  className,
}: {
  children?: ReactNode;
  className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "eyebrow whitespace-nowrap px-3 py-2 font-semibold",
        className,
      )}
    >
      {children}
    </th>
  );
}

/** A live session. Its times are epoch floats, not the registry's ISO text. */
function RunningRow({
  session,
  selected,
  cancelling,
  onInspect,
  onCancel,
}: {
  session: SessionSummary;
  selected: boolean;
  cancelling: boolean;
  onInspect: () => void;
  onCancel: () => void;
}) {
  const cancellable =
    session.status === "running" || session.status === "queued";
  return (
    <li
      className={cn(
        "flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 transition-colors",
        selected ? "bg-accent/5" : "hover:bg-panel-2/60",
      )}
    >
      <LiveDot
        active={cancellable}
        tone={session.status === "failed" ? "bad" : "accent"}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="mono truncate text-xs text-ink">
            {session.label}
          </span>
          <Badge tone="neutral">{session.kind}</Badge>
          {selected && <Badge tone="accent">inspecting</Badge>}
        </div>
        <p className="mono mt-1 truncate text-[10px] text-faint">
          {session.experiment_id} · {session.scenario_id} ·{" "}
          {int(session.n_frames)} frames · {duration(session.duration_sec)}
        </p>
      </div>
      <div className="w-40 shrink-0">
        <ProgressBar value={session.progress} showSweep={cancellable} />
        <p className="mono mt-1 text-right text-[10px] text-faint">
          {(session.progress * 100).toFixed(0)}% · {session.status}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          size="sm"
          icon={<Telescope className="size-3.5" />}
          onClick={onInspect}
        >
          Inspect
        </Button>
        <Button
          size="sm"
          variant="danger"
          icon={<CircleSlash className="size-3.5" />}
          disabled={!cancellable || cancelling}
          onClick={onCancel}
        >
          {cancelling ? "Cancelling" : "Cancel"}
        </Button>
      </div>
      {session.error && (
        <p className="mono w-full text-[10px] text-bad">{session.error}</p>
      )}
    </li>
  );
}

/**
 * One `<tbody>` per configuration hash.
 *
 * The group header is the honest part of this table: a hash tells you two runs were asked
 * the same question, and nothing more. If the rows inside disagree about `code_version` or
 * `scheduler_version` then re-running one will not necessarily reproduce the other, so the
 * group is marked divergent and the differing versions are listed.
 */
function GroupBody({
  group,
  currentId,
  reportSelection,
  expanded,
  onExpand,
  onInspect,
  onReplay,
  onToggleReport,
  replayingId,
}: {
  group: HashGroup;
  currentId: string | null;
  reportSelection: string[];
  expanded: string | null;
  onExpand: (id: string) => void;
  onInspect: (id: string) => void;
  onReplay: (id: string) => void;
  onToggleReport: (id: string) => void;
  replayingId: string | null;
}) {
  const repeated = group.rows.length > 1;
  return (
    <tbody className="border-t border-line">
      <tr className="bg-void/60">
        <td colSpan={11} className="px-3 py-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Hash className="size-3 text-faint" />
            <span className="mono text-[11px] text-signal">{group.hash}</span>
            <span className="text-[10px] text-faint">
              {repeated
                ? `${group.rows.length} runs of this configuration`
                : "one run"}
            </span>
            {repeated &&
              (group.reproducible ? (
                <Badge tone="good">
                  <ShieldCheck className="size-3" />
                  same code · comparable
                </Badge>
              ) : (
                <Badge tone="warn">
                  <ShieldAlert className="size-3" />
                  {group.versions.length} version pairs · not a reproduction
                </Badge>
              ))}
            <CopyButton value={group.hash} label="hash" />
          </div>
        </td>
      </tr>
      {group.rows.map((row) => (
        <RegistryRow
          key={row.experiment_id}
          row={row}
          current={row.experiment_id === currentId}
          inReport={reportSelection.includes(row.experiment_id)}
          open={expanded === row.experiment_id}
          replaying={replayingId === row.experiment_id}
          onExpand={() => onExpand(row.experiment_id)}
          onInspect={() => onInspect(row.experiment_id)}
          onReplay={() => onReplay(row.experiment_id)}
          onToggleReport={() => onToggleReport(row.experiment_id)}
        />
      ))}
    </tbody>
  );
}

const STATUS_TONE: Record<
  string,
  "good" | "warn" | "bad" | "accent" | "neutral"
> = {
  finished: "good",
  running: "accent",
  queued: "accent",
  failed: "bad",
  cancelled: "warn",
  cancelling: "warn",
};

/** One stored run. The replay button is the interesting control — see the note below. */
function RegistryRow({
  row,
  current,
  inReport,
  open,
  replaying,
  onExpand,
  onInspect,
  onReplay,
  onToggleReport,
}: {
  row: RegistryRecord;
  current: boolean;
  inReport: boolean;
  open: boolean;
  replaying: boolean;
  onExpand: () => void;
  onInspect: () => void;
  onReplay: () => void;
  onToggleReport: () => void;
}) {
  // The route reads `config["kind"]`, not the column, and 422s on anything but an episode.
  const storedKind = String(
    (row.config as { kind?: unknown }).kind ?? row.kind,
  );
  const isEpisode = storedKind === "episode";
  const elapsed = isoElapsed(row.created_at, row.finished_at);
  const hasResult = Object.keys(row.metrics ?? {}).length > 0;

  return (
    <>
      <tr
        className={cn(
          "border-t border-line/60 align-middle transition-colors",
          current ? "bg-accent/[0.07]" : "hover:bg-panel-2/50",
        )}
      >
        <td className="px-1 py-2 text-center">
          <button
            type="button"
            onClick={onExpand}
            aria-expanded={open}
            aria-label={
              open ? "Hide stored configuration" : "Show stored configuration"
            }
            className={cn(
              "mono size-5 rounded text-[10px] text-faint transition-colors hover:bg-line hover:text-ink",
              open && "bg-line text-ink",
            )}
          >
            {open ? "−" : "+"}
          </button>
        </td>
        <td className="max-w-[220px] px-3 py-2">
          <div className="flex items-center gap-1.5">
            <span
              className="mono truncate text-[11px] text-ink"
              title={row.experiment_id}
            >
              {row.experiment_id}
            </span>
            <CopyButton value={row.experiment_id} label="id" />
          </div>
          {row.recordings.length > 0 && (
            <p
              className="mono mt-0.5 truncate text-[10px] text-faint"
              title={row.recordings.join(", ")}
            >
              {row.recordings.length} recording
              {row.recordings.length === 1 ? "" : "s"} · {row.recordings[0]}
            </p>
          )}
        </td>
        <td className="px-3 py-2">
          <Badge tone={storedKind === "episode" ? "neutral" : "signal"}>
            {storedKind}
          </Badge>
        </td>
        <td
          className="mono max-w-[170px] truncate px-3 py-2 text-[11px] text-ink-dim"
          title={row.scenario_id}
        >
          {row.scenario_id || "—"}
        </td>
        <td className="px-3 py-2">
          <span
            className="mono text-[11px]"
            style={{
              color: row.scheduler ? policyColor(row.scheduler) : PALETTE.muted,
            }}
          >
            {row.scheduler ? policyLabel(row.scheduler) : "—"}
          </span>
          {row.ablation && row.ablation !== "full" && (
            <p className="mono mt-0.5 text-[10px] text-warn">{row.ablation}</p>
          )}
        </td>
        <td className="mono px-3 py-2 text-right text-[11px] text-ink-dim">
          {row.seed}
        </td>
        <td className="px-3 py-2">
          <Badge tone={STATUS_TONE[row.status] ?? "neutral"}>
            {row.status}
          </Badge>
        </td>
        <td
          className="mono px-3 py-2 text-right text-[11px] text-ink-dim"
          title={isoStamp(row.created_at)}
        >
          {isoClock(row.created_at)}
        </td>
        <td className="mono px-3 py-2 text-right text-[11px] text-ink-dim">
          {elapsed === null ? "—" : duration(elapsed)}
        </td>
        <td className="px-3 py-2">
          <p className="mono text-[10px] text-muted">
            {row.code_version || "—"}
          </p>
          <p className="mono text-[10px] text-faint">
            {row.scheduler_version || "—"}
          </p>
        </td>
        <td className="px-3 py-2">
          <div className="flex items-center justify-end gap-1.5">
            <Button
              size="sm"
              variant={current ? "primary" : "ghost"}
              icon={<Telescope className="size-3.5" />}
              onClick={onInspect}
              title="Load this run into the explain screens"
            >
              {current ? "Loaded" : "Inspect"}
            </Button>
            <Button
              size="sm"
              icon={<RotateCcw className="size-3.5" />}
              disabled={!isEpisode || replaying}
              onClick={onReplay}
              title={
                isEpisode
                  ? "Re-execute this episode from its stored scenario, seed and flags"
                  : `Replay covers single episodes; this row is a ${storedKind} batch (the API returns 422)`
              }
            >
              {replaying ? "Queued" : "Replay"}
            </Button>
            <Button
              size="sm"
              variant={inReport ? "primary" : "subtle"}
              icon={<FileText className="size-3.5" />}
              disabled={!hasResult}
              onClick={onToggleReport}
              title={
                hasResult
                  ? "Queue this run for the report generator"
                  : "This run stored no metrics, so a report cannot cite it"
              }
            >
              {inReport ? "Queued" : "Report"}
            </Button>
          </div>
        </td>
      </tr>
      {row.error && (
        <tr className="border-t border-bad/20 bg-bad/[0.06]">
          <td />
          <td colSpan={10} className="px-3 py-1.5">
            <p className="mono text-[10px] leading-relaxed text-bad">
              {row.error}
            </p>
          </td>
        </tr>
      )}
      {open && (
        <tr className="border-t border-line/60 bg-void/70">
          <td />
          <td colSpan={10} className="px-3 py-3">
            <ConfigDrawer row={row} />
          </td>
        </tr>
      )}
    </>
  );
}

/**
 * The stored configuration, exactly as the registry holds it.
 *
 * This is the drawer that makes the row auditable, so it shows the JSON rather than a
 * prettified summary — the hash was computed over this object (sorted keys, no spaces), and
 * a reader checking a claim needs the object, not a paraphrase of it.
 */
function ConfigDrawer({ row }: { row: RegistryRecord }) {
  const [tab, setTab] = useState<"config" | "metrics">("config");
  const metricEntries = Object.entries(row.metrics ?? {});
  const scenario = (
    row.config as { scenario?: { windows?: unknown[]; kind?: string } }
  ).scenario;
  const windowCount = Array.isArray(scenario?.windows)
    ? scenario.windows.length
    : null;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "config", label: "Stored configuration" },
            { value: "metrics", label: "Metrics", count: metricEntries.length },
          ]}
        />
        <span className="flex-1" />
        {windowCount !== null && (
          <Badge tone="neutral">
            <Boxes className="size-3" />
            {int(windowCount)} windows spliced
          </Badge>
        )}
        <CopyButton
          value={JSON.stringify(
            tab === "config" ? row.config : row.metrics,
            null,
            2,
          )}
          label="JSON"
        />
      </div>

      {tab === "config" ? (
        <>
          <pre className="mono max-h-72 overflow-auto rounded-md border border-line bg-void px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
            {JSON.stringify(row.config, null, 2)}
          </pre>
          <p className="text-[10px] leading-relaxed text-faint">
            The configuration hash{" "}
            <span className="mono text-signal">{row.config_hash}</span> is the
            first 16 hex characters of SHA-256 over the scenario, scheduler,
            seed and ablation flags with sorted keys. Replay rebuilds the
            scenario from <span className="mono">config.scenario</span> above
            rather than re-resolving{" "}
            <span className="mono">{row.scenario_id || "the preset id"}</span>,
            because the window index can move underneath a preset and a replay
            must not quietly run a different set of recordings.
          </p>
        </>
      ) : metricEntries.length === 0 ? (
        <p className="text-[11px] text-faint">
          This run stored no metrics. That is the registry being literal: a row
          is written when a run starts, so a crashed or cancelled run keeps its
          configuration and loses its result.
        </p>
      ) : (
        <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2 xl:grid-cols-3">
          {metricEntries.map(([metric, value]) => (
            <div
              key={metric}
              className="flex items-baseline justify-between gap-3 border-b border-line/50 py-1"
            >
              <span className="truncate text-[10px] text-muted">
                {metricLabel(metric)}
              </span>
              <span className="mono shrink-0 text-[11px] text-ink">
                {num(value, 4)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Copy to clipboard, with the two-second acknowledgement that makes it feel like it worked. */
function CopyButton({ value, label }: { value: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(value).then(() => {
          setDone(true);
          window.setTimeout(() => setDone(false), 2000);
        });
      }}
      className={cn(
        "mono inline-flex shrink-0 items-center gap-1 rounded px-1 py-0.5 text-[10px] transition-colors",
        done ? "text-good" : "text-faint hover:bg-line hover:text-ink",
      )}
      aria-label={`Copy ${label}`}
      title={`Copy ${label}`}
    >
      <Copy className="size-3" />
      {done ? "copied" : ""}
    </button>
  );
}

/** What the replay mutation actually did, including the refusal the API is entitled to give. */
function ReplayNotice({
  replay,
}: {
  replay: ReturnType<typeof useReplayExperiment>;
}) {
  if (!replay.isError && !replay.isSuccess) return null;
  if (replay.isError) {
    return (
      <Panel title="Replay refused" className="border-bad/30">
        <p className="text-[11px] leading-relaxed text-bad">
          {String(replay.error)}
        </p>
        <p className="mt-2 text-[11px] leading-relaxed text-faint">
          The API refuses a replay it cannot honour rather than approximating
          one. The two refusals you will see are{" "}
          <span className="mono">422</span> for a batch — an arena or ablation
          row is many episodes and the endpoint covers one — and{" "}
          <span className="mono">404</span> for an id no longer in the registry.
        </p>
      </Panel>
    );
  }
  const data = replay.data;
  return (
    <Panel title="Replay running" className="border-good/30">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="good">
          <RotateCcw className="size-3" />
          re-executing
        </Badge>
        <span className="mono text-[11px] text-ink">{data?.experiment_id}</span>
        <span className="text-[10px] text-faint">from</span>
        <span className="mono text-[11px] text-muted">{data?.replay_of}</span>
        <span className="text-[10px] text-faint">·</span>
        <span className="mono text-[11px] text-signal">
          {data?.config_hash}
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-faint">
        This is a fresh execution of the stored episode, not a cached picture
        being played back. The new run gets its own experiment id and its own
        registry row; if the code has not changed since the original, the
        configuration hash above will match and so will every metric.
      </p>
    </Panel>
  );
}

/** What this screen is claiming, in one paragraph, where a reviewer will look for it. */
function Provenance() {
  return (
    <Panel
      title="What the registry does and does not prove"
      subtitle="read before citing a row"
    >
      <div className="grid gap-4 text-[11px] leading-relaxed text-faint md:grid-cols-3">
        <div>
          <p className="flex items-center gap-1.5 font-semibold text-ink-dim">
            <Hash className="size-3.5 text-signal" />
            The hash is the question
          </p>
          <p className="mt-1.5">
            <span className="mono text-signal">config_hash</span> covers the
            scenario, the scheduler, the seed and the ablation flags — nothing
            else. Two rows sharing it were asked the same question. They are the
            same <em>answer</em> only when{" "}
            <span className="mono">code_version</span> and{" "}
            <span className="mono">scheduler_version</span> match too, which is
            why a repeated hash with mixed versions is flagged rather than
            merged.
          </p>
        </div>
        <div>
          <p className="flex items-center gap-1.5 font-semibold text-ink-dim">
            <RotateCcw className="size-3.5 text-accent" />
            Replay re-runs
          </p>
          <p className="mt-1.5">
            Replay rebuilds the stored{" "}
            <span className="mono">ScenarioSpec</span> and executes the episode
            again from the stored seed. It deliberately does not re-resolve the
            preset id: the window index is rebuilt whenever new data is fetched,
            so a preset can point at different recordings than it did last week.
            Batches cannot be replayed from here.
          </p>
        </div>
        <div>
          <p className="flex items-center gap-1.5 font-semibold text-ink-dim">
            <Clock className="size-3.5 text-warn" />
            Every row is kept
          </p>
          <p className="mt-1.5">
            A row is written when a run <em>starts</em>, so failures and
            cancellations stay visible with their configuration intact and no
            metrics. Nothing is pruned to make the history look better, and a
            run with no metrics cannot be queued for a report — the generator
            only cites values an execution produced.
          </p>
        </div>
      </div>
      <p className="mt-3 flex items-center gap-1.5 border-t border-line pt-3 text-[10px] text-muted">
        <GitCommitHorizontal className="size-3.5 shrink-0 text-faint" />
        Times are stored as ISO-8601 UTC text by the registry and shown in your
        local zone; a live session reports epoch seconds instead, and both are
        handled by the same formatter.
      </p>
    </Panel>
  );
}
