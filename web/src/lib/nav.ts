/** The screen map. One list, so the sidebar, the command palette and the router agree. */

import {
  Activity,
  Boxes,
  BrainCircuit,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  Layers,
  ListTree,
  Radar,
  ScrollText,
  SlidersHorizontal,
  Sparkles,
  Swords,
} from "lucide-react";
import type { ComponentType } from "react";

export interface NavItem {
  path: string;
  label: string;
  /** Shown under the label in the sidebar; also the page subtitle. */
  blurb: string;
  icon: ComponentType<{ className?: string }>;
  group: "operate" | "explain" | "evaluate" | "evidence";
}

export const NAV: NavItem[] = [
  {
    path: "/",
    label: "Command Center",
    blurb: "Live waterfall, KPI row, launch controls",
    icon: LayoutDashboard,
    group: "operate",
  },
  {
    path: "/replay",
    label: "Real Spectrum Replay",
    blurb: "Cached recordings and their provenance",
    icon: Radar,
    group: "operate",
  },
  {
    path: "/timeline",
    label: "Event Timeline",
    blurb: "What happened, step by step",
    icon: ListTree,
    group: "operate",
  },
  {
    path: "/belief",
    label: "Belief Map",
    blurb: "Occupancy posterior, uncertainty, staleness",
    icon: Activity,
    group: "explain",
  },
  {
    path: "/decision",
    label: "Decision Inspector",
    blurb: "Why this window, term by term",
    icon: SlidersHorizontal,
    group: "explain",
  },
  {
    path: "/memory",
    label: "Associative Memory",
    blurb: "Context prototypes and Hopfield retrieval",
    icon: BrainCircuit,
    group: "explain",
  },
  {
    path: "/arena",
    label: "Algorithm Arena",
    blurb: "Six policies, identical seeds",
    icon: Swords,
    group: "evaluate",
  },
  {
    path: "/ablation",
    label: "Ablation Lab",
    blurb: "Remove one component at a time",
    icon: Layers,
    group: "evaluate",
  },
  {
    path: "/lab",
    label: "Experiment Lab",
    blurb: "Presets, weights, custom scenarios",
    icon: FlaskConical,
    group: "evaluate",
  },
  {
    path: "/analytics",
    label: "Analytics & Pareto",
    blurb: "Significance, effect size, frontier",
    icon: Gauge,
    group: "evaluate",
  },
  {
    path: "/registry",
    label: "Registry",
    blurb: "Every run, hashed and replayable",
    icon: Boxes,
    group: "evidence",
  },
  {
    path: "/reports",
    label: "Reports",
    blurb: "Self-contained HTML, executed values only",
    icon: ScrollText,
    group: "evidence",
  },
  {
    path: "/demo",
    label: "Demo Mode",
    blurb: "Full-screen presentation view",
    icon: Sparkles,
    group: "evidence",
  },
];

export const GROUP_LABELS: Record<NavItem["group"], string> = {
  operate: "Operate",
  explain: "Explain",
  evaluate: "Evaluate",
  evidence: "Evidence",
};

export function navFor(pathname: string): NavItem | undefined {
  return NAV.find((item) => item.path === pathname) ?? NAV.find((item) => item.path === "/");
}
