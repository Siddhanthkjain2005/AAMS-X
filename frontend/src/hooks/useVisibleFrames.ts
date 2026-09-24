import { useMemo } from 'react'
import { useCurrentFrame, useMission } from '../stores/mission'

export function useVisibleFrames() {
  const frames = useMission(s => s.frames)
  const current = useCurrentFrame()
  return useMemo(() => frames.slice(0, (current?.step ?? -1) + 1).filter(Boolean), [frames, current?.step])
}
