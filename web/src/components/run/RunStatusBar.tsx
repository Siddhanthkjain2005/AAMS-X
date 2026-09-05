/** The run's own controls: progress, scrub, cancel, replay.
 *
 * The scrub cursor is the one piece of state that changes what every other panel shows.
 * Dragging it off the live edge freezes the belief map, the decision inspector and the
 * memory view at that step so a claim can be examined; releasing it returns to following
 * the stream. The badge says which mode you are in, because a frozen console that looks
 * live is the most dangerous thing this UI could do.
 */

import { Ban, Radio, Rewind, SkipForward } from "lucide-react";

import { useCancelExperiment, useReplayExperiment } from "@/api/queries";
import { Badge, Button, LiveDot, ProgressBar } from "@/components/ui";
import { duration, int, num } from "@/lib/format";
import { useLive } from "@/state/LiveProvider";
import { useSession } from "@/state/session";

export function RunStatusBar() {
  const { state, frames } = useLive();
  const experimentId = useSession((session) => session.experimentId);
  const cursor = useSession((session) => session.cursor);
  const setCursor = useSession((session) => session.setCursor);
  const setExperimentId = useSession((session) => session.setExperimentId);
  const cancel = useCancelExperiment();
  const replay = useReplayExperiment();

  const session = state.session;
  const retained = frames?.size ?? 0;
  const running = session?.status === "running" || session?.status === "queued";
  const frozen = cursor !== null;

  if (!experimentId) return null;

  return (
    <div className="panel lit flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
      <div className="flex min-w-0 items-center gap-2">
        <LiveDot active={state.status === "streaming"} tone={frozen ? "warn" : "accent"} />
        <span className="mono truncate text-[11px] text-ink-dim">
          {session?.label ?? experimentId}
        </span>
        <Badge tone={statusTone(session?.status)}>{session?.status ?? state.status}</Badge>
        {frozen && <Badge tone="warn">frozen at frame {int(cursor + 1)}</Badge>}
      </div>

      <div className="flex min-w-48 flex-1 items-center gap-3">
        <ProgressBar
          value={session?.progress ?? 0}
          tone={frozen ? "warn" : "accent"}
          showSweep={running}
          className="flex-1"
        />
        <span className="mono shrink-0 text-[10px] text-faint">
          {num((session?.progress ?? 0) * 100, 0)}% · {int(state.frameCount)} frames
          {session?.duration_sec ? ` · ${duration(session.duration_sec)}` : ""}
        </span>
      </div>

      {retained > 1 && (
        <input
          type="range"
          min={0}
          max={retained - 1}
          value={cursor ?? retained - 1}
          onChange={(event) => {
            const next = Number(event.target.value);
            setCursor(next >= retained - 1 ? null : next);
          }}
          aria-label="Scrub through retained frames"
          className="h-4 w-44 cursor-pointer appearance-none bg-transparent
            [&::-webkit-slider-runnable-track]:h-1 [&::-webkit-slider-runnable-track]:rounded-full
            [&::-webkit-slider-runnable-track]:bg-line
            [&::-webkit-slider-thumb]:mt-[-5px] [&::-webkit-slider-thumb]:size-3.5
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-ink"
        />
      )}

      <div className="flex shrink-0 items-center gap-1.5">
        {frozen && (
          <Button size="sm" icon={<SkipForward className="size-3" />} onClick={() => setCursor(null)}>
            Live edge
          </Button>
        )}
        {running ? (
          <Button
            size="sm"
            variant="danger"
            icon={<Ban className="size-3" />}
            disabled={cancel.isPending}
            onClick={() => cancel.mutate(experimentId)}
          >
            Cancel
          </Button>
        ) : (
          <Button
            size="sm"
            icon={<Rewind className="size-3" />}
            disabled={replay.isPending}
            onClick={() =>
              replay.mutate(
                { id: experimentId, paceHz: 60 },
                { onSuccess: (started) => setExperimentId(started.experiment_id) },
              )
            }
          >
            Replay
          </Button>
        )}
      </div>

      {state.error && (
        <p className="mono w-full text-[11px] text-bad">
          <Radio className="mr-1 inline size-3" />
          {state.error}
        </p>
      )}
    </div>
  );
}

function statusTone(status: string | undefined) {
  switch (status) {
    case "running":
      return "accent" as const;
    case "completed":
      return "good" as const;
    case "failed":
      return "bad" as const;
    case "cancelled":
    case "cancelling":
      return "warn" as const;
    default:
      return "neutral" as const;
  }
}
