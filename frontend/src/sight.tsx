import {useFrame,useThree} from '@react-three/fiber';
import {useMemo,useRef} from 'react';
import * as THREE from 'three';
import {lobScope} from './scope';

// The heavy's lobbed-fire sight, rebuilt from scratch: a single tube in front of the eye, one
// magnified disc inside it, and the crosshair as UI over the canvas. Nothing else is modelled — no
// cradle, no eyecup — so nothing can sit inside the sight picture.
//
// The tube is a short cylinder with a slight flare. A straight tube projects its *far* rim well inside
// its *near* rim as seen from the eye, which reads as a hoop cutting across the magnified image; a
// 1.2x flare puts the far rim outside the disc, so the whole bore is clean glass.

const REAR_RADIUS = 0.085;
const FRONT_RADIUS = 0.103;
const TUBE_LENGTH = 0.05;
const EYE_GAP = 0.26;
// The metal rim that frames the glass. The flare puts both rims on the same circle, so an open shell
// only ever projected a hairline; the wall now carries a real annulus, twice the width of that line,
// and it grows outward from the bore so the magnified disc keeps its size.
const RIM_WIDTH = 0.0045;

/** NDC (half-height) radius of the magnified disc: the rear rim as the eye sees it. */
function apertureRadius(fovDeg: number) {
  const half = Math.tan((fovDeg * Math.PI) / 360);
  return (REAR_RADIUS / ((EYE_GAP - TUBE_LENGTH / 2) * half)) * 0.5;
}

const METAL = {color: '#23272c', metalness: 0.85, roughness: 0.36} as const;

/** The tube itself; its axis runs down the line of sight once the group is turned. */
function Tube() {
  const geometry = useMemo(() => {
    // Bore, outer wall and the rear annulus that reads as the scope's frame. The wall is what makes
    // the rim visible: the bare flare hides the far rim behind the near one.
    return {
      bore: new THREE.CylinderGeometry(FRONT_RADIUS, REAR_RADIUS, TUBE_LENGTH, 40, 1, true),
      wall: new THREE.CylinderGeometry(FRONT_RADIUS + RIM_WIDTH, REAR_RADIUS + RIM_WIDTH, TUBE_LENGTH, 40, 1, true),
      rim: new THREE.RingGeometry(REAR_RADIUS, REAR_RADIUS + RIM_WIDTH, 40, 1),
    };
  }, []);
  return (
    <>
      <mesh geometry={geometry.bore}>
        <meshStandardMaterial {...METAL} side={THREE.DoubleSide} />
      </mesh>
      <mesh geometry={geometry.wall}>
        <meshStandardMaterial {...METAL} side={THREE.DoubleSide} />
      </mesh>
      <mesh geometry={geometry.rim} position={[0, -TUBE_LENGTH / 2, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <meshStandardMaterial {...METAL} side={THREE.DoubleSide} />
      </mesh>
    </>
  );
}

/**
 * Holds the tube on the sight line while R is up and drops it under the eye when it is not. The flip
 * is a translate + scale, never a spin in place, so its rim cannot sweep across the reticle.
 */
export function ScopeSight({camera}: {camera: THREE.Camera}) {
  const group = useRef<THREE.Group>(null);
  const eye = useMemo(() => new THREE.Vector3(), []);
  const forward = useMemo(() => new THREE.Vector3(), []);
  useFrame((_, dt) => {
    const g = group.current;
    if (!g) return;
    // Up in 0.26 s, away in 0.1 s: a sight that lingers in front of the eye on its way out is just
    // something in the way.
    const target = lobScope.active || lobScope.optic > 0.03 ? 1 : 0;
    const travel = Math.min(1, dt / (target > lobScope.sight ? 0.26 : 0.1));
    const step = Math.sign(target - lobScope.sight) * Math.min(travel, Math.abs(target - lobScope.sight));
    lobScope.sight = Math.max(0, Math.min(1, lobScope.sight + step));
    g.visible = lobScope.sight > 0.05;
    if (!g.visible) return;
    const ease = lobScope.sight * lobScope.sight * (3 - 2 * lobScope.sight);
    const stow = 1 - ease;
    camera.getWorldPosition(eye);
    camera.getWorldDirection(forward);
    g.position.copy(eye).addScaledVector(forward, EYE_GAP);
    g.quaternion.copy(camera.quaternion);
    g.scale.setScalar(0.15 + 0.85 * ease);
    g.translateY(-0.22 * stow);
    g.translateX(0.04 * stow);
    // A cylinder's axis is its local +Y; -90 deg about X lays it down the line of sight. The stow tilt
    // folds into that same axis, so the tube simply stands up as it comes in.
    g.rotateX(-Math.PI / 2 - Math.PI * 0.45 * stow);
  });
  return (
    <group ref={group} visible={false}>
      <Tube />
    </group>
  );
}

/** Mounts the tube on the active camera; it stays stowed until the cockpit flips it up. */
export function SightRig() {
  const camera = useThree(s => s.camera);
  return <ScopeSight camera={camera} />;
}

const VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }
`;

// One pass over the rendered frame: inside the aperture the frame is resampled `uZoom` times larger,
// outside it passes straight through. The edge is a percent and a half wide and the whole effect fades
// with `uMix`, so the glass grows in and out with the tube instead of popping on.
const FRAGMENT = /* glsl */ `
  uniform sampler2D tDiffuse;
  uniform float uAspect;
  uniform float uRadius;
  uniform float uZoom;
  uniform float uMix;
  varying vec2 vUv;

  void main(){
    vec3 plain = texture2D(tDiffuse, vUv).rgb;
    vec2 p = (vUv - 0.5) * vec2(uAspect, 1.0);
    float r = length(p);
    float mask = 1.0 - smoothstep(uRadius * 0.985, uRadius, r);
    vec3 lens = texture2D(tDiffuse, 0.5 + (p / uZoom) / vec2(uAspect, 1.0)).rgb;
    gl_FragColor = vec4(mix(plain, lens, mask * uMix), 1.0);
  }
`;

type Pass = {target: THREE.WebGLRenderTarget; quad: THREE.Mesh; scene: THREE.Scene; camera: THREE.OrthographicCamera; size: [number, number]};

/**
 * Draws one frame. With the sight on the eye the scene goes into a render target and the lens pass
 * composites the magnified disc over the plain view; otherwise it is a normal render. No extra scene
 * pass and no reticle texture — the crosshair is DOM above the canvas.
 */
export function useSightRenderer() {
  const gl = useThree(s => s.gl);
  const pass = useRef<Pass | null>(null);
  const optics = useRef({mix: 0, at: 0});
  const build = () => {
    const target = new THREE.WebGLRenderTarget(1, 1, {depthBuffer: true, stencilBuffer: false});
    target.texture.minFilter = THREE.LinearFilter;
    target.texture.magFilter = THREE.LinearFilter;
    const material = new THREE.ShaderMaterial({
      uniforms: {
        tDiffuse: {value: target.texture},
        uAspect: {value: 1},
        uRadius: {value: 0.29},
        uZoom: {value: 2.5},
        uMix: {value: 0},
      },
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      depthTest: false,
      depthWrite: false,
      toneMapped: false,
    });
    const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
    quad.frustumCulled = false;
    const scene = new THREE.Scene();
    scene.add(quad);
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    pass.current = {target, quad, scene, camera, size: [0, 0]};
    return pass.current;
  };
  return (scene: THREE.Scene, camera: THREE.PerspectiveCamera, width: number, height: number, fov: number, enabled: boolean) => {
    // The tube has to be square on the eye before the glass can magnify, so the optics run their own
    // 0.18 s ramp once the flip has landed, and fold out before the tube leaves.
    const o = optics.current;
    const now = performance.now();
    const dt = Math.min(0.1, (now - (o.at || now)) / 1000);
    o.at = now;
    const want = enabled && lobScope.active && lobScope.sight > 0.96 ? 1 : 0;
    o.mix = Math.max(0, Math.min(1, o.mix + Math.sign(want - o.mix) * Math.min(dt / 0.18, Math.abs(want - o.mix))));
    lobScope.optic = o.mix;
    const mix = o.mix * o.mix * (3 - 2 * o.mix);
    if (mix <= 0.002) {
      gl.setRenderTarget(null);
      gl.render(scene, camera);
      return;
    }
    const p = pass.current ?? build();
    const pixelRatio = gl.getPixelRatio();
    const w = Math.max(2, Math.round(width * pixelRatio));
    const h = Math.max(2, Math.round(height * pixelRatio));
    if (p.size[0] !== w || p.size[1] !== h) {
      p.target.setSize(w, h);
      p.size = [w, h];
    }
    gl.setRenderTarget(p.target);
    gl.render(scene, camera);
    gl.setRenderTarget(null);
    const material = p.quad.material as THREE.ShaderMaterial;
    material.uniforms.uAspect.value = width / Math.max(1, height);
    material.uniforms.uRadius.value = apertureRadius(fov);
    material.uniforms.uZoom.value = 1 + (lobScope.zoom - 1) * mix;
    material.uniforms.uMix.value = mix;
    gl.render(p.scene, p.camera);
  };
}
