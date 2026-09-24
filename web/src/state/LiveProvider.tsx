/** One socket for the whole console.
 *
 * Every explain-screen wants the same live run. If each opened its own `WebSocket`, the
 * server would fan the same frames out four times and switching screens would drop the
 * history. So the stream is opened once here, at the shell, and shared by context.
 */

import { createContext, useContext, type ReactNode } from "react";

import { useExperimentStream, type LiveStream } from "@/hooks/useExperimentStream";
import { useSession } from "./session";

const LiveContext = createContext<LiveStream | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const experimentId = useSession((state) => state.experimentId);
  const live = useExperimentStream(experimentId);
  return <LiveContext.Provider value={live}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveStream {
  const value = useContext(LiveContext);
  if (!value) throw new Error("useLive must be used inside <LiveProvider>");
  return value;
}

/**
 * The frame a screen should draw: the scrub cursor when one is set, otherwise the live
 * edge. Returning `null` when there is nothing yet is intentional — screens render an
 * explicit empty state rather than zeros that look like measurements.
 */
export function useActiveFrame() {
  const { state, frames } = useLive();
  const cursor = useSession((session) => session.cursor);
  if (cursor === null) return state.latest;
  return frames?.at(cursor) ?? state.latest;
}
