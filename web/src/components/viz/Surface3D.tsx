/** The waterfall as terrain.
 *
 * Same numbers as the 2D instrument — `measured_db` where the receiver looked, the
 * posterior where it did not — but height as well as colour, which makes two things
 * legible that the flat view flattens: how far above threshold a detection actually was,
 * and how much of the band was never observed (the plateaus). It is the demo view, not the
 * measurement view: the 2D waterfall stays the reference because a rotated surface can
 * hide a column behind a ridge.
 *
 * The geometry is allocated once and mutated in place. Each new frame shifts every row one
 * step toward the viewer and writes the newest row at the near edge, so the cost per frame
 * is one typed-array copy plus `nRegions` vertex writes, independent of history depth.
 */

import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { FrameRing } from "@/api/stream";
import type { Frame } from "@/api/types";
import { usePrefersReducedMotion } from "@/hooks/useMeasure";
import { cn } from "@/lib/cn";
import { SPECTRUM_LUT, lutOffset } from "@/lib/palette";

const MARGIN_CEILING_DB = 14;
/** Terrain half-width in world units; the camera framing below assumes this. */
const SPAN = 10;
const HEIGHT_SCALE = 2.4;

interface SurfaceProps {
  frames: FrameRing | null;
  nRegions: number;
  /** History depth in steps. 72 keeps the far edge visible at this camera distance. */
  depth?: number;
  /**
   * Per-region height in [0, 1] for one frame. The default is the honest spectrum view;
   * pass a selector to build the same terrain from the belief or the uncertainty.
   */
  select?: (frame: Frame, region: number) => number;
  lut?: Uint8ClampedArray;
  /** Printed bottom-left. Say what height means, or the surface is only decoration. */
  caption?: string;
}

/** The default height rule, kept nameable so the caption can describe it. */
function spectrumHeight(frame: Frame, region: number): number {
  if (!frame.available) return 0;
  const index = frame.regions.indexOf(region);
  if (index >= 0) return Math.max(0, frame.measured_db[index] ?? 0) / MARGIN_CEILING_DB;
  // Inference, not measurement: the belief is drawn at 55% height so a plateau reads as
  // "not looked at" rather than as a measured null.
  return (frame.belief[region] ?? 0) * 0.55;
}

function Terrain({ frames, nRegions, depth = 72, select, lut }: SurfaceProps) {
  const cols = Math.max(2, nRegions);
  const rows = Math.max(2, depth);
  const heightOf = select ?? spectrumHeight;
  const ramp = lut ?? SPECTRUM_LUT;
  const lastStep = useRef(-1);

  // heights[row * cols + col]; row 0 = oldest (far), rows-1 = newest (near edge).
  const buffers = useMemo(
    () => ({ heights: new Float32Array(rows * cols), geometry: buildGeometry(rows, cols) }),
    [rows, cols],
  );
  useEffect(() => {
    lastStep.current = -1;
    const geometry = buffers.geometry;
    return () => geometry.dispose();
  }, [buffers]);

  const material = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.62,
        metalness: 0.12,
        side: THREE.DoubleSide,
      }),
    [],
  );
  useEffect(() => () => material.dispose(), [material]);

  useFrame(() => {
    if (!frames) return;
    const latest = frames.at(-1);
    if (!latest || latest.step === lastStep.current) return;

    const { heights, geometry } = buffers;
    const position = geometry.getAttribute("position") as THREE.BufferAttribute;
    const colour = geometry.getAttribute("color") as THREE.BufferAttribute;

    heights.copyWithin(0, cols);
    const base = (rows - 1) * cols;
    for (let col = 0; col < cols; col += 1) {
      heights[base + col] = Math.min(1.4, Math.max(0, heightOf(latest, col)));
    }

    for (let row = 0; row < rows; row += 1) {
      // Age is depth here; an un-faded horizon competes with the live edge for attention.
      const fade = 0.35 + 0.65 * (row / (rows - 1));
      for (let col = 0; col < cols; col += 1) {
        const index = row * cols + col;
        const elevation = heights[index];
        position.setY(index, elevation * HEIGHT_SCALE);
        const offset = lutOffset(elevation);
        colour.setXYZ(
          index,
          (ramp[offset] / 255) * fade,
          (ramp[offset + 1] / 255) * fade,
          (ramp[offset + 2] / 255) * fade,
        );
      }
    }
    position.needsUpdate = true;
    colour.needsUpdate = true;
    geometry.computeVertexNormals();
    lastStep.current = latest.step;
  });

  return (
    <group>
      <mesh geometry={buffers.geometry} material={material} />
      <mesh geometry={buffers.geometry}>
        <meshBasicMaterial wireframe color="#4fd1c5" transparent opacity={0.06} />
      </mesh>
      <mesh position={[0, 0.02, SPAN / 2 + 0.08]}>
        <boxGeometry args={[SPAN * 2, 0.05, 0.07]} />
        <meshBasicMaterial color="#4fd1c5" />
      </mesh>
    </group>
  );
}

/** Vertex grid over x ∈ [-SPAN, SPAN] (frequency) and z ∈ [-SPAN/2, SPAN/2] (time). */
function buildGeometry(rows: number, cols: number): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const count = rows * cols;
  const positions = new Float32Array(count * 3);
  const colours = new Float32Array(count * 3);

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const index = (row * cols + col) * 3;
      positions[index] = (col / (cols - 1) - 0.5) * SPAN * 2;
      positions[index + 1] = 0;
      positions[index + 2] = (row / (rows - 1) - 0.5) * SPAN;
    }
  }

  const indices: number[] = [];
  for (let row = 0; row < rows - 1; row += 1) {
    for (let col = 0; col < cols - 1; col += 1) {
      const a = row * cols + col;
      indices.push(a, a + cols, a + 1, a + 1, a + cols, a + cols + 1);
    }
  }

  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colours, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

export function Surface3D({
  frames,
  nRegions,
  depth,
  select,
  lut,
  caption = "height = dB above threshold · plateau = inferred, not measured · drag to orbit",
  className,
  autoRotate = true,
}: SurfaceProps & { className?: string; autoRotate?: boolean }) {
  const reduced = usePrefersReducedMotion();
  return (
    <div className={cn("relative h-full w-full", className)}>
      <Canvas
        dpr={[1, 1.75]}
        camera={{ position: [0, 7.5, 13.5], fov: 42 }}
        gl={{ antialias: true, powerPreference: "high-performance" }}
      >
        <color attach="background" args={["#070a0e"]} />
        <fog attach="fog" args={["#070a0e", 14, 34]} />
        <ambientLight intensity={0.55} />
        <directionalLight position={[6, 12, 8]} intensity={1.1} color="#cfe9ff" />
        <pointLight position={[-8, 4, -6]} intensity={0.5} color="#4fd1c5" />
        <Terrain frames={frames} nRegions={nRegions} depth={depth} select={select} lut={lut} />
        <gridHelper args={[40, 40, "#12202a", "#0d1620"]} position={[0, -0.02, 0]} />
        <OrbitControls
          enablePan={false}
          minDistance={8}
          maxDistance={26}
          maxPolarAngle={Math.PI / 2.15}
          autoRotate={autoRotate && !reduced}
          autoRotateSpeed={0.35}
          target={[0, 0.6, 0]}
        />
      </Canvas>
      <p className="mono pointer-events-none absolute bottom-2 left-3 text-[9px] text-faint">
        {caption}
      </p>
    </div>
  );
}
