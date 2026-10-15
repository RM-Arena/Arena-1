//! Shared finite armor geometry. Dimensions without a CAD source are public proxies.
use super::*;
use rapier3d::na::Vector3;

#[derive(Clone, Copy, Serialize)]
pub(crate) struct Plate {
    pub face: usize,
    pub center: [f64; 3],
    pub normal: [f64; 3],
    pub width: f64,
    pub height: f64,
    pub heavy_only: bool,
    pub weakspot: bool,
}

/// Figure 4-32: the outpost's three rotating middle armour modules are staggered,
/// 1116 / 1216 / 1316 mm above its base; face k keeps its own height as it turns.
pub(crate) const OUTPOST_MIDDLE_Z: [f64; 3] = [1.116, 1.216, 1.316];

pub(crate) fn plates(b: &Base, outpost: bool) -> Vec<Plate> {
    let mut result = Vec::new();
    // Figure 4-11: the large base modules are 287 mm above the pedestal once exposed.
    // Top (dart-detection) modules detect 42 mm even while the base's shells are closed.
    let levels: Vec<(Option<f64>, f64, f64, bool, bool, f64)> = if outpost {
        vec![
            (None, 0.2965, 0.17, false, true, 0.0),
            (Some(1.5), 0.095, 0.135, true, false, 0.0),
        ]
    } else {
        let mut levels = vec![(Some(1.043), 0.095, 0.135, true, false, 0.0)];
        if b.armor_open {
            levels.push((Some(0.287), 0.34, 0.23, false, true, 15.0_f64.to_radians()));
        }
        levels
    };
    for (level, (z, radius, width, heavy_only, weakspot, tilt)) in levels.into_iter().enumerate() {
        for face in 0..3 {
            let a = if outpost && level == 0 {
                b.rotation
            } else {
                0.0
            } + face as f64 * std::f64::consts::TAU / 3.0;
            let z = z.unwrap_or(OUTPOST_MIDDLE_Z[face]);
            result.push(Plate {
                face: if outpost && level == 0 {
                    face
                } else if outpost {
                    3 + face
                } else if level == 0 {
                    3 + face
                } else {
                    face
                },
                center: [b.x + radius * a.cos(), b.y + radius * a.sin(), b.z + z],
                normal: [a.cos() * tilt.cos(), a.sin() * tilt.cos(), tilt.sin()],
                width,
                height: 0.125,
                heavy_only,
                weakspot,
            });
        }
    }
    result
}

pub(crate) fn coordinates(plate: &Plate, point: [f64; 3]) -> (f64, f64, f64) {
    let n = Vector3::from(plate.normal);
    let u = Vector3::new(-n.y, n.x, 0.0).normalize();
    let v = n.cross(&u);
    let d = Vector3::from(point) - Vector3::from(plate.center);
    (d.dot(&u), d.dot(&v), d.dot(&n))
}

pub(crate) fn intersection(plate: &Plate, origin: [f64; 3], delta: [f64; 3]) -> Option<f64> {
    let n = Vector3::from(plate.normal);
    let d = Vector3::from(delta).dot(&n);
    if d >= -1e-10 {
        return None;
    }
    let t = (Vector3::from(plate.center) - Vector3::from(origin)).dot(&n) / d;
    if !(0.0..=1.0).contains(&t) {
        return None;
    }
    let point = std::array::from_fn(|k| origin[k] + t * delta[k]);
    let (u, v, _) = coordinates(plate, point);
    (u.abs() <= plate.width / 2.0 && v.abs() <= plate.height / 2.0).then_some(t)
}

/// Figures 4-10/4-11: closed, three corner shells form the pyramid and meet at a
/// narrow slit in the middle of each face. Opening swings each half-shell outward
/// about its corner, uncovering the face's large armour module. The swept boxes
/// stop shots; opening never changes the ground robot forbidden pedestal.
pub(crate) const BASE_SHELL_OPEN_RAD: f64 = 1.15;

pub(crate) fn covers(b: &Base) -> Vec<Wall> {
    cover_geometry(b.x, b.y, b.z, b.armor_open_progress)
}

pub(crate) fn cover_geometry(x: f64, y: f64, z: f64, progress: f64) -> Vec<Wall> {
    let (radius, reach, length) = (0.43, 0.265, 0.24);
    let mut walls = Vec::new();
    for face in 0..3 {
        let a = face as f64 * std::f64::consts::TAU / 3.0;
        let (n, t) = ([a.cos(), a.sin()], [-a.sin(), a.cos()]);
        for (k, side) in [-1.0_f64, 1.0].into_iter().enumerate() {
            // Hinge at the corner end; closed, the half-shell runs back toward the slit.
            let hinge = [x + radius * n[0] + side * reach * t[0], y + radius * n[1] + side * reach * t[1]];
            let theta = progress.clamp(0.0, 1.0) * BASE_SHELL_OPEN_RAD;
            let dir = [
                -side * t[0] * theta.cos() + n[0] * theta.sin(),
                -side * t[1] * theta.cos() + n[1] * theta.sin(),
            ];
            let center = [hinge[0] + dir[0] * length / 2.0, hinge[1] + dir[1] * length / 2.0];
            walls.push(Wall {
                x: center[0] - 0.03,
                y: center[1] - length / 2.0,
                w: 0.06,
                h: length,
                height: 0.78,
                bottom: z + 0.08,
                // Local +y runs along the half-shell.
                rotation: (-dir[0]).atan2(dir[1]),
                kind: "base_cover".into(),
                id: format!("base_cover_{face}_{k}"),
                source_page: 39,
            });
        }
    }
    walls
}
