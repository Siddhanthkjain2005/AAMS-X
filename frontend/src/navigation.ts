import { BookOpen, Box, BrainCircuit, ChartNoAxesCombined, Database, Fingerprint, FolderClock, LayoutDashboard, Swords, Timer, Workflow } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Page } from './types'

export interface NavigationItem { id: Page; title: string; icon: LucideIcon; description: string; tag?: string }
export const navigation: { group: string; pages: NavigationItem[] }[] = [
  { group: 'WORKSPACE', pages: [
    { id: 'command', title: 'Command Center', icon: LayoutDashboard, description: 'Overview, configuration, and demo launchpad' },
    { id: 'duel', title: 'Live Duel', icon: Swords, description: 'Compare two policies in one recorded or live world', tag: 'CORE' },
    { id: 'cube', title: 'Spectrum Cube', icon: Box, description: 'Explore observations in three dimensions', tag: '3D' },
    { id: 'library', title: 'Experiment Library', icon: FolderClock, description: 'Search, favorite, export, and replay saved experiments' },
  ] },
  { group: 'UNDERSTAND', pages: [
    { id: 'knowledge', title: 'AI Observability', icon: BrainCircuit, description: 'Inspect observed evidence and model uncertainty' },
    { id: 'periodic', title: 'Periodic Challenge', icon: Timer, description: 'Review recorded recurrence evidence' },
  ] },
  { group: 'RESEARCH', pages: [
    { id: 'benchmark', title: 'Benchmark Lab', icon: ChartNoAxesCombined, description: 'Review multi-seed comparisons and ablations' },
    { id: 'explorer', title: 'Dataset Explorer', icon: Database, description: 'Explore the included measured RF recording' },
    { id: 'provenance', title: 'Data Provenance', icon: Fingerprint, description: 'Inspect source availability, lineage, and checksums' },
    { id: 'architecture', title: 'Architecture', icon: Workflow, description: 'Understand the observation-only software boundary' },
    { id: 'methodology', title: 'Methodology', icon: BookOpen, description: 'Metric definitions, assumptions, and limitations' },
  ] },
]
export const allPages = navigation.flatMap(group => group.pages)
export const pageTitles = Object.fromEntries(allPages.map(page => [page.id, page.title])) as Record<Page, string>

export const tourSteps: { page: Page; title: string; description: string; focus: string }[] = [
  { page: 'duel', title: 'Two views. One experiment.', description: 'Compare the two observation histories. Both receivers use the same stored world and timing budget. This is a saved replay, paused for inspection.', focus: 'Look at the observation waterfalls and the recorded metrics below.' },
  { page: 'knowledge', title: 'Make the model visible.', description: 'Probability and uncertainty describe what has been learned from observations. Unobserved bands remain unknown.', focus: 'Switch between probability, uncertainty, and information gain.' },
  { page: 'cube', title: 'Explore another perspective.', description: 'The same recorded observations become a time × frequency × energy scene. Rotate the view to inspect the history.', focus: 'Try Top, Side, or Orbit. The data stays the same.' },
  { page: 'provenance', title: 'Know where the data came from.', description: 'Each source has an explicit status, scope, and transformation history. The included measured recording has no labelled emitter ground truth.', focus: 'Open the checksums and processing lineage for a source.' },
  { page: 'benchmark', title: 'Read the broader evidence.', description: 'Compare recorded runs across scenarios and seeds. Results vary by scenario; confidence intervals and ablations help show that variation.', focus: 'Review the recorded benchmark, then replay any individual run.' },
]

