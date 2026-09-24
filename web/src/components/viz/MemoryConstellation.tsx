/** The associative memory as a constellation.
 *
 * Stored contexts sit on a ring; the current context is the node at the centre. Sphere
 * radius is the prototype's utility, colour is its recency, and the beam from the centre
 * is the modern-Hopfield retrieval weight for *this* step — so the picture answers "what
 * does the memory hold, and which of it is being used right now" in one frame.
 *
 * Two honesty constraints shape it. Only the prototypes the run actually stored are drawn,
 * so an empty memory is an empty ring rather than a ring of placeholders. And a prototype
 * that the current readout does not name gets no beam at all, rather than a faint one —
 * a dim beam would imply a small weight where the readout reported none.
 */

import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import type { MemoryPrototype, MemoryReadout } from "@/api/types";
import { usePrefersReducedMotion } from "@/hooks/useMeasure";
import { cn } from "@/lib/cn";
import { MEMORY_LUT, lutOffset } from "@/lib/palette";

const RING_RADIUS = 6.2;

function lutColour(lut: Uint8ClampedArray, t: number): THREE.Color {
  const offset = lutOffset(t);
  return new THREE.Color(lut[offset] / 255, lut[offset + 1] / 255, lut[offset + 2] / 255);
}

interface ConstellationProps {
  prototypes: MemoryPrototype[];
  readout: MemoryReadout | null;
  /** Newest step the run has reached — used to age each prototype's colour. */
  step: number;
  selected?: number | null;
  onSelect?: (id: number) => void;
}

function Nodes({ prototypes, readout, step, selected, onSelect }: ConstellationProps) {
  const group = useRef<THREE.Group>(null);
  const reduced = usePrefersReducedMotion();

  const weights = useMemo(() => {
    const map = new Map<number, number>();
    if (!readout) return map;
    readout.top_ids.forEach((id, index) => map.set(id, readout.top_weights[index] ?? 0));
    return map;
  }, [readout]);

  const nodes = useMemo(() => {
    const maxUtility = Math.max(...prototypes.map((entry) => entry.utility), 1e-6);
    return prototypes.map((prototype, index) => {
      const angle = (index / Math.max(1, prototypes.length)) * Math.PI * 2;
      const age = step > 0 ? Math.min(1, (step - prototype.last_step) / Math.max(1, step)) : 0;
      return {
        prototype,
        position: new THREE.Vector3(
          Math.cos(angle) * RING_RADIUS,
          Math.sin(index * 1.7) * 0.55,
          Math.sin(angle) * RING_RADIUS,
        ),
        radius: 0.26 + 0.5 * Math.min(1, prototype.utility / maxUtility),
        colour: lutColour(MEMORY_LUT, 0.25 + 0.75 * (1 - age)),
      };
    });
  }, [prototypes, step]);

  // Retrieval beams: one LineSegments object rebuilt only when the weight set changes.
  const beams = useMemo(() => {
    const active = nodes.filter((node) => (weights.get(node.prototype.id) ?? 0) > 0);
    const positions = new Float32Array(active.length * 6);
    const colours = new Float32Array(active.length * 6);
    active.forEach((node, index) => {
      positions.set([0, 0, 0, node.position.x, node.position.y, node.position.z], index * 6);
      const weight = weights.get(node.prototype.id) ?? 0;
      const tint = lutColour(MEMORY_LUT, 0.45 + 0.55 * weight);
      colours.set([tint.r * 0.3, tint.g * 0.3, tint.b * 0.3, tint.r, tint.g, tint.b], index * 6);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colours, 3));
    const material = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
    });
    return new THREE.LineSegments(geometry, material);
  }, [nodes, weights]);

  useFrame((_state, delta) => {
    if (group.current && !reduced) group.current.rotation.y += delta * 0.09;
  });

  const similarity = readout?.similarity ?? 0;

  return (
    <group ref={group}>
      <primitive object={beams} />

      {/* The current context. Recognised → teal and lit; unrecognised → hollow grey. */}
      <mesh>
        <icosahedronGeometry args={[0.52 + 0.24 * similarity, 2]} />
        <meshStandardMaterial
          color={readout?.recognised ? "#4fd1c5" : "#3a4a5a"}
          emissive={readout?.recognised ? "#4fd1c5" : "#000000"}
          emissiveIntensity={readout?.recognised ? 0.5 + similarity : 0}
          roughness={0.35}
          metalness={0.25}
          wireframe={!readout?.recognised}
        />
      </mesh>

      {nodes.map((node) => {
        const weight = weights.get(node.prototype.id) ?? 0;
        const isSelected = selected === node.prototype.id;
        const isTop = readout?.prototype_id === node.prototype.id;
        return (
          <mesh
            key={node.prototype.id}
            position={node.position}
            onClick={(event) => {
              event.stopPropagation();
              onSelect?.(node.prototype.id);
            }}
          >
            <sphereGeometry args={[node.radius * (isSelected ? 1.25 : 1), 24, 20]} />
            <meshStandardMaterial
              color={node.colour}
              emissive={node.colour}
              emissiveIntensity={isTop ? 0.95 : 0.12 + weight * 0.8}
              roughness={0.42}
              metalness={0.3}
            />
          </mesh>
        );
      })}
    </group>
  );
}

export function MemoryConstellation({
  className,
  caption = "ring = stored contexts · centre = this step's context · beam = Hopfield retrieval weight",
  ...props
}: ConstellationProps & { className?: string; caption?: string }) {
  return (
    <div className={cn("relative h-full w-full", className)}>
      <Canvas
        dpr={[1, 1.75]}
        camera={{ position: [0, 5.4, 12.4], fov: 44 }}
        gl={{ antialias: true, powerPreference: "high-performance" }}
      >
        <color attach="background" args={["#070a0e"]} />
        <fog attach="fog" args={["#070a0e", 12, 30]} />
        <ambientLight intensity={0.5} />
        <pointLight position={[0, 2, 0]} intensity={1.4} color="#a78bfa" distance={18} />
        <directionalLight position={[7, 9, 6]} intensity={0.7} color="#cfe9ff" />
        <Nodes {...props} />
        <OrbitControls
          enablePan={false}
          minDistance={7}
          maxDistance={22}
          maxPolarAngle={Math.PI / 1.9}
          target={[0, 0, 0]}
        />
      </Canvas>
      <p className="mono pointer-events-none absolute bottom-2 left-3 text-[9px] text-faint">
        {caption}
      </p>
    </div>
  );
}
