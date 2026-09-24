/** The console shell and the router.
 *
 * Twelve screens plus the registry, all inside one layout so the shared socket in
 * `LiveProvider` survives navigation — switching from the waterfall to the belief map
 * must not drop the run being watched. Demo Mode is the exception: it renders outside the
 * chrome, because a projector should show the instruments and nothing else.
 *
 * Screens are lazy so the first paint does not pay for three.js and echarts; the shell,
 * the palette and the socket are all that ship in the entry chunk.
 */

import { AnimatePresence, motion } from "framer-motion";
import { Suspense, lazy, useEffect, useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";

import { ErrorBoundary } from "@/components/shell/ErrorBoundary";
import { Backdrop } from "@/components/shell/Backdrop";
import { DataBanner } from "@/components/shell/DataBanner";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { LoadingState } from "@/components/ui";
import { navFor } from "@/lib/nav";

const CommandCenter = lazy(() => import("@/screens/CommandCenter"));
const BeliefMap = lazy(() => import("@/screens/BeliefMap"));
const DecisionInspector = lazy(() => import("@/screens/DecisionInspector"));
const MemoryVisualizer = lazy(() => import("@/screens/MemoryVisualizer"));
const Arena = lazy(() => import("@/screens/Arena"));
const AblationLab = lazy(() => import("@/screens/AblationLab"));
const ExperimentLab = lazy(() => import("@/screens/ExperimentLab"));
const Analytics = lazy(() => import("@/screens/Analytics"));
const Replay = lazy(() => import("@/screens/Replay"));
const Timeline = lazy(() => import("@/screens/Timeline"));
const Registry = lazy(() => import("@/screens/Registry"));
const Reports = lazy(() => import("@/screens/Reports"));
const DemoMode = lazy(() => import("@/screens/DemoMode"));
const NotFound = lazy(() => import("@/screens/NotFound"));

export function App() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  // The document title is how a judge with six tabs open finds the console again.
  useEffect(() => {
    const screen = navFor(location.pathname);
    document.title = screen ? `AAMS-X · ${screen.label}` : "AAMS-X · Active Sensing Console";
  }, [location.pathname]);

  if (location.pathname === "/demo") {
    return (
      <>
        <Backdrop />
        <ErrorBoundary where="Demo Mode">
          <Suspense fallback={<LoadingState label="Preparing the presentation view" />}>
            <DemoMode />
          </Suspense>
        </ErrorBoundary>
      </>
    );
  }

  return (
    <>
      <Backdrop />
      <div className="flex h-screen w-full overflow-hidden">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((prior) => !prior)} />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar />
          <DataBanner />
          <main className="min-h-0 flex-1 overflow-y-auto">
            <ErrorBoundary where={navFor(location.pathname)?.label}>
              <Suspense fallback={<LoadingState label="Loading instruments" />}>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={location.pathname}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    className="min-h-full"
                  >
                    <Routes location={location}>
                      <Route path="/" element={<CommandCenter />} />
                      <Route path="/replay" element={<Replay />} />
                      <Route path="/timeline" element={<Timeline />} />
                      <Route path="/belief" element={<BeliefMap />} />
                      <Route path="/decision" element={<DecisionInspector />} />
                      <Route path="/memory" element={<MemoryVisualizer />} />
                      <Route path="/arena" element={<Arena />} />
                      <Route path="/ablation" element={<AblationLab />} />
                      <Route path="/lab" element={<ExperimentLab />} />
                      <Route path="/analytics" element={<Analytics />} />
                      <Route path="/registry" element={<Registry />} />
                      <Route path="/reports" element={<Reports />} />
                      <Route path="*" element={<NotFound />} />
                    </Routes>
                  </motion.div>
                </AnimatePresence>
              </Suspense>
            </ErrorBoundary>
          </main>
        </div>
      </div>
    </>
  );
}
