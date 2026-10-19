// The intro's 3D scene, seen through the goalkeeper's eyes.
import { useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { ballTextures, grassTexture } from './textures';
import { BALL } from './ballPhysics';
import { EYE, SPIN, frameAt, T_KICK } from './timeline';

const LINE = 0.12;        // painted line width (m)
const PITCH_L = 105, PITCH_W = 68;

/** A flat painted strip between two points on the ground. */
function Strip({ a, b }: { a: [number, number]; b: [number, number] }) {
  const dx = b[0] - a[0], dz = b[1] - a[1];
  const length = Math.hypot(dx, dz);
  return (
    <mesh position={[(a[0] + b[0]) / 2, 0.006, (a[1] + b[1]) / 2]} rotation={[-Math.PI / 2, 0, -Math.atan2(dz, dx)]}>
      <planeGeometry args={[length + LINE, LINE]} />
      <meshStandardMaterial color="#e8ece8" roughness={0.9} />
    </mesh>
  );
}

function Box({ x0, x1, z0, z1 }: { x0: number; x1: number; z0: number; z1: number }) {
  return (<>
    <Strip a={[x0, z0]} b={[x1, z0]} /><Strip a={[x1, z0]} b={[x1, z1]} />
    <Strip a={[x1, z1]} b={[x0, z1]} /><Strip a={[x0, z1]} b={[x0, z0]} />
  </>);
}

/** Part of a circle painted on the ground; angles measured in the ring's plane (see RingGeometry). */
function Arc({ cx, cz, r, start, length }: { cx: number; cz: number; r: number; start: number; length: number }) {
  return (
    <mesh position={[cx, 0.006, cz]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[r - LINE / 2, r + LINE / 2, 96, 1, start, length]} />
      <meshStandardMaterial color="#e8ece8" roughness={0.9} />
    </mesh>
  );
}

function Pitch() {
  const grass = useMemo(() => {
    const t = grassTexture();
    t.repeat.set(1, 130 / 11);       // stripes 5.5 m wide across the pitch
    return t;
  }, []);
  const arcStart = Math.asin(5.5 / 9.15);   // the "D" outside each penalty area
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, -PITCH_L / 2]} receiveShadow>
        <planeGeometry args={[96, 130]} />
        <meshStandardMaterial map={grass} roughness={0.95} />
      </mesh>
      {/* outline and halfway line */}
      <Box x0={-PITCH_W / 2} x1={PITCH_W / 2} z0={0} z1={-PITCH_L} />
      <Strip a={[-PITCH_W / 2, -PITCH_L / 2]} b={[PITCH_W / 2, -PITCH_L / 2]} />
      <Arc cx={0} cz={-PITCH_L / 2} r={9.15} start={0} length={Math.PI * 2} />
      {/* our end: penalty area, goal area, spot, D */}
      <Box x0={-20.16} x1={20.16} z0={0} z1={-16.5} />
      <Box x0={-9.16} x1={9.16} z0={0} z1={-5.5} />
      <Arc cx={0} cz={-11} r={9.15} start={arcStart} length={Math.PI - 2 * arcStart} />
      <mesh position={[0, 0.007, -11]} rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[0.12, 24]} /><meshStandardMaterial color="#e8ece8" /></mesh>
      {/* far end */}
      <Box x0={-20.16} x1={20.16} z0={-PITCH_L} z1={-PITCH_L + 16.5} />
      <Box x0={-9.16} x1={9.16} z0={-PITCH_L} z1={-PITCH_L + 5.5} />
      <Arc cx={0} cz={-PITCH_L + 11} r={9.15} start={Math.PI + arcStart} length={Math.PI - 2 * arcStart} />
      <Goal z={-PITCH_L} />
    </group>
  );
}

function Goal({ z }: { z: number }) {
  const post = (x: number) => (
    <mesh position={[x, 1.22, z]}><cylinderGeometry args={[0.06, 0.06, 2.44, 16]} /><meshStandardMaterial color="#f4f4f4" /></mesh>
  );
  return (
    <group>
      {post(-3.66)}{post(3.66)}
      <mesh position={[0, 2.44, z]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[0.06, 0.06, 7.44, 16]} /><meshStandardMaterial color="#f4f4f4" /></mesh>
    </group>
  );
}

function Ball({ ballRef }: { ballRef: React.RefObject<THREE.Mesh | null> }) {
  const tex = useMemo(() => ballTextures(2048), []);
  return (
    <mesh ref={ballRef} castShadow>
      <sphereGeometry args={[BALL.radius, 96, 48]} />
      <meshStandardMaterial map={tex.map} bumpMap={tex.bump} bumpScale={0.6} roughness={0.42} metalness={0} />
    </mesh>
  );
}

/** Stand-in for the kicker until the motion-captured player arrives (slice 2). */
function StandIn({ kickerRef }: { kickerRef: React.RefObject<THREE.Group | null> }) {
  return (
    <group ref={kickerRef}>
      <mesh position={[0, 0.95, 0]} castShadow><capsuleGeometry args={[0.2, 1.1, 8, 16]} /><meshStandardMaterial color="#13213a" roughness={0.7} /></mesh>
      <mesh position={[0, 1.72, 0]} castShadow><sphereGeometry args={[0.12, 24, 16]} /><meshStandardMaterial color="#2a1d16" /></mesh>
    </group>
  );
}

const SPIN_AXIS = new THREE.Vector3(...SPIN).normalize();
const SPIN_RATE = Math.hypot(...SPIN);

function Driver({ time, ballRef, kickerRef, onFrame }: {
  time: () => number;
  ballRef: React.RefObject<THREE.Mesh | null>;
  kickerRef: React.RefObject<THREE.Group | null>;
  onFrame: (black: number) => void;
}) {
  const { camera } = useThree();
  const look = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    const t = time();
    const f = frameAt(t);
    if (ballRef.current) {
      ballRef.current.position.set(...f.ball);
      ballRef.current.quaternion.setFromAxisAngle(SPIN_AXIS, Math.max(0, f.s - T_KICK) * SPIN_RATE);
    }
    if (kickerRef.current) {
      kickerRef.current.position.set(...f.kicker);
    }
    // Keeper's head: a slow breathing sway, plus a sharp shake when the ball hits the gloves.
    const sway = Math.sin(t * 1.7) * 0.012, bob = Math.sin(t * 3.4) * 0.006;
    const shake = f.shake * 0.03;
    camera.position.set(EYE[0] + sway + Math.sin(t * 90) * shake, EYE[1] + bob + Math.cos(t * 77) * shake, EYE[2]);
    look.set(...f.look);
    camera.lookAt(look);
    onFrame(f.black);
  });
  return null;
}

export default function IntroScene({ time, onFrame }: { time: () => number; onFrame: (black: number) => void }) {
  const ballRef = useRef<THREE.Mesh>(null);
  const kickerRef = useRef<THREE.Group>(null);
  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      gl={{ antialias: true, preserveDrawingBuffer: true }}
      camera={{ fov: 40, near: 0.03, far: 500, position: EYE }}
    >
      <color attach="background" args={['#04060a']} />
      <fog attach="fog" args={['#04060a', 70, 260]} />
      <hemisphereLight args={['#8ea6c8', '#0b160d', 0.35]} />
      <directionalLight position={[-30, 45, 10]} intensity={1.6} castShadow shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-20} shadow-camera-right={20} shadow-camera-top={20} shadow-camera-bottom={-20} />
      <directionalLight position={[35, 40, -80]} intensity={0.9} />
      <Pitch />
      <Ball ballRef={ballRef} />
      <StandIn kickerRef={kickerRef} />
      <Driver time={time} ballRef={ballRef} kickerRef={kickerRef} onFrame={onFrame} />
    </Canvas>
  );
}
