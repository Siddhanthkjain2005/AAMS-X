import { Component, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import type { OrbitControls as OrbitControlsType } from 'three-stdlib'
import * as THREE from 'three'
import { Box, Focus, Move3D, RotateCcw, ScanLine } from 'lucide-react'
import { useCurrentFrame, useMission } from '../stores/mission'
import { PageHeader, Panel, Toggle, TruthBoundary } from '../components/ui'
import { TransportBar } from '../components/Controls'
import { Waterfall } from '../visualizations/Waterfall'
import { useVisibleFrames } from '../hooks/useVisibleFrames'
import type { Frame, ReceiverConfig } from '../types'

type CameraView = 'orbit' | 'reset' | 'top' | 'side' | 'follow'

class CubeBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <CubeFallback /> : this.props.children }
}
function CubeFallback() {
  return <div className="cube-fallback"><Box size={30} /><h3>WebGL is unavailable in this browser</h3><p>The same observation trace remains accessible in the 2D spectrum view.</p><Waterfall height={310} /></div>
}

function Camera({ view, band, width, bands }: { view: CameraView; band: number; width: number; bands: number }) {
  const { camera } = useThree()
  const controls = useRef<OrbitControlsType>(null)
  useEffect(() => {
    camera.up.set(0, 0, 1)
    if (view === 'top') camera.position.set(5, 3, 17)
    else if (view === 'side') camera.position.set(5, -15, 4)
    else if (view === 'follow') camera.position.set(15, (band + width / 2) / bands * 6 - 7, 7)
    else if (view === 'reset') camera.position.set(14, -10, 11)
    if (view !== 'orbit') controls.current?.target.set(view === 'follow' ? 9 : 5, view === 'follow' ? (band + width / 2) / bands * 6 : 3, 0.8)
    controls.current?.update()
  }, [view, camera, band, width, bands])
  return <OrbitControls ref={controls} makeDefault target={[5, 3, 0.8]} minDistance={4} maxDistance={30} enableDamping dampingFactor={0.12} />
}

function Scene({ frames, receiver, energy, belief, truth, path, detections, view }: { frames: Frame[]; receiver: ReceiverConfig; energy: boolean; belief: boolean; truth: boolean; path: boolean; detections: boolean; view: CameraView }) {
  const data = useMemo(() => {
    const recent = frames.slice(-180)
    const stride = Math.max(1, Math.ceil(recent.length * receiver.bands / 9000))
    const sampled = recent.filter((_, i) => i % stride === 0)
    const positions: number[] = [], colors: number[] = [], hitPositions: number[] = []
    const trail: [number, number, number][] = []
    const surface: number[] = [], indices: number[] = []
    const low = receiver.noise_floor_db, range = Math.max(16, receiver.snr_db + 4)
    const z = (v: number) => Math.max(0.04, Math.min(3.6, (v - low + 2) / range * 3.6))
    sampled.forEach((frame, i) => {
      const p = frame.policies.magnts ?? Object.values(frame.policies)[0]
      if (!p) return
      const x = i / Math.max(1, sampled.length - 1) * 10
      const observations = truth && frame.evaluation ? frame.evaluation.energy.map((v, band) => ({ band, energy: v, detected: false })) : p.observations.values
      observations.forEach(v => {
        if (v.energy === null) return
        const height = z(v.energy)
        positions.push(x, (v.band + 0.5) / receiver.bands * 6, height)
        const c = Math.max(0, Math.min(1, height / 3.6))
        colors.push(0.26 + c * 0.43, 0.24 + c * 0.39, 0.45 + c * 0.25)
      })
      p.observations.values.filter(v => v.detected && v.energy !== null).forEach(v => hitPositions.push(x, (v.band + 0.5) / receiver.bands * 6, z(v.energy!) + 0.06))
      trail.push([x, (p.selected_window.start + p.selected_window.width / 2) / receiver.bands * 6, 3.9])
      p.belief.probability.forEach((probability, b) => {
        surface.push(x, (b + 0.5) / receiver.bands * 6, probability * 3.5)
        if (i > 0 && b > 0) {
          const k = i * receiver.bands + b
          indices.push(k, k - 1, k - receiver.bands, k - 1, k - receiver.bands - 1, k - receiver.bands)
        }
      })
    })
    return { positions: new Float32Array(positions), colors: new Float32Array(colors), hitPositions: new Float32Array(hitPositions), trail, surface: new Float32Array(surface), indices }
  }, [frames, receiver, truth])
  const latest = frames[frames.length - 1]
  const p = latest?.policies.magnts ?? Object.values(latest?.policies ?? {})[0]
  const band = p?.selected_window.start ?? 0
  const pointsGeometry = useMemo(() => new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(data.positions, 3)).setAttribute('color', new THREE.BufferAttribute(data.colors, 3)), [data])
  const hitsGeometry = useMemo(() => new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(data.hitPositions, 3)), [data])
  const surfaceGeometry = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(data.surface, 3)).setIndex(data.indices)
    geometry.computeVertexNormals()
    return geometry
  }, [data])
  useEffect(() => () => { pointsGeometry.dispose(); hitsGeometry.dispose(); surfaceGeometry.dispose() }, [pointsGeometry, hitsGeometry, surfaceGeometry])
  return <>
    <color attach="background" args={['#0b1018']} /><ambientLight intensity={1.1} /><directionalLight position={[4, -3, 9]} intensity={2} />
    <Camera view={view} band={band} width={receiver.window_width} bands={receiver.bands} />
    <gridHelper args={[12, 24, '#354154', '#1c2839']} rotation={[Math.PI / 2, 0, 0]} position={[5, 3, -0.06]} />
    <Line points={[[0, 0, 0], [10.7, 0, 0]]} color="#52627a" lineWidth={1} /><Line points={[[0, 0, 0], [0, 6.6, 0]]} color="#52627a" lineWidth={1} /><Line points={[[0, 0, 0], [0, 0, 4.3]]} color="#52627a" lineWidth={1} />
    <Html position={[5.5, -0.7, 0]} center><span className="cube-axis">X / TIME →</span></Html><Html position={[-0.9, 3.6, 0]} center><span className="cube-axis">Y / FREQUENCY</span></Html><Html position={[0, 0, 4.65]} center><span className="cube-axis">Z / {belief ? 'BELIEF / ENERGY' : 'SIGNAL ENERGY'}</span></Html>
    {energy && <points geometry={pointsGeometry}><pointsMaterial vertexColors size={0.065} sizeAttenuation transparent opacity={0.85} depthWrite={false} /></points>}
    {belief && data.surface.length > 3 && <mesh geometry={surfaceGeometry}><meshStandardMaterial color="#a390d4" transparent opacity={0.35} side={THREE.DoubleSide} roughness={0.75} depthWrite={false} /></mesh>}
    {path && data.trail.length > 1 && <Line points={data.trail} color="#c0e88c" lineWidth={1.3} transparent opacity={0.75} />}
    {detections && <points geometry={hitsGeometry}><pointsMaterial color="#d7f7ac" size={0.11} sizeAttenuation transparent opacity={0.95} depthWrite={false} /></points>}
    {p && <group position={[10, (band + receiver.window_width / 2) / receiver.bands * 6, 1.85]}><mesh><boxGeometry args={[0.035, receiver.window_width / receiver.bands * 6, 3.7]} /><meshBasicMaterial color="#c0e88c" transparent opacity={0.15} depthWrite={false} /></mesh><Line points={[[0, -receiver.window_width / receiver.bands * 3, -1.85], [0, -receiver.window_width / receiver.bands * 3, 1.85], [0, receiver.window_width / receiver.bands * 3, 1.85], [0, receiver.window_width / receiver.bands * 3, -1.85]]} color="#c0e88c" lineWidth={1} /></group>}
  </>
}

export default function SpectrumCube() {
  const s = useMission()
  const frame = useCurrentFrame()
  const frames = useVisibleFrames()
  const [view, setView] = useState<CameraView>('orbit')
  const [energy, setEnergy] = useState(true), [belief, setBelief] = useState(false), [path, setPath] = useState(true), [detections, setDetections] = useState(true)
  const receiver = s.run?.config.receiver ?? s.config.receiver
  return <>
    <PageHeader eyebrow="SPATIAL INTELLIGENCE" title="Spectrum Intelligence Cube" description="Interception is a time × frequency search problem. Explore the observations in three dimensions." action={<span className="badge violet"><Box size={13} />BUFFERED WEBGL SCENE</span>} />
    <TransportBar />
    <Panel className="cube-panel"><div className="cube-toolbar"><div className="segmented">{([{ id: 'orbit', icon: Move3D, label: 'Orbit' }, { id: 'reset', icon: RotateCcw, label: 'Reset' }, { id: 'top', icon: Box, label: 'Top' }, { id: 'side', icon: ScanLine, label: 'Side' }, { id: 'follow', icon: Focus, label: 'Follow receiver' }] as const).map(v => <button className={view === v.id ? 'active' : ''} key={v.id} onClick={() => setView(v.id)}><v.icon size={13} />{v.label}</button>)}</div><span className="muted small-copy">Drag to orbit · scroll to zoom</span></div>
      <div className="cube-scene"><CubeBoundary><Suspense fallback={<div className="empty-state">Preparing local WebGL scene…</div>}><Canvas camera={{ position: [14, -10, 11], up: [0, 0, 1], fov: 44 }} dpr={[1, 1.6]} gl={{ antialias: true, powerPreference: 'high-performance' }} fallback={<p>WebGL is unavailable. The observation trace is available in the Command Center waterfall.</p>}><Scene frames={frames} receiver={receiver} energy={energy} belief={belief} truth={s.judge} path={path} detections={detections} view={view} /></Canvas></Suspense></CubeBoundary>
        <div className="cube-hud"><span className="eyebrow">SPECTRUM SPACE</span><strong>{s.run ? `SLOT ${frame?.step ?? 0}` : 'AWAITING OBSERVATIONS'}</strong><span>{receiver.bands} frequency bands · last {Math.min(frames.length, 180)} time slots</span></div><div className="cube-legend"><span><i className="legend-dot violet" />{s.judge ? 'Evaluation energy' : 'Observed energy'}</span><span><i className="legend-dot green" />Receiver / decisions</span><span className="muted">Height is normalized for visualization</span></div>
      </div><div className="cube-layers"><span className="eyebrow">LAYERS</span><Toggle checked={energy} onChange={setEnergy} label="Measured / simulated energy" /><Toggle checked={belief} onChange={setBelief} label="Belief surface" /><Toggle checked={s.judge} onChange={value => void s.setJudge(value)} label="Judge / full recording" /><Toggle checked={path} onChange={setPath} label="Decision path" /><Toggle checked={detections} onChange={setDetections} label="Detections" /></div>
    </Panel>
    <div className="three-column cube-explain"><Panel><span className="axis-letter">X</span><h3>Time reveals recurrence</h3><p>Repeated peaks form temporal structures. The scene shows up to 180 recent slots from the actual experiment.</p></Panel><Panel><span className="axis-letter violet-text">Y</span><h3>Frequency reveals agility</h3><p>Frequency changes form shifting ridges. Only observed regions appear unless Judge View is explicitly enabled.</p></Panel><Panel><span className="axis-letter accent">Z</span><h3>Height reveals evidence</h3><p>Compare energy with the learned belief surface. The narrow scanning plane marks the receiver’s current bandwidth.</p></Panel></div><TruthBoundary />
  </>
}
