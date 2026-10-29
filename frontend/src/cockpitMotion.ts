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
// The rumble sits in the 3–9 Hz band a driver reads as "the machine is rolling"; anything faster than
// that stops reading as motion and starts reading as vibration, which is what a first-person pilot
// complains about. The impulses are the part a driver is meant to notice. Everything is capped at
// ±8 mm, ±0.0015 rad of roll and ±0.004 rad of pitch: enough to feel like a machine, small enough
// that the reticle does not wander while the pilot holds it still.
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
  // turns every kerb and suspension tick into a kick; 0.85 m/s is a dropped step or the end of a jump.
  if (alive && Math.abs(dvz) > .85) s.yv -= Math.min(.10, dvz * .012);
  const shot = r.last_shot_time ?? 0;
  if (shot !== s.lastShot) {
    s.lastShot = shot;
    if (alive) { s.pitchv += is42(r.role) ? .12 : .05; s.yv -= .0025; }
  }
  const hit = r.last_damage_time ?? 0;
  if (hit !== s.lastHit) {
    s.lastHit = hit;
    if (alive) { s.rollv += (r.slot % 2 ? 1 : -1) * .05; s.yv -= .004; }
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
  // 3.2 → 8.7 Hz: the rolling band. The old 6 → 22 Hz sweep lived where a lens reads vibration rather
  // than motion, which is why it survived every amplitude cut and still felt like a buzz.
  s.phase += dt * Math.PI * 2 * (3.2 + 5.5 * drive);
  // The motor and gear whine is a different tone from the tread passing under the wheels, so it keeps
  // its own high-frequency phase instead of riding the tread wave.
  s.buzz += dt * Math.PI * 2 * (38 + 10 * buzz);
  // The rumble is deliberately small, and it only runs while the chassis is actually rolling: a
  // machine holding position still draws current, and that current used to buzz the lens while the
  // robot stood still. The impulses are the part a driver is meant to notice.
  const rolling = drive * buzz, tread = drive * .0007 + rolling * .0002;
  shakeAt.y = Math.max(-.008, Math.min(.008, s.y)) + tread * (Math.sin(s.phase) + .45 * Math.sin(s.phase * 2.37 + 1.1));
  shakeAt.roll = Math.max(-.0015, Math.min(.0015, s.roll)) + drive * .0004 * Math.sin(s.phase * .55 + 2.2) + rolling * .0001 * Math.sin(s.buzz);
  shakeAt.pitch = Math.max(-.004, Math.min(.004, s.pitch)) + drive * .00025 * Math.sin(s.phase * 1.1);
  return shakeAt;
}

// The caps above are the contract other layers rely on: the camera applies these numbers directly.
export const SHAKE_LIMITS = {y: .008, roll: .0015, pitch: .004} as const;

// ---- Eye height ---------------------------------------------------------------------------------
// The lens sits at the hull's reported height, which arrives at 20 Hz and carries every suspension tick
// and every millimetre of terrain. Following it directly buzzes the picture; following it too slowly
// lets the eye sink into a ramp. The compromise is a critically damped spring — the same shape as the
// old single-pole low-pass, without its phase distortion at 2–5 Hz — with its restoring force gated
// below a sub-millimetre dead-band, which is what removes the last of the buzz.
//
// 20 rad/s is deliberately slower than the old 33 s⁻¹: the field's own road humps are 70 mm high every
// 240 mm, which at 2–4 m/s is 8–17 Hz of body bob, and only a filter this slow turns that into one soft
// heave. A spring that slow would trail a steady climb by 2V/ω, so the *slow* vertical velocity is fed
// forward to cancel exactly that; a ramp keeps its speed and a washboard keeps its filtering.
export type EyeLift = {y: number; v: number; ready: boolean};
export type EyeMount = {id: string; ride: EyeLift; vz: number};
export const createEyeLift = (): EyeLift => ({y: 0, v: 0, ready: false});
export const createEyeMount = (): EyeMount => ({id: '', ride: createEyeLift(), vz: 0});
const LIFT_W = 20, LIFT_DEADBAND = .0006, LIFT_RAMP_LEAD = 2 / LIFT_W, LIFT_SPEED_RATE = 3;

export function eyeLiftStep(s: EyeLift, target: number, dt: number): number {
  if (!s.ready) { s.y = target; s.v = 0; s.ready = true; return s.y; }
  // Sub-stepped at 240 Hz: 60, 120 and 240 Hz panels must ride identically, and a dropped frame must
  // not turn one step into an overshoot.
  const h = 1 / 240, steps = Math.max(1, Math.ceil(dt / h)), step = dt / steps;
  for (let k = 0; k < steps; k++) {
    const err = target - s.y;
    // Damping always applies, so the eye never coasts; only the spring force is dead-banded.
    if (Math.abs(err) > LIFT_DEADBAND) s.v += LIFT_W * LIFT_W * err * step;
    s.v -= 2 * LIFT_W * s.v * step;
    s.y += s.v * step;
  }
  return s.y;
}

// One machine's eye height for one frame. A new machine, or a jump the size of a teleport, re-seeds the
// ride instead of gliding across the field.
export function eyeMountStep(m: EyeMount, id: string, height: number, vz: number, dt: number): number {
  if (m.id !== id || Math.abs(height - m.ride.y) > .75) { m.id = id; m.ride.ready = false; m.vz = vz; }
  m.vz += (vz - m.vz) * (1 - Math.exp(-LIFT_SPEED_RATE * Math.max(0, dt)));
  return eyeLiftStep(m.ride, height + LIFT_RAMP_LEAD * m.vz, dt);
}

