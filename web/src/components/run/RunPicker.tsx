/** Choose which run the explain-screens read from.
 *
 * Running sessions come first — during a demo the interesting run is the one streaming —
 * then the most recent completed ones. Picking a finished run loads its stored result over
 * the socket, which is why the same four screens work live and post-hoc.
 */

import { ChevronDown } from "lucide-react";

import { useActive, useHistory } from "@/api/queries";
import { Badge, LiveDot } from "@/components/ui";
import { isoClock, policyLabel } from "@/lib/format";
import { useSession } from "@/state/session";

export function RunPicker({ limit = 20 }: { limit?: number }) {
  const experimentId = useSession((state) => state.experimentId);
  const setExperimentId = useSession((state) => state.setExperimentId);
  const active = useActive();
  const history = useHistory({ limit });

  const running = active.data?.active ?? [];
  const runningIds = new Set(running.map((entry) => entry.experiment_id));
  const finished = (history.data?.experiments ?? []).filter(
    (record) => !runningIds.has(record.experiment_id),
  );

  return (
    <label className="relative flex items-center gap-2">
      <span className="sr-only">Run to inspect</span>
      {experimentId && runningIds.has(experimentId) && <LiveDot active />}
      <select
        value={experimentId ?? ""}
        onChange={(event) => setExperimentId(event.target.value || null)}
        className="mono h-7 max-w-72 appearance-none truncate rounded-md border border-line-bright bg-panel-2 pr-7 pl-2.5 text-[11px] text-ink transition-colors hover:border-accent-dim focus:border-accent focus:outline-none"
      >
        <option value="">— no run loaded —</option>
        {running.length > 0 && (
          <optgroup label="running">
            {running.map((entry) => (
              <option key={entry.experiment_id} value={entry.experiment_id}>
                {entry.label} · {Math.round(entry.progress * 100)}%
              </option>
            ))}
          </optgroup>
        )}
        {finished.length > 0 && (
          <optgroup label="recent">
            {finished.map((record) => (
              <option key={record.experiment_id} value={record.experiment_id}>
                {policyLabel(record.scheduler)} · {record.scenario_id} · seed{" "}
                {record.seed} · {isoClock(record.created_at)}
              </option>
            ))}
          </optgroup>
        )}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 size-3.5 text-faint" />
      {history.data && finished.length === 0 && running.length === 0 && (
        <Badge tone="warn">no runs yet</Badge>
      )}
    </label>
  );
}
