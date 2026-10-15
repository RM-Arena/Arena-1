use super::*;

#[derive(Clone, Serialize, Deserialize)]
pub struct PickupState {
    pub stage: String,
    pub elapsed: f64,
    pub phase_elapsed: f64,
    pub progress: f64,
    pub point: [f64; 3],
    pub direction: [f64; 3],
    pub held: bool,
    #[serde(default)]
    pub arm: u32,
}

impl Engine {
    pub(super) fn request_pickup(&mut self, i: usize, rpc: &Value) {
        let r = &self.robots[i];
        if r.role != "engineer" {
            return;
        }
        let arm=rpc["pickup_arm"].as_u64().unwrap_or(if r.arm_count==2 {r.carried_units as u64%2} else {0}) as u32;
        let requested = rpc["pick_unit"].as_bool() == Some(true)
            && arm<r.arm_count
            && !rpc[if arm==0 {"arm"}else{"arm2"}].is_object()
            && (arm==1 || rpc.get("rescue").is_none());
        let eligible = requested
            && r.alive
            && !r.weak
            && !r.red_card
            && r.unit_pickup.as_ref().map(|s|s.arm==arm).unwrap_or(true)
            && r.carried_units < 2
            && self.raw_zone(i, "resource", Some(&r.team));
        if !eligible {
            if self.robots[i].unit_pickup.take().is_some() {
                self.event("unit_pickup_cancelled", json!({"robot":self.robots[i].id}));
            }
            return;
        }
        if r.unit_pickup.is_some() {
            return;
        }
        // A card lineup may contain multiple engineers. The physical dispenser
        // presents one unit at a time, so only one arm can claim that unit.
        if self.robots.iter().enumerate().any(|(j, other)| {
            j != i && other.team == r.team && other.unit_pickup.is_some()
        }) {
            return;
        }
        let station = self.arena.field_geometry["fixtures"]
            .as_array()
            .and_then(|f| {
                f.iter()
                    .find(|f| f["kind"] == "resource" && f["team"].as_str() == Some(&r.team))
            });
        let Some(station) = station else {
            return;
        };
        let point = &station["pick_point"];
        let (Some(x), Some(y)) = (point[0].as_f64(), point[1].as_f64()) else {
            return;
        };
        self.robots[i].unit_pickup = Some(PickupState {
            stage: "approaching".into(),
            elapsed: 0.0,
            phase_elapsed: 0.0,
            progress: 0.0,
            point: [
                x,
                y,
                height_at(&self.arena, x, y) + point[2].as_f64().unwrap_or(0.6),
            ],
            direction: std::array::from_fn(|k| station["pick_dir"][k].as_f64().unwrap_or(0.0)),
            held: false,
            arm,
        });
        self.event("unit_pickup_started", json!({"robot":self.robots[i].id}));
    }

    pub(super) fn advance_pickups(&mut self) {
        for i in 0..self.robots.len() {
            let r = &self.robots[i];
            if r.unit_pickup.is_none() {
                continue;
            }
            if !r.alive || r.weak || r.red_card || !self.raw_zone(i, "resource", Some(&r.team)) {
                self.robots[i].unit_pickup = None;
                self.event("unit_pickup_cancelled", json!({"robot":self.robots[i].id}));
                continue;
            }
            let selected=r.unit_pickup.as_ref().unwrap().arm;
            let arm = self.physics.as_ref().unwrap().design(i)[if selected==0 {"arm"}else{"arm2"}].clone();
            let stowed = physics::arm_stowed(&arm);
            let r = &mut self.robots[i];
            let state = r.unit_pickup.as_mut().unwrap();
            state.elapsed += DT;
            let target = if state.stage == "lifting" {
                [state.point[0], state.point[1], state.point[2] + 0.18]
            } else {
                state.point
            };
            let tip=if selected==0 {r.arm_tip}else{r.arm2_tip};
            let joints=if selected==0 {r.arm_joints}else{r.arm2_joints};
            let error = tip
                .iter()
                .zip(target)
                .map(|(a, b)| (a - b).powi(2))
                .sum::<f64>()
                .sqrt();
            let ready = match state.stage.as_str() {
                "approaching" => error < 0.045 && joints[6] > 0.8,
                "gripping" => error < 0.045 && joints[6] < 0.2,
                "lifting" => error < 0.05,
                "stowing" => joints
                    .iter()
                    .zip(stowed)
                    .enumerate()
                    .all(|(k, (a, b))| (a - b).abs() < if k == 1 || k == 2 { 0.025 } else { 0.08 }),
                _ => false,
            };
            state.phase_elapsed = if ready { state.phase_elapsed + DT } else { 0.0 };
            let (index, duration, next) = match state.stage.as_str() {
                "approaching" => (0, 0.2, "gripping"),
                "gripping" => (1, 0.35, "lifting"),
                "lifting" => (2, 0.3, "stowing"),
                _ => (3, 0.4, "complete"),
            };
            state.progress = (index as f64 + (state.phase_elapsed / duration).min(1.0)) / 4.0;
            if state.phase_elapsed + 1e-8 < duration {
                continue;
            }
            if next == "complete" {
                r.carried_units += 1;
                r.unit_pickup = None;
                self.event("unit_pickup", json!({"robot":self.robots[i].id,"amount":1}));
            } else {
                state.stage = next.into();
                state.phase_elapsed = 0.0;
                if next == "lifting" {
                    state.held = true;
                }
            }
        }
    }
}
