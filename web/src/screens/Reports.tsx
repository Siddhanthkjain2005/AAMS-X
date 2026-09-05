/** Report generation — the screen that turns a selection of executed runs into one file
 * somebody can email to a reviewer.
 *
 * The generator (`aamsx/reports/html.py`) is deliberately incapable of inventing a number:
 * a metric absent from a stored result renders as "not measured", a curve with fewer than
 * two points renders as no chart rather than a flat line, and an id with no stored result
 * becomes a section that says so. This screen mirrors that honesty forward — it counts how
 * many queued runs would render as "no stored result" *before* generating, because a report
 * with four empty sections is worse than a report with two full ones.
 *
 * The preview iframe is sandboxed with no allowances at all. The report needs no
 * JavaScript by design, so `sandbox=""` costs nothing and means a report can never reach
 * back into the console that rendered it.
 */

import {
  CheckCircle2,
  ExternalLink,
  FileText,
  FilePlus2,
  FolderOpen,
  Info,
  ListChecks,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { reportUrl } from "@/api/client";
import { useCreateReport, useHistory, useReports } from "@/api/queries";
import type { RegistryRecord, ReportSummary } from "@/api/types";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Panel,
  Spinner,
  Stat,
} from "@/components/ui";
import { bytes, int, isoClock, policyLabel, timestamp } from "@/lib/format";
import { policyColor } from "@/lib/palette";
import { cn } from "@/lib/cn";
import { useSession } from "@/state/session";

/** Resolution of a queued id against the registry window we can actually see. */
type Resolved =
  | { state: "ready"; row: RegistryRecord; metrics: number }
  | { state: "empty"; row: RegistryRecord }
  | { state: "unknown" };

export default function Reports() {
  const selection = useSession((state) => state.reportSelection);
  const toggleSelection = useSession((state) => state.toggleReportSelection);
  const clearSelection = useSession((state) => state.clearReportSelection);

  const [title, setTitle] = useState("AAMS-X Experiment Report");
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<string | null>(null);

  const history = useHistory({ limit: 500 });
  const reports = useReports();
  const create = useCreateReport();

  const byId = useMemo(() => {
    const map = new Map<string, RegistryRecord>();
    for (const row of history.data?.experiments ?? [])
      map.set(row.experiment_id, row);
    return map;
  }, [history.data]);

  const resolved = useMemo<[string, Resolved][]>(
    () =>
      selection.map((id) => {
        const row = byId.get(id);
        if (!row) return [id, { state: "unknown" }];
        const metrics = Object.keys(row.metrics ?? {}).length;
        return [
          id,
          metrics > 0
            ? { state: "ready", row, metrics }
            : { state: "empty", row },
        ];
      }),
    [selection, byId],
  );

  const ready = resolved.filter(([, entry]) => entry.state === "ready").length;
  const empty = resolved.filter(([, entry]) => entry.state === "empty").length;
  const unknown = resolved.filter(
    ([, entry]) => entry.state === "unknown",
  ).length;

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Report generator"
        subtitle="self-contained HTML · inline SVG · no CDN, no JavaScript needed to read it"
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={ready ? "accent" : "neutral"}>
              <ListChecks className="size-3" />
              {ready} of {selection.length} queued runs have results
            </Badge>
            {selection.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                icon={<Trash2 className="size-3.5" />}
                onClick={clearSelection}
              >
                Clear
              </Button>
            )}
          </div>
        }
      >
        <div className="grid gap-3 lg:grid-cols-[1fr_1fr_auto]">
          <Field label="Title" hint="printed at the head of the document">
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={140}
              className="h-9 w-full rounded-md border border-line bg-void px-3 text-xs text-ink placeholder:text-faint focus:border-accent/60 focus:outline-none"
            />
          </Field>
          <Field
            label="Notes"
            hint="context for a reader; rendered verbatim and escaped"
          >
            <input
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={600}
              placeholder="e.g. six seeds per arm, VALIDATION split only"
              className="h-9 w-full rounded-md border border-line bg-void px-3 text-xs text-ink placeholder:text-faint focus:border-accent/60 focus:outline-none"
            />
          </Field>
          <div className="flex items-end">
            <Button
              variant="primary"
              icon={
                create.isPending ? (
                  <Spinner className="size-3.5" />
                ) : (
                  <FilePlus2 className="size-4" />
                )
              }
              disabled={selection.length === 0 || create.isPending}
              onClick={() =>
                create.mutate(
                  {
                    experiment_ids: selection,
                    title: title.trim() || undefined,
                    notes: notes.trim() || undefined,
                  },
                  {
                    onSuccess: (report) => setPreview(report.name),
                  },
                )
              }
            >
              {create.isPending
                ? "Rendering"
                : `Generate from ${selection.length}`}
            </Button>
          </div>
        </div>

        {(empty > 0 || unknown > 0) && (
          <div className="mt-3 flex gap-2.5 rounded-md border border-warn/30 bg-warn/[0.06] px-3 py-2.5">
            <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn" />
            <div className="text-[11px] leading-relaxed text-ink-dim">
              {empty > 0 && (
                <p>
                  <span className="font-semibold text-warn">{empty}</span>{" "}
                  queued {empty === 1 ? "run has" : "runs have"} no stored
                  metrics — a failure, a cancellation or a run still in flight.
                  The generator will include {empty === 1 ? "it" : "them"} as a
                  section reading{" "}
                  <span className="mono">no stored result for this id</span>{" "}
                  rather than skipping {empty === 1 ? "it" : "them"} silently.
                </p>
              )}
              {unknown > 0 && (
                <p className={cn(empty > 0 && "mt-1.5")}>
                  <span className="font-semibold text-warn">{unknown}</span>{" "}
                  {unknown === 1 ? "id is" : "ids are"} outside the 500 most
                  recent registry rows, so this screen cannot say whether{" "}
                  {unknown === 1 ? "it has" : "they have"} a result. The server
                  checks again at render time.
                </p>
              )}
            </div>
          </div>
        )}
      </Panel>

      {create.isError && (
        <Panel title="Report could not be generated" className="border-bad/30">
          <ErrorState error={create.error} onRetry={() => create.reset()} />
        </Panel>
      )}

      {create.data && (
        <Panel
          title="Report ready"
          subtitle="written by the API from stored execution results"
          className="border-good/30"
          actions={
            <a
              href={reportUrl(create.data.name)}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex h-7 items-center gap-1.5 rounded-md border border-good/40 bg-good/10 px-2.5 text-[11px] font-semibold text-good transition-colors hover:bg-good/20"
            >
              <ExternalLink className="size-3.5" />
              Open standalone
            </a>
          }
        >
          <div className="grid gap-4 sm:grid-cols-4">
            <Stat
              label="Document"
              value={<CheckCircle2 className="size-6" />}
              hint={create.data.name}
              tone="good"
            />
            <Stat
              label="Runs requested"
              value={int(create.data.experiment_ids.length)}
              hint="including missing sections"
            />
            <Stat
              label="File size"
              value={bytes(create.data.size_bytes)}
              hint="one self-contained HTML file"
            />
            <Stat
              label="Dependencies"
              value="0"
              hint="no CDN · no JavaScript"
              tone="accent"
            />
          </div>
        </Panel>
      )}

      <div className="grid min-h-[390px] gap-3 xl:grid-cols-[minmax(360px,0.72fr)_minmax(0,1.28fr)]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            title="Queued experiment sections"
            subtitle="the order below becomes the document order"
            actions={
              selection.length > 0 ? (
                <Badge tone={empty || unknown ? "warn" : "good"}>
                  {selection.length} selected
                </Badge>
              ) : undefined
            }
            className="min-h-[230px]"
            bodyClassName="overflow-y-auto"
          >
            {history.isLoading && selection.length > 0 ? (
              <LoadingState label="Resolving selected runs" />
            ) : history.isError && selection.length > 0 ? (
              <ErrorState
                error={history.error}
                onRetry={() => void history.refetch()}
              />
            ) : selection.length === 0 ? (
              <EmptyState
                icon={<ListChecks className="size-5 text-faint" />}
                title="No experiments are queued"
                detail="Add completed episode, arena or ablation rows from the Registry. The queue is capped at 24 sections so a report stays reviewable."
                action={
                  <Link
                    to="/registry"
                    className="inline-flex h-7 items-center gap-1.5 rounded-md border border-line-bright px-2.5 text-[11px] font-semibold text-ink-dim transition-colors hover:bg-panel-2 hover:text-ink"
                  >
                    <FolderOpen className="size-3.5" />
                    Browse registry
                  </Link>
                }
              />
            ) : (
              <div className="space-y-2">
                {resolved.map(([id, entry], index) => (
                  <SelectionRow
                    key={id}
                    id={id}
                    index={index}
                    entry={entry}
                    onRemove={() => toggleSelection(id)}
                  />
                ))}
              </div>
            )}
          </Panel>

          <Panel
            title="Generated reports"
            subtitle="the latest 50 files retained by the server"
            bodyClassName="overflow-y-auto"
            className="min-h-[260px] flex-1"
          >
            {reports.isLoading ? (
              <LoadingState label="Reading report directory" />
            ) : reports.isError ? (
              <ErrorState
                error={reports.error}
                onRetry={() => void reports.refetch()}
              />
            ) : (reports.data?.reports.length ?? 0) === 0 ? (
              <EmptyState
                icon={<FileText className="size-5 text-faint" />}
                title="No generated reports yet"
                detail="Generate one from the queued execution results above; it will be written to the configured reports directory."
              />
            ) : (
              <div className="space-y-1.5">
                {reports.data?.reports.map((report) => (
                  <ReportRow
                    key={report.name}
                    report={report}
                    selected={preview === report.name}
                    onPreview={() => setPreview(report.name)}
                  />
                ))}
              </div>
            )}
          </Panel>
        </div>

        <Panel
          title="Document preview"
          subtitle="fully sandboxed · scripts, forms, navigation and same-origin access denied"
          flush
          actions={
            preview ? (
              <div className="flex items-center gap-1.5">
                <Badge tone="good">
                  <ShieldCheck className="size-3" />
                  isolated
                </Badge>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<X className="size-3.5" />}
                  onClick={() => setPreview(null)}
                >
                  Close
                </Button>
              </div>
            ) : undefined
          }
        >
          {preview ? (
            <iframe
              key={preview}
              title={`Preview of ${preview}`}
              src={reportUrl(preview)}
              sandbox=""
              referrerPolicy="no-referrer"
              className="h-full min-h-[520px] w-full border-0 bg-white"
            />
          ) : (
            <EmptyState
              icon={<FileText className="size-6 text-faint" />}
              title="Choose a report to preview"
              detail="The preview is deliberately more restricted than opening the file directly. Generated reports do not need scripts, network requests or access to this application."
            />
          )}
        </Panel>
      </div>

      <Panel
        title="What this document can support"
        subtitle="provenance rules enforced by the generator"
      >
        <div className="grid gap-4 text-[11px] leading-relaxed text-faint md:grid-cols-3">
          <HonestyNote
            icon={<ShieldCheck className="size-4 text-good" />}
            title="Executed values only"
          >
            Every number is loaded from the selected experiment&apos;s stored
            result. Missing metrics print{" "}
            <span className="mono text-ink-dim">not measured</span>; they are
            never inferred, interpolated or copied from another run.
          </HonestyNote>
          <HonestyNote
            icon={<FileText className="size-4 text-accent" />}
            title="Portable by design"
          >
            Styles and charts are embedded into one HTML file. Curves are inline
            SVG built from stored samples, and fewer than two samples produces
            no chart instead of a fabricated flat line.
          </HonestyNote>
          <HonestyNote
            icon={<Info className="size-4 text-warn" />}
            title="A report is not a rerun"
          >
            The document preserves what an execution produced; it does not prove
            the current code would reproduce it. Use the Registry replay control
            and compare code, scheduler and configuration versions for that
            claim.
          </HonestyNote>
        </div>
      </Panel>
    </div>
  );
}

function SelectionRow({
  id,
  index,
  entry,
  onRemove,
}: {
  id: string;
  index: number;
  entry: Resolved;
  onRemove: () => void;
}) {
  const row = entry.state === "unknown" ? null : entry.row;
  const tone =
    entry.state === "ready"
      ? "good"
      : entry.state === "empty"
        ? "warn"
        : "neutral";
  const label =
    entry.state === "ready"
      ? `${entry.metrics} stored metrics`
      : entry.state === "empty"
        ? "no stored metrics"
        : "outside recent window";

  return (
    <div className="group flex items-center gap-3 rounded-md border border-line bg-void/45 px-3 py-2.5">
      <span className="mono w-5 shrink-0 text-center text-[10px] text-faint">
        {index + 1}
      </span>
      {row && (
        <span
          className="h-7 w-0.5 shrink-0 rounded-full"
          style={{ background: policyColor(row.scheduler) }}
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          <span className="mono truncate text-[11px] text-ink">{id}</span>
          <Badge tone={tone} className="shrink-0">
            {label}
          </Badge>
        </div>
        <p className="mt-1 truncate text-[10px] text-faint">
          {row ? (
            <>
              {row.kind} · {policyLabel(row.scheduler)} ·{" "}
              {row.scenario_id || "unnamed scenario"} · seed {row.seed} ·{" "}
              {isoClock(row.created_at)}
            </>
          ) : (
            "The API will resolve this id while rendering."
          )}
        </p>
      </div>
      <Button
        size="sm"
        variant="ghost"
        icon={<X className="size-3.5" />}
        aria-label={`Remove ${id} from report`}
        className="opacity-60 group-hover:opacity-100"
        onClick={onRemove}
      >
        Remove
      </Button>
    </div>
  );
}

function ReportRow({
  report,
  selected,
  onPreview,
}: {
  report: ReportSummary;
  selected: boolean;
  onPreview: () => void;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border px-3 py-2.5 transition-colors",
        selected
          ? "border-accent/45 bg-accent/[0.07]"
          : "border-line bg-void/35 hover:bg-panel-2/55",
      )}
    >
      <FileText
        className={cn(
          "size-4 shrink-0",
          selected ? "text-accent" : "text-faint",
        )}
      />
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        onClick={onPreview}
      >
        <span className="mono block truncate text-[11px] text-ink-dim">
          {report.name}
        </span>
        <span className="mono mt-0.5 block text-[10px] text-faint">
          {timestamp(report.modified)} · {bytes(report.size_bytes)}
        </span>
      </button>
      <button
        type="button"
        className="rounded p-1.5 text-faint transition-colors hover:bg-line hover:text-accent"
        aria-label={`Preview ${report.name}`}
        onClick={onPreview}
      >
        <FolderOpen className="size-3.5" />
      </button>
      <a
        href={reportUrl(report.name)}
        target="_blank"
        rel="noreferrer noopener"
        aria-label={`Open ${report.name} in a new tab`}
        className="rounded p-1.5 text-faint transition-colors hover:bg-line hover:text-accent"
      >
        <ExternalLink className="size-3.5" />
      </a>
    </div>
  );
}

function HonestyNote({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="flex items-center gap-2 font-semibold text-ink-dim">
        {icon}
        {title}
      </p>
      <p className="mt-1.5">{children}</p>
    </div>
  );
}
