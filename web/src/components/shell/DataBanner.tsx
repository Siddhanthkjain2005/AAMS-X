/** The backend's own warnings, shown verbatim.
 *
 * `/status` returns a `warnings` list when the offline cache is empty, when the window
 * index is missing, or when fewer than seven presets can be built from what is cached.
 * Those strings are written by the backend and printed unedited, because the alternative
 * — a console that looks fully operational on an empty cache — is exactly the failure
 * this project refuses to ship. Dismissable per session, not per page load.
 */

import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, X } from "lucide-react";
import { useState } from "react";

import { useStatus } from "@/api/queries";

export function DataBanner() {
  const status = useStatus();
  const [dismissed, setDismissed] = useState<string[]>([]);
  const warnings = (status.data?.warnings ?? []).filter((text) => !dismissed.includes(text));
  if (!warnings.length) return null;

  return (
    <AnimatePresence initial={false}>
      {warnings.map((text) => (
        <motion.div
          key={text}
          layout
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          className="overflow-hidden border-b border-warn/25 bg-warn/[0.07]"
        >
          <div className="flex items-start gap-3 px-5 py-2.5">
            <AlertTriangle className="mt-px size-4 shrink-0 text-warn" />
            <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-ink-dim">{text}</p>
            <button
              type="button"
              onClick={() => setDismissed((prior) => [...prior, text])}
              className="shrink-0 rounded p-0.5 text-faint transition-colors hover:text-ink"
              aria-label="Dismiss warning"
            >
              <X className="size-3.5" />
            </button>
          </div>
        </motion.div>
      ))}
    </AnimatePresence>
  );
}
