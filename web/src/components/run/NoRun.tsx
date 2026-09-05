/** What every explain-screen shows before there is anything to explain.
 *
 * Not zeros. A belief map with a flat posterior and a decision inspector with eight empty
 * bars look like measurements of a quiet band; they are the absence of a run. So the
 * screens say so and offer the two ways to get one.
 */

import { Play, Rewind } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, EmptyState } from "@/components/ui";

export function NoRun({ what }: { what: string }) {
  return (
    <EmptyState
      title={`No run is loaded, so there is no ${what} to show`}
      detail="Start an episode from the Command Center, or open a finished run from the Registry. Nothing on this screen is generated without a run behind it."
      icon={<Play className="size-5 text-faint" />}
      action={
        <div className="mt-1 flex gap-2">
          <Link to="/">
            <Button size="sm" variant="primary" icon={<Play className="size-3.5" />}>
              Command Center
            </Button>
          </Link>
          <Link to="/registry">
            <Button size="sm" icon={<Rewind className="size-3.5" />}>
              Registry
            </Button>
          </Link>
        </div>
      }
    />
  );
}
