import {is42, type Robot} from './types';

// A cockpit lens is bolted to a chassis that runs on wheels, so it carries the machine's own motion.
// Three sources, all read off the simulated body rather than from noise — which is the difference
// between "the robot is running" and "the picture is wobbling":
//  · tread rumble — two incommensurate harmonics whose frequency and amplitude follow the speed, so a
//    crawl hums and a dash buzzes;
//  · suspension jolts — a damped impulse when the vertical velocity changes abruptly (landing a
//    step, a jump, a collision), scaled by how hard the change was;
//  · gun and hits — a pitch kick on the shot (about twice as hard for the 42 mm) and a lateral
//    shoulder knock on damage.
// The rumble only runs under power and is a third of the old amplitude; the impulses are the part a
// driver is meant to notice. Everything is capped at ±1.2 cm and ±0.0075 rad: enough to feel like a
// machine, small enough that the reticle does not wander while the pilot holds it still.
export type ShakeState = {
  id: string; y: number; yv: number; roll: number; rollv: number; pitch: number; pitchv: number;
  phase: number; buzz: number; lastShot: number; lastHit: number; vz: number;
};
export type ShakeOffset = {y: number; roll: number; pitch: number};

export const createShakeState = (): ShakeState => ({
  id: '', y: 0, yv: 0, roll: 0, rollv: 0, pitch: 0, pitchv: 0,
  phase: 0, buzz: 0, lastShot: 0, lastHit: 0, vz: 0,
});

// Reused every frame: this runs on the render loop, so it must not hand the collector an object.
const shakeAt: ShakeOffset = {y: 0, roll: 0, pitch: 0};

// One spring per axis, just past critical (ω≈33 rad/s, ζ≈1.02): it settles in about 120 ms without a
// second swing, which is the difference between "the machine took a hit" and "the picture bounces".
const SPRING_K = 1100, SPRING_C = 68;

export function shakeOf(s: ShakeState, r: Robot, dt: number): ShakeOffset {
  if (s.id !== r.id) {
    s.id = r.id; s.y = s.yv = s.roll = s.rollv = s.pitch = s.pitchv = 0;
    s.phase = r.slot * 1.7; s.buzz = r.slot * 2.3;
    s.lastShot = r.last_shot_time ?? 0; s.lastHit = r.last_damage_time ?? 0; s.vz = r.vz ?? 0;
  }
  const alive = r.alive || r.role === 'aerial';
  const speed = alive ? Math.hypot(r.vx || 0, r.vy || 0) : 0;
  const dvz = (r.vz ?? 0) - s.vz;
  s.vz = r.vz ?? 0;
  // Only a real landing is a jolt. Vertical speed arrives with the 20 Hz snapshot, so a low threshold
  // turns every kerb and suspension tick into a kick; 0.55 m/s is a dropped step or the end of a jump.
  if (alive && Math.abs(dvz) > .55) s.yv -= Math.min(.22, dvz * .02);
  const shot = r.last_shot_time ?? 0;
  if (shot !== s.lastShot) {
    s.lastShot = shot;
    if (alive) { s.pitchv += is42(r.role) ? .22 : .1; s.yv -= .005; }
  }
  const hit = r.last_damage_time ?? 0;
  if (hit !== s.lastHit) {
    s.lastHit = hit;
    if (alive) { s.rollv += (r.slot % 2 ? 1 : -1) * .1; s.yv -= .01; }
  }
  // The integration runs in ≤1/120 s steps: an explicit spring evaluated at a dropped frame's 50 ms
  // would over-shoot its own damping term and ring, so a hitch must not change the feel.
  const h = Math.min(1 / 120, dt), steps = Math.max(1, Math.ceil(dt / h)), step = dt / steps;
  for (let k = 0; k < steps; k++) {
    s.yv += (-SPRING_K * s.y - SPRING_C * s.yv) * step; s.y += s.yv * step;
    s.rollv += (-SPRING_K * s.roll - SPRING_C * s.rollv) * step; s.roll += s.rollv * step;
    s.pitchv += (-SPRING_K * s.pitch - SPRING_C * s.pitchv) * step; s.pitch += s.pitchv * step;
  }
  const drive = alive && r.grounded !== false ? Math.min(1, speed / 3.2) : 0;
  const buzz = Math.min(1, Math.abs(r.motor_power_w ?? 0) / Math.max(1, r.power_limit ?? 100));
  s.phase += dt * Math.PI * 2 * (6 + 16 * drive);
  // The motor and gear whine is a different tone from the tread passing under the wheels, so it keeps
  // its own high-frequency phase instead of riding the tread wave.
  s.buzz += dt * Math.PI * 2 * (38 + 10 * buzz);
  // The rumble is deliberately small, and it only runs while the chassis is actually rolling: a
  // machine holding position still draws current, and that current used to buzz the lens while the
  // robot stood still. The impulses are the part a driver is meant to notice.
  const rolling = drive * buzz, tread = drive * .0011 + rolling * .0004;
  shakeAt.y = Math.max(-.012, Math.min(.012, s.y)) + tread * (Math.sin(s.phase) + .45 * Math.sin(s.phase * 2.37 + 1.1));
  shakeAt.roll = Math.max(-.003, Math.min(.003, s.roll)) + drive * .0009 * Math.sin(s.phase * .79 + 2.2) + rolling * .0002 * Math.sin(s.buzz);
  shakeAt.pitch = Math.max(-.0075, Math.min(.0075, s.pitch)) + drive * .0005 * Math.sin(s.phase * 1.61);
  return shakeAt;
}

// The caps above are the contract other layers rely on: the camera applies these numbers directly.
export const SHAKE_LIMITS = {y: .012, roll: .003, pitch: .0075} as const;
