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
