// The lobbed-fire sight a 2027 heavy can flip up with R. The cockpit owns the toggle and the sight
// line while the camera lives in `ArenaScene`, so both are shared through this one object:
// `active` is the request to swing the sight up, `sight` is the swing itself (0 stowed, 1 on the
// eye) and `yaw`/`pitch` are the direction the reticle points — which is *not* the gun, because the
// launcher carries its own drop solution underneath the line of sight.
export const lobScope = {
  active: false,
  /** Swing of the mechanical sight: 0 folded down beside the gun, 1 in front of the eye. */
  sight: 0,
  /** The lens itself: 0 plain view, 1 fully magnified. It lags `active` so the glass clears before
   * the tube swings away, and the sight rig holds its position until it has. */
  optic: 0,
  /** Magnification inside the lens; the world outside keeps the plain first-person fov. */
  zoom: 2.5,
  yaw: 0,
  pitch: 0,
};

// The gimbal angle the pilot is commanding right now, published every rendered frame. The camera
// reads this instead of waiting for the engine's echo of it: the echo only arrives with the match
// snapshot (about 10 Hz), so a cockpit that read it stepped its view a few times per snapshot and
// sat still in between — which is what a jerky first-person turn actually was. The echo still has
// the last word (it is the gun's real angle), so the camera eases onto it whenever the two drift.
export const pilotAim = {
  /** True while a pilot is aboard; the camera only borrows this angle when it is. */
  live: false,
  yaw: 0,
  pitch: 0,
  /** How many times the cockpit advanced the aim (it runs once per animation frame), and the last
   *  step it took, so a stall can be told from a slow turn in the live diagnostics. */
  runs: 0,
  step: 0,
};
