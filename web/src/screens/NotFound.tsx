import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { Button, EmptyState, Panel } from "@/components/ui";
import { NAV } from "@/lib/nav";

export default function NotFound() {
  return (
    <div className="p-4">
      <Panel className="min-h-96">
        <EmptyState
          title="That screen does not exist"
          detail="The console has thirteen screens. Every one of them is in the sidebar."
          icon={<Compass className="size-5 text-faint" />}
          action={
            <div className="mt-2 flex max-w-lg flex-wrap justify-center gap-1.5">
              {NAV.map((item) => (
                <Link key={item.path} to={item.path}>
                  <Button size="sm" variant="subtle">
                    {item.label}
                  </Button>
                </Link>
              ))}
            </div>
          }
        />
      </Panel>
    </div>
  );
}
