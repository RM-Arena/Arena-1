use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub const DT: f64 = 0.05;
const ROLES: [&str; 7] = [
    "hero", "engineer", "infantry", "infantry", "infantry", "sentry", "scout",
];

#[derive(Clone, Serialize, Deserialize)]
pub struct Spec {
    pub hp: f64,
    pub speed: f64,
    pub damage: f64,
    pub cooldown: f64,
    pub ammo: u32,
    pub vision: f64,
    pub range: f64,
    pub acceleration: f64,
    pub armor: f64,
    pub heat_per_shot: f64,
    pub max_heat: f64,
    pub cooling: f64,
    pub projectile_speed: f64,
    pub asset: String,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Wall {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
    pub height: f64,
    pub kind: String,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Terrain {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
    pub kind: String,
    pub elevation: f64,
    pub speed_multiplier: f64,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub direction: i32,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub axis: String,
}
fn is_zero(value: &i32) -> bool {
    *value == 0
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Zone {
    pub id: String,
    pub x: f64,
    pub y: f64,
    pub radius: f64,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Arena {
    pub name: String,
    pub width: f64,
    pub height: f64,
    pub obstacles: Vec<Wall>,
    pub terrain: Vec<Terrain>,
    pub zones: Vec<Zone>,
    pub asset: String,
}
#[derive(Clone, Deserialize)]
pub struct Config {
    pub maps: BTreeMap<String, Arena>,
    pub specs: BTreeMap<String, Spec>,
}
pub fn config() -> Config {
    serde_json::from_str(include_str!("../../config/rules.json")).expect("valid embedded config")
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Robot {
    pub id: String,
    pub slot: u32,
    pub team: String,
    pub role: String,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub vx: f64,
    pub vy: f64,
    pub vz: f64,
    pub hp: f64,
    pub max_hp: f64,
    pub ammo: u32,
    pub aim: f64,
    pub pitch: f64,
    pub heading: f64,
    pub radius: f64,
    pub cooldown: f64,
    pub skill_cooldown: f64,
    pub shield: f64,
    pub energy: f64,
    pub heat: f64,
    pub overheated: bool,
    pub dash: f64,
    pub armor: f64,
    pub level: u32,
    pub kills: u32,
    pub damage: f64,
    pub alive: bool,
    pub upgrades: BTreeMap<String, u32>,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Base {
    pub x: f64,
    pub y: f64,
    pub hp: f64,
    pub max_hp: f64,
    pub radius: f64,
}
#[derive(Clone, Serialize, Deserialize, Default)]
pub struct Team {
    pub score: f64,
    pub resources: f64,
    pub kills: u32,
    pub captured_seconds: f64,
}
#[derive(Clone, Serialize, Deserialize, Default)]
pub struct ZoneState {
    pub owner: Option<String>,
    pub progress: f64,
    pub contested: bool,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Projectile {
    pub id: u64,
    pub source: String,
    pub team: String,
    pub role: String,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub vx: f64,
    pub vy: f64,
    pub vz: f64,
    pub remaining: f64,
    pub damage: f64,
    pub radius: f64,
}
#[derive(Clone, Default)]
struct Action {
    mv: [f64; 2],
    aim: Option<f64>,
    pitch: f64,
    fire: bool,
    skill: bool,
    upgrade: Option<String>,
}

pub struct Engine {
    pub seed: i64,
    pub duration: f64,
    pub tick: u64,
    pub status: String,
    pub winner: Option<String>,
    pub reason: Option<String>,
    pub arena: Arena,
    pub robots: Vec<Robot>,
    pub bases: BTreeMap<String, Base>,
    pub teams: BTreeMap<String, Team>,
    pub zones: BTreeMap<String, ZoneState>,
    pub projectiles: Vec<Projectile>,
    pub events: Vec<Value>,
    specs: BTreeMap<String, Spec>,
    rng: u64,
    next_projectile: u64,
}
fn dist(x: f64, y: f64, a: f64, b: f64) -> f64 {
    (x - a).hypot(y - b)
}
fn approach(a: f64, b: f64, delta: f64) -> f64 {
    a + (b - a).clamp(-delta, delta)
}
fn turn(a: f64, b: f64, delta: f64) -> f64 {
    let difference =
        (b - a + std::f64::consts::PI).rem_euclid(std::f64::consts::TAU) - std::f64::consts::PI;
    (a + difference.clamp(-delta, delta)).rem_euclid(std::f64::consts::TAU)
}
fn contains(x: f64, y: f64, t: &Terrain) -> bool {
    x >= t.x && x <= t.x + t.w && y >= t.y && y <= t.y + t.h
}
pub fn height_at(arena: &Arena, x: f64, y: f64) -> f64 {
    arena
        .terrain
        .iter()
        .filter(|t| contains(x, y, t))
        .map(|t| {
            if t.kind == "ramp" {
                let p = if t.axis == "x" {
                    (x - t.x) / t.w
                } else {
                    (y - t.y) / t.h
                };
                t.elevation * if t.direction < 0 { 1.0 - p } else { p }
            } else {
                t.elevation
            }
        })
        .fold(0.0, f64::max)
}
pub fn segment_box(x: f64, y: f64, dx: f64, dy: f64, w: &Wall) -> Option<f64> {
    let (mut lo, mut hi): (f64, f64) = (0.0, 1.0);
    for (p, d, a, b) in [(x, dx, w.x, w.x + w.w), (y, dy, w.y, w.y + w.h)] {
        if d.abs() < 1e-12 {
            if p < a || p > b {
                return None;
            }
        } else {
            let (aa, bb) = ((a - p) / d, (b - p) / d);
            lo = lo.max(aa.min(bb));
            hi = hi.min(aa.max(bb));
        }
        if lo > hi {
            return None;
        }
    }
    Some(lo)
}
pub fn segment_circle(x: f64, y: f64, dx: f64, dy: f64, cx: f64, cy: f64, r: f64) -> Option<f64> {
    let (ox, oy) = (x - cx, y - cy);
    let c = ox * ox + oy * oy - r * r;
    if c <= 0.0 {
        return Some(0.0);
    }
    let a = dx * dx + dy * dy;
    let b = 2.0 * (ox * dx + oy * dy);
    let discriminant = b * b - 4.0 * a * c;
    if a < 1e-12 || discriminant < 0.0 {
        return None;
    }
    let t = (-b - discriminant.sqrt()) / (2.0 * a);
    if (0.0..=1.0).contains(&t) {
        Some(t)
    } else {
        None
    }
}
fn slab(p: f64, d: f64, a: f64, b: f64) -> Option<(f64, f64)> {
    if d.abs() < 1e-12 {
        if p >= a && p <= b {
            Some((0.0, 1.0))
        } else {
            None
        }
    } else {
        let (a, b) = ((a - p) / d, (b - p) / d);
        Some((a.min(b).max(0.0), a.max(b).min(1.0)))
    }
}
fn segment_box_3d(p: &Projectile, dx: f64, dy: f64, dz: f64, w: &Wall) -> Option<f64> {
    let (mut lo, mut hi): (f64, f64) = (0.0, 1.0);
    for (pos, d, a, b) in [
        (p.x, dx, w.x, w.x + w.w),
        (p.y, dy, w.y, w.y + w.h),
        (p.z, dz, -p.radius, w.height + p.radius),
    ] {
        let (a, b) = slab(pos, d, a, b)?;
        lo = lo.max(a);
        hi = hi.min(b);
        if lo > hi {
            return None;
        }
    }
    Some(lo)
}
fn segment_cylinder(
    p: &Projectile,
    dx: f64,
    dy: f64,
    dz: f64,
    cx: f64,
    cy: f64,
    radius: f64,
    bottom: f64,
    top: f64,
) -> Option<f64> {
    let (ox, oy) = (p.x - cx, p.y - cy);
    let a = dx * dx + dy * dy;
    let b = 2.0 * (ox * dx + oy * dy);
    let c = ox * ox + oy * oy - radius * radius;
    let (enter, exit) = if a < 1e-12 {
        if c > 0.0 {
            return None;
        }
        (0.0, 1.0)
    } else {
        let determinant = b * b - 4.0 * a * c;
        if determinant < 0.0 {
            return None;
        }
        let root = determinant.sqrt();
        (
            ((-b - root) / (2.0 * a)).max(0.0),
            ((-b + root) / (2.0 * a)).min(1.0),
        )
    };
    let (lo, hi) = slab(p.z, dz, bottom - p.radius, top + p.radius)?;
    let lo = lo.max(enter);
    let hi = hi.min(exit);
    if lo <= hi {
        Some(lo)
    } else {
        None
    }
}

impl Engine {
    pub fn new(seed: i64, duration: f64, map: &str) -> Result<Self, String> {
        if !duration.is_finite() || !(1.0..=600.0).contains(&duration) {
            return Err("duration must be in [1,600]".into());
        }
        let conf = config();
        let arena = conf.maps.get(map).ok_or("Unknown map")?.clone();
        let mut robots = Vec::new();
        for team in ["red", "blue"] {
            for (i, role) in ROLES.iter().enumerate() {
                let s = &conf.specs[*role];
                let x = if team == "red" { 3.5 } else { 36.5 };
                let y = if team == "red" {
                    3.0 + i as f64 * 3.0
                } else {
                    21.0 - i as f64 * 3.0
                };
                robots.push(Robot {
                    id: format!("{team}-{}", i + 1),
                    slot: (i + 1) as u32,
                    team: team.into(),
                    role: (*role).into(),
                    x,
                    y,
                    z: height_at(&arena, x, y),
                    vx: 0.0,
                    vy: 0.0,
                    vz: 0.0,
                    hp: s.hp,
                    max_hp: s.hp,
                    ammo: s.ammo,
                    aim: if team == "red" {
                        0.0
                    } else {
                        std::f64::consts::PI
                    },
                    pitch: 0.04,
                    heading: if team == "red" {
                        0.0
                    } else {
                        std::f64::consts::PI
                    },
                    radius: 0.48,
                    cooldown: 0.0,
                    skill_cooldown: 0.0,
                    shield: 0.0,
                    energy: 100.0,
                    heat: 0.0,
                    overheated: false,
                    dash: 0.0,
                    armor: s.armor,
                    level: 1,
                    kills: 0,
                    damage: 0.0,
                    alive: true,
                    upgrades: BTreeMap::new(),
                });
            }
        }
        let bases = [
            (
                "red".into(),
                Base {
                    x: 1.6,
                    y: 12.0,
                    hp: 1800.0,
                    max_hp: 1800.0,
                    radius: 1.25,
                },
            ),
            (
                "blue".into(),
                Base {
                    x: 38.4,
                    y: 12.0,
                    hp: 1800.0,
                    max_hp: 1800.0,
                    radius: 1.25,
                },
            ),
        ]
        .into();
        let zones = arena
            .zones
            .iter()
            .map(|z| (z.id.clone(), ZoneState::default()))
            .collect();
        Ok(Self {
            seed,
            duration,
            tick: 0,
            status: "ready".into(),
            winner: None,
            reason: None,
            arena,
            robots,
            bases,
            teams: [
                ("red".into(), Team::default()),
                ("blue".into(), Team::default()),
            ]
            .into(),
            zones,
            projectiles: Vec::new(),
            events: Vec::new(),
            specs: conf.specs,
            rng: seed as u64 ^ 0x9e3779b97f4a7c15,
            next_projectile: 1,
        })
    }
    pub fn time(&self) -> f64 {
        ((self.tick as f64 * DT) * 1e6).round() / 1e6
    }
    pub fn snapshot(&self) -> Value {
        json!({"api_version":2,"engine":"rust","rules":"rmuc-arena-v2","tick":self.tick,
        "rules_hash":format!("{:x}",Sha256::digest(include_bytes!("../../config/rules.json"))),
        "engine_hash":format!("{:x}",Sha256::digest(include_bytes!("lib.rs"))),
        "time":self.time(),"dt":DT,"remaining":(self.duration-self.time()).max(0.0),"duration":self.duration,"seed":self.seed,
        "status":self.status,"winner":self.winner,"reason":self.reason,"arena":self.arena,"robots":self.robots,
        "bases":self.bases,"teams":self.teams,"zones":self.zones,"projectiles":self.projectiles,"events":self.events})
    }
    pub fn digest(&self) -> String {
        format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&self.snapshot()).unwrap())
        )
    }
    fn random(&mut self) -> f64 {
        self.rng = self.rng.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.rng;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        ((z ^ (z >> 31)) >> 11) as f64 / (1u64 << 53) as f64
    }
    fn event(&mut self, kind: &str, mut data: Value) {
        data["type"] = json!(kind);
        data["tick"] = json!(self.tick);
        data["time"] = json!(self.time());
        data["id"] = json!(format!("{}:{}", self.tick, self.events.len()));
        self.events.push(data);
    }
    fn visible(&self, a: &Robot, b: &Robot) -> bool {
        if dist(a.x, a.y, b.x, b.y) > self.specs[&a.role].vision {
            return false;
        }
        self.arena.obstacles.iter().all(|w| {
            segment_box(a.x, a.y, b.x - a.x, b.y - a.y, w)
                .map(|t| a.z + 1.05 + (b.z + 0.65 - a.z - 1.05) * t > w.height)
                .unwrap_or(true)
        })
    }
    pub fn observation(&self, team: &str, slots: Option<&[u32]>) -> Value {
        let friends: Vec<&Robot> = self.robots.iter().filter(|r| r.team == team).collect();
        let observers: Vec<&Robot> = friends
            .iter()
            .copied()
            .filter(|r| r.alive && slots.map(|s| s.contains(&r.slot)).unwrap_or(true))
            .collect();
        let enemies: Vec<Value> = self
            .robots
            .iter()
            .filter(|r| r.team != team && r.alive && observers.iter().any(|a| self.visible(a, r)))
            .map(|r| {
                json!({"id":r.id,"slot":r.slot,"team":r.team,"role":r.role,"x":r.x,"y":r.y,"z":r.z,
                "vx":r.vx,"vy":r.vy,"hp":r.hp,"max_hp":r.max_hp,"alive":r.alive,"radius":r.radius})
            })
            .collect();
        let bullets: Vec<&Projectile> = self
            .projectiles
            .iter()
            .filter(|p| {
                p.team == team
                    || observers.iter().any(|a| {
                        dist(a.x, a.y, p.x, p.y) < self.specs[&a.role].vision
                            && self.arena.obstacles.iter().all(|w| {
                                segment_box(a.x, a.y, p.x - a.x, p.y - a.y, w)
                                    .map(|t| a.z + 1.05 + (p.z - a.z - 1.05) * t > w.height)
                                    .unwrap_or(true)
                            })
                    })
            })
            .collect();
        json!({"api_version":2,"seed":self.seed,"tick":self.tick,"time":self.time(),"dt":DT,"policy_dt":0.1,
            "remaining":(self.duration-self.time()).max(0.0),"team":team,
            "controlled_ids":friends.iter().filter(|r|slots.map(|s|s.contains(&r.slot)).unwrap_or(true)).map(|r|r.slot.to_string()).collect::<Vec<_>>(),
            "robots":friends,"enemies":enemies,"arena":self.arena,"bases":self.bases,"teams":self.teams,"zones":self.zones,
            "projectiles":bullets,"specs":self.specs})
    }
    fn blocked(&self, x: f64, y: f64, radius: f64) -> bool {
        if x < radius
            || x > self.arena.width - radius
            || y < radius
            || y > self.arena.height - radius
        {
            return true;
        }
        self.arena
            .obstacles
            .iter()
            .any(|w| dist(x, y, x.clamp(w.x, w.x + w.w), y.clamp(w.y, w.y + w.h)) < radius - 1e-9)
            || self
                .bases
                .values()
                .any(|b| dist(x, y, b.x, b.y) < radius + b.radius)
    }
    fn normalize(&mut self, raw: &Value, i: usize) -> Action {
        let id = self.robots[i].id.clone();
        let mut a = Action {
            pitch: 0.04,
            ..Default::default()
        };
        if !raw.is_object() {
            self.event(
                "invalid_action",
                json!({"robot":id,"reason":"action must be an object"}),
            );
            return a;
        }
        if let Some(mv) = raw.get("move") {
            if let Some(v) = mv.as_array().filter(|v| v.len() == 2) {
                if let (Some(x), Some(y)) = (
                    v[0].as_f64().filter(|v| v.is_finite()),
                    v[1].as_f64().filter(|v| v.is_finite()),
                ) {
                    let (x, y) = (x.clamp(-1.0, 1.0), y.clamp(-1.0, 1.0));
                    let n = x.hypot(y).max(1.0);
                    a.mv = [x / n, y / n];
                } else {
                    self.event(
                        "invalid_action",
                        json!({"robot":id,"reason":"move must contain finite numbers"}),
                    );
                }
            } else {
                self.event(
                    "invalid_action",
                    json!({"robot":id,"reason":"move must contain two numbers"}),
                );
            }
        }
        for name in ["aim", "pitch"] {
            if let Some(v) = raw.get(name).filter(|v| !v.is_null()) {
                if let Some(n) = v.as_f64().filter(|v| v.is_finite()) {
                    if name == "aim" {
                        a.aim = Some(n.rem_euclid(std::f64::consts::TAU));
                    } else {
                        a.pitch = n.clamp(-0.3, 0.5);
                    }
                } else {
                    self.event(
                        "invalid_action",
                        json!({"robot":id,"reason":format!("{name} must be finite")}),
                    );
                }
            }
        }
        for name in ["fire", "skill"] {
            if let Some(v) = raw.get(name) {
                if let Some(b) = v.as_bool() {
                    if name == "fire" {
                        a.fire = b;
                    } else {
                        a.skill = b;
                    }
                } else {
                    self.event(
                        "invalid_action",
                        json!({"robot":id,"reason":format!("{name} must be boolean")}),
                    );
                }
            }
        }
        a.upgrade = raw
            .get("upgrade")
            .and_then(Value::as_str)
            .filter(|s| ["damage", "armor", "mobility"].contains(s))
            .map(str::to_owned);
        a
    }
    pub fn finish(&mut self, winner: Option<String>, reason: &str) {
        self.status = "finished".into();
        self.winner = winner;
        self.reason = Some(reason.into());
        self.event("finish", json!({"winner":self.winner,"reason":reason}));
    }
    fn damage_robot(&mut self, index: usize, amount: f64, source: usize) {
        if !self.robots[index].alive {
            return;
        }
        let armor = self.robots[index].armor;
        let shield = if self.robots[index].shield > 0.0 {
            0.4
        } else {
            1.0
        };
        let actual = (amount * (1.0 - armor) * shield).min(self.robots[index].hp);
        self.robots[index].hp = (self.robots[index].hp - actual).max(0.0);
        self.robots[source].damage += actual;
        let team = self.robots[source].team.clone();
        self.teams.get_mut(&team).unwrap().score += actual * 0.05;
        let r = &self.robots[index];
        self.event(
            "hit",
            json!({"robot":r.id,"x":r.x,"y":r.y,"z":r.z+0.6,"team":team,"damage":actual}),
        );
        if self.robots[index].hp <= 0.0 {
            self.robots[index].alive = false;
            self.robots[index].vx = 0.0;
            self.robots[index].vy = 0.0;
            self.robots[source].kills += 1;
            let t = self.teams.get_mut(&team).unwrap();
            t.kills += 1;
            t.score += 100.0;
            t.resources += 25.0;
            let r = &self.robots[index];
            self.event("destroy",json!({"robot":r.id,"killer":self.robots[source].id,"x":r.x,"y":r.y,"z":r.z+0.5,"team":team}));
        }
    }
    pub fn step(&mut self, commands: &Value) -> Value {
        if self.status == "finished" {
            return self.snapshot();
        }
        self.status = "running".into();
        self.events.clear();
        let mut actions = Vec::new();
        for i in 0..self.robots.len() {
            let r = &self.robots[i];
            let raw = commands
                .get(&r.team)
                .and_then(|c| c.get(r.slot.to_string()));
            actions.push(self.normalize(raw.unwrap_or(&json!({})), i));
        }
        for team in ["red", "blue"] {
            if let Some(obj) = commands.get(team).and_then(Value::as_object) {
                for key in obj.keys() {
                    if !["1", "2", "3", "4", "5", "6", "7"].contains(&key.as_str()) {
                        self.event(
                            "invalid_action",
                            json!({"team":team,"reason":"uncontrolled slot"}),
                        );
                    }
                }
            }
        }
        let old: Vec<(f64, f64)> = self.robots.iter().map(|r| (r.x, r.y)).collect();
        for i in 0..self.robots.len() {
            if !self.robots[i].alive {
                continue;
            }
            let spec = self.specs[&self.robots[i].role].clone();
            let mut r = self.robots[i].clone();
            let a = &actions[i];
            r.cooldown = (r.cooldown - DT).max(0.0);
            r.skill_cooldown = (r.skill_cooldown - DT).max(0.0);
            r.shield = (r.shield - DT).max(0.0);
            r.dash = (r.dash - DT).max(0.0);
            r.energy = (r.energy + 6.0 * DT).min(100.0);
            r.heat = (r.heat - spec.cooling * DT).max(0.0);
            if r.overheated && r.heat < 40.0 {
                r.overheated = false;
            }
            if let Some(aim) = a.aim {
                r.aim = turn(r.aim, aim, 6.0 * DT);
            }
            r.pitch = approach(r.pitch, a.pitch, 1.5 * DT);
            let terrain_speed = self
                .arena
                .terrain
                .iter()
                .filter(|t| contains(r.x, r.y, t))
                .map(|t| t.speed_multiplier)
                .fold(1.0, f64::min);
            let speed = spec.speed
                * (1.0 + 0.08 * (*r.upgrades.get("mobility").unwrap_or(&0) as f64))
                * terrain_speed
                * if r.dash > 0.0 { 2.0 } else { 1.0 };
            let desired = [a.mv[0] * speed, a.mv[1] * speed];
            let (dvx, dvy) = (desired[0] - r.vx, desired[1] - r.vy);
            let n = dvx.hypot(dvy);
            let ratio = if n > 0.0 {
                (spec.acceleration * DT / n).min(1.0)
            } else {
                0.0
            };
            r.vx += dvx * ratio;
            r.vy += dvy * ratio;
            if r.vx.hypot(r.vy) > 0.05 {
                r.heading = turn(r.heading, r.vy.atan2(r.vx), 3.5 * DT);
            }
            let (dx, dy) = (r.vx * DT, r.vy * DT);
            let steps = (dx.hypot(dy) / (r.radius * 0.45)).ceil().max(1.0) as u32;
            for _ in 0..steps {
                let nx = r.x + dx / steps as f64;
                let ny = r.y + dy / steps as f64;
                if !self.blocked(nx, r.y, r.radius) && height_at(&self.arena, nx, r.y) - r.z < 0.25
                {
                    r.x = nx;
                } else {
                    r.vx = 0.0;
                }
                if !self.blocked(r.x, ny, r.radius) && height_at(&self.arena, r.x, ny) - r.z < 0.25
                {
                    r.y = ny;
                } else {
                    r.vy = 0.0;
                }
            }
            let ground = height_at(&self.arena, r.x, r.y);
            if ground >= r.z - 0.04 {
                r.z = ground;
                r.vz = 0.0;
            } else {
                r.vz -= 9.81 * DT;
                r.z = (r.z + r.vz * DT).max(ground);
                if r.z <= ground {
                    r.vz = 0.0;
                }
            }
            self.robots[i] = r;
        }
        let mut collision_events = Vec::new();
        for pass in 0..10 {
            let mut collided = false;
            for i in 0..self.robots.len() {
                for j in i + 1..self.robots.len() {
                    let (a, b) = (&self.robots[i], &self.robots[j]);
                    if !a.alive || !b.alive || (a.z - b.z).abs() > 0.9 {
                        continue;
                    }
                    let (dx, dy) = (b.x - a.x, b.y - a.y);
                    let d = dx.hypot(dy);
                    let needed = a.radius + b.radius;
                    if d < needed - 1e-7 {
                        collided = true;
                        let (ux, uy) = if d > 1e-8 {
                            (dx / d, dy / d)
                        } else {
                            (0.0, 1.0)
                        };
                        let push = (needed - d + 1e-6) / 2.0;
                        if pass == 0 && (a.vx - b.vx).hypot(a.vy - b.vy) > 2.0 && self.tick % 8 == 0
                        {
                            collision_events
                                .push(json!({"x":(a.x+b.x)/2.0,"y":(a.y+b.y)/2.0,"z":a.z+0.3}));
                        }
                        for (k, sign) in [(i, -1.0), (j, 1.0)] {
                            let r = &self.robots[k];
                            let (x, y) = (r.x + ux * push * sign, r.y + uy * push * sign);
                            if !self.blocked(x, y, r.radius)
                                && height_at(&self.arena, x, y) - r.z < 0.25
                            {
                                self.robots[k].x = x;
                                self.robots[k].y = y;
                            }
                        }
                    }
                }
            }
            if !collided {
                break;
            }
        }
        let mut conflict = vec![false; self.robots.len()];
        for _ in 0..self.robots.len() {
            let before = conflict.iter().filter(|v| **v).count();
            for i in 0..self.robots.len() {
                for j in i + 1..self.robots.len() {
                    let (a, b) = (&self.robots[i], &self.robots[j]);
                    if a.alive
                        && b.alive
                        && (a.z - b.z).abs() < 0.9
                        && dist(a.x, a.y, b.x, b.y) < a.radius + b.radius - 1e-5
                    {
                        conflict[i] = true;
                        conflict[j] = true;
                    }
                }
            }
            for (i, v) in conflict.iter().enumerate() {
                if *v {
                    self.robots[i].x = old[i].0;
                    self.robots[i].y = old[i].1;
                    self.robots[i].vx = 0.0;
                    self.robots[i].vy = 0.0;
                }
            }
            if conflict.iter().filter(|v| **v).count() == before {
                break;
            }
        }
        for data in collision_events {
            self.event("collision", data);
        }
        for i in 0..self.robots.len() {
            if !self.robots[i].alive {
                continue;
            }
            let a = &actions[i];
            let spec = self.specs[&self.robots[i].role].clone();
            if a.skill && self.robots[i].skill_cooldown <= 1e-8 && self.robots[i].energy >= 50.0 {
                self.robots[i].energy -= 50.0;
                self.robots[i].skill_cooldown = 15.0;
                let r = self.robots[i].clone();
                if r.role == "engineer" {
                    for friend in &mut self.robots {
                        if friend.alive
                            && friend.team == r.team
                            && dist(r.x, r.y, friend.x, friend.y) <= 3.5
                        {
                            friend.hp = (friend.hp + 45.0).min(friend.max_hp);
                            friend.ammo = (friend.ammo + 12).min(self.specs[&friend.role].ammo);
                        }
                    }
                } else {
                    self.robots[i].shield = 2.5;
                    if r.role == "scout" {
                        self.robots[i].dash = 0.7;
                    }
                }
                self.event(
                    "skill",
                    json!({"robot":r.id,"team":r.team,"role":r.role,"x":r.x,"y":r.y,"z":r.z}),
                );
            }
            let r = &mut self.robots[i];
            let base = &self.bases[&r.team];
            if dist(r.x, r.y, base.x, base.y) < 4.0 {
                r.hp = (r.hp + 8.0 * DT).min(r.max_hp);
                if self.tick % 20 == 0 {
                    r.ammo = (r.ammo + 5).min(spec.ammo);
                }
            }
            let upgrade = a.upgrade.as_deref().unwrap_or("damage");
            let level = *r.upgrades.get(upgrade).unwrap_or(&0);
            if self.teams[&r.team].resources >= 60.0 && level < 2 {
                self.teams.get_mut(&r.team).unwrap().resources -= 60.0;
                r.upgrades.insert(upgrade.into(), level + 1);
                r.level += 1;
                if upgrade == "armor" {
                    r.armor = (r.armor + 0.08).min(0.45);
                }
                self.event(
                    "upgrade",
                    json!({"robot":self.robots[i].id,"team":self.robots[i].team,"branch":upgrade}),
                );
            }
            let r = self.robots[i].clone();
            if a.fire && r.cooldown <= 1e-8 && r.ammo > 0 && !r.overheated {
                self.robots[i].ammo -= 1;
                self.robots[i].cooldown = spec.cooldown;
                self.robots[i].heat += spec.heat_per_shot;
                if self.robots[i].heat >= spec.max_heat {
                    self.robots[i].overheated = true;
                    self.event("overheat", json!({"robot":r.id,"team":r.team}));
                }
                let angle = r.aim + (self.random() - 0.5) * 0.026;
                let pitch = r.pitch;
                let v = spec.projectile_speed;
                let buff = self.arena.zones.iter().any(|z| {
                    self.zones[&z.id].owner.as_deref() == Some(&r.team)
                        && dist(r.x, r.y, z.x, z.y) <= z.radius
                });
                let damage = spec.damage
                    * (1.0 + 0.15 * (*r.upgrades.get("damage").unwrap_or(&0) as f64))
                    * if buff { 1.1 } else { 1.0 };
                self.projectiles.push(Projectile {
                    id: self.next_projectile,
                    source: r.id.clone(),
                    team: r.team.clone(),
                    role: r.role.clone(),
                    x: r.x + angle.cos() * 0.72,
                    y: r.y + angle.sin() * 0.72,
                    z: r.z + 0.78,
                    vx: angle.cos() * pitch.cos() * v,
                    vy: angle.sin() * pitch.cos() * v,
                    vz: pitch.sin() * v,
                    remaining: spec.range,
                    damage,
                    radius: if r.role == "hero" { 0.1 } else { 0.045 },
                });
                self.next_projectile += 1;
                self.event("shot",json!({"robot":r.id,"team":r.team,"role":r.role,"x":r.x,"y":r.y,"z":r.z+0.78,"angle":angle,"pitch":pitch}));
            }
        }
        self.fly_projectiles();
        self.update_zones();
        self.tick += 1;
        let destroyed: Vec<&str> = ["red", "blue"]
            .into_iter()
            .filter(|t| self.bases[*t].hp <= 0.0)
            .collect();
        let eliminated: Vec<&str> = ["red", "blue"]
            .into_iter()
            .filter(|t| !self.robots.iter().any(|r| r.alive && r.team == *t))
            .collect();
        let (losers, reason) = if !destroyed.is_empty() {
            (destroyed, "base_destroyed")
        } else {
            (eliminated, "elimination")
        };
        if !losers.is_empty() {
            let winner = if losers.len() == 2 {
                None
            } else {
                Some(if losers[0] == "red" { "blue" } else { "red" }.into())
            };
            self.finish(winner, reason);
        } else if self.time() >= self.duration {
            let metric = |team: &str| {
                (
                    (self.teams[team].score * 1e6).round() as i64,
                    self.bases[team].hp,
                    self.robots
                        .iter()
                        .filter(|r| r.team == team)
                        .map(|r| r.hp)
                        .sum::<f64>(),
                )
            };
            let winner = match metric("red").partial_cmp(&metric("blue")).unwrap() {
                std::cmp::Ordering::Greater => Some("red".into()),
                std::cmp::Ordering::Less => Some("blue".into()),
                _ => None,
            };
            self.finish(winner, "timeout");
        }
        self.snapshot()
    }
    fn fly_projectiles(&mut self) {
        let projectiles = std::mem::take(&mut self.projectiles);
        let mut remaining = Vec::new();
        for mut p in projectiles {
            let Some(source) = self.robots.iter().position(|r| r.id == p.source) else {
                continue;
            };
            let speed = p.vx.hypot(p.vy);
            let length = (speed * DT).min(p.remaining);
            let ratio = if speed > 0.0 { length / speed } else { DT };
            let (dx, dy, dz) = (
                p.vx * ratio,
                p.vy * ratio,
                p.vz * ratio - 4.905 * ratio * ratio,
            );
            let mut hits: Vec<(f64, u8, usize)> = Vec::new();
            for w in &self.arena.obstacles {
                if let Some(t) = segment_box_3d(&p, dx, dy, dz, w) {
                    hits.push((t, 0, 0));
                }
            }
            // Swept horizontal intersections plus vertical extent for robot armor.
            for (i, r) in self.robots.iter().enumerate() {
                if r.alive && r.team != p.team {
                    if let Some(t) = segment_cylinder(
                        &p,
                        dx,
                        dy,
                        dz,
                        r.x,
                        r.y,
                        r.radius + p.radius,
                        r.z - 0.08,
                        r.z + 1.05,
                    ) {
                        hits.push((t, 1, i));
                    }
                }
            }
            let enemy = if p.team == "red" { "blue" } else { "red" };
            let b = &self.bases[enemy];
            if b.hp > 0.0 {
                if let Some(t) = segment_cylinder(&p, dx, dy, dz, b.x, b.y, b.radius, 0.0, 3.2) {
                    hits.push((t, 2, 0));
                }
            }
            // Sample terrain along the swept segment; substep spacing is <= 0.2m.
            let n = (length / 0.2).ceil().max(1.0) as u32;
            for i in 1..=n {
                let t = i as f64 / n as f64;
                if p.z + dz * t <= height_at(&self.arena, p.x + dx * t, p.y + dy * t) {
                    hits.push((t, 0, 0));
                    break;
                }
            }
            hits.sort_by(|a, b| a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)).then(a.2.cmp(&b.2)));
            if let Some(&(t, kind, index)) = hits.first() {
                let (x, y, z) = (p.x + dx * t, p.y + dy * t, (p.z + dz * t).max(0.03));
                if kind == 1 {
                    self.damage_robot(index, p.damage, source);
                } else if kind == 2 {
                    let base = self.bases.get_mut(enemy).unwrap();
                    let actual = p.damage.min(base.hp);
                    base.hp = (base.hp - actual).max(0.0);
                    self.robots[source].damage += actual;
                    self.teams.get_mut(&p.team).unwrap().score += actual * 0.05;
                    self.event(
                        "base_hit",
                        json!({"team":p.team,"x":x,"y":y,"z":z,"damage":actual}),
                    );
                }
                if p.role == "hero" {
                    let splash: Vec<usize> = self
                        .robots
                        .iter()
                        .enumerate()
                        .filter(|(_, r)| {
                            r.alive
                                && r.team != p.team
                                && dist(x, y, r.x, r.y) < 1.4
                                && (r.z - z).abs() < 1.3
                        })
                        .map(|(i, _)| i)
                        .collect();
                    for i in splash {
                        if kind != 1 || i != index {
                            self.damage_robot(i, p.damage * 0.35, source);
                        }
                    }
                    self.event(
                        "explosion",
                        json!({"x":x,"y":y,"z":z,"team":p.team,"radius":1.4}),
                    );
                } else {
                    self.event("impact", json!({"x":x,"y":y,"z":z,"team":p.team}));
                }
                continue;
            }
            p.x += dx;
            p.y += dy;
            p.z += dz;
            p.vz -= 9.81 * ratio;
            p.remaining -= length;
            if p.remaining > 0.0
                && p.x >= 0.0
                && p.x <= self.arena.width
                && p.y >= 0.0
                && p.y <= self.arena.height
            {
                remaining.push(p);
            }
        }
        self.projectiles = remaining;
    }
    fn update_zones(&mut self) {
        let mut events = Vec::new();
        for z in &self.arena.zones {
            let red = self
                .robots
                .iter()
                .any(|r| r.alive && r.team == "red" && dist(r.x, r.y, z.x, z.y) <= z.radius);
            let blue = self
                .robots
                .iter()
                .any(|r| r.alive && r.team == "blue" && dist(r.x, r.y, z.x, z.y) <= z.radius);
            let state = self.zones.get_mut(&z.id).unwrap();
            state.contested = red && blue;
            if red != blue {
                state.progress =
                    (state.progress + if red { DT / 3.0 } else { -DT / 3.0 }).clamp(-1.0, 1.0);
                let owner = if state.progress >= 1.0 - 1e-8 {
                    Some("red".into())
                } else if state.progress <= -1.0 + 1e-8 {
                    Some("blue".into())
                } else {
                    None
                };
                if owner != state.owner {
                    state.owner = owner.clone();
                    events.push(json!({"zone":z.id,"team":owner,"x":z.x,"y":z.y,"z":height_at(&self.arena,z.x,z.y)}));
                }
            }
            if let Some(owner) = &state.owner {
                if !state.contested {
                    let team = self.teams.get_mut(owner).unwrap();
                    team.score += 4.0 * DT;
                    team.resources += 3.0 * DT;
                    team.captured_seconds += DT;
                }
            }
        }
        for data in events {
            self.event("capture", data);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn deterministic_action_trace() {
        let mut a = Engine::new(42, 10.0, "foundry").unwrap();
        let mut b = Engine::new(42, 10.0, "foundry").unwrap();
        let commands = json!({"red":{"1":{"move":[1,0],"aim":0,"fire":true}},"blue":{"1":{"move":[-1,0],"aim":3.141592653589793,"fire":true}}});
        for _ in 0..200 {
            assert_eq!(a.step(&commands), b.step(&commands));
        }
        assert_eq!(a.digest(), b.digest());
        assert_eq!(a.status, "finished");
    }
    #[test]
    fn fields_of_view_are_private() {
        let mut m = Engine::new(42, 10.0, "foundry").unwrap();
        m.robots[0].x = 20.0;
        m.robots[0].y = 2.0;
        m.robots[0].z = 1.2;
        m.robots[7].x = 23.0;
        m.robots[7].y = 2.0;
        assert_eq!(
            m.observation("red", Some(&[1]))["enemies"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert_eq!(
            m.observation("red", Some(&[2]))["enemies"]
                .as_array()
                .unwrap()
                .len(),
            0
        );
        assert!(m.observation("red", None)["enemies"][0]
            .get("ammo")
            .is_none());
    }
    #[test]
    fn wall_and_height_affect_visibility() {
        let mut m = Engine::new(42, 10.0, "foundry").unwrap();
        m.robots[0].x = 16.0;
        m.robots[0].y = 9.0;
        m.robots[7].x = 24.0;
        m.robots[7].y = 9.0;
        assert!(!m.visible(&m.robots[0], &m.robots[7]));
        m.robots[0].z = 4.0;
        m.robots[7].z = 4.0;
        assert!(m.visible(&m.robots[0], &m.robots[7]));
    }
    #[test]
    fn accelerated_motion_and_clamped_actions() {
        let mut m = Engine::new(42, 10.0, "foundry").unwrap();
        m.step(&json!({"red":{"1":{"move":[100,100]}}}));
        assert!(m.robots[0].vx.hypot(m.robots[0].vy) <= 7.0 * DT + 1e-8);
        assert!(m.robots[0].x > 3.5);
        assert!(m.robots[0].x < 3.6);
    }
    #[test]
    fn projectile_hits_are_swept() {
        assert!((segment_circle(0.0, 0.0, 10.0, 0.0, 5.0, 0.0, 1.0).unwrap() - 0.4).abs() < 1e-8);
        let mut m = Engine::new(42, 10.0, "foundry").unwrap();
        m.robots[0].x = 20.0;
        m.robots[0].y = 12.0;
        m.robots[7].x = 22.0;
        m.robots[7].y = 12.0;
        m.step(&json!({"red":{"1":{"aim":0,"fire":true,"pitch":0}}}));
        assert!(m.robots[7].hp < 420.0);
        assert_eq!(m.robots[0].ammo, 35);
    }
    #[test]
    fn collisions_never_leave_overlapping_robots() {
        let mut m = Engine::new(42, 20.0, "foundry").unwrap();
        m.robots[0].x = 11.0;
        m.robots[0].y = 7.0;
        for _ in 0..200 {
            m.step(&json!({"red":{"1":{"move":[1,0]},"2":{"move":[1,0]},"3":{"move":[1,0]}}}));
            for (i, a) in m.robots.iter().enumerate() {
                assert!(!m.blocked(a.x, a.y, a.radius));
                for b in &m.robots[i + 1..] {
                    if (a.z - b.z).abs() < 0.9 {
                        assert!(dist(a.x, a.y, b.x, b.y) >= a.radius + b.radius - 1e-5);
                    }
                }
            }
        }
        assert!(m.robots[0].x <= 11.52 + 1e-8);
    }
    #[test]
    fn heat_prevents_unlimited_fire() {
        let mut m = Engine::new(42, 15.0, "foundry").unwrap();
        m.specs.get_mut("sentry").unwrap().cooling = 1.0;
        for _ in 0..100 {
            m.step(&json!({"red":{"6":{"fire":true}}}));
        }
        assert!(m.robots[5].overheated);
        let ammo = m.robots[5].ammo;
        m.step(&json!({"red":{"6":{"fire":true}}}));
        assert_eq!(m.robots[5].ammo, ammo);
    }
    #[test]
    fn skills_consume_energy_and_heal() {
        let mut m = Engine::new(42, 10.0, "foundry").unwrap();
        m.robots[0].hp = 100.0;
        m.robots[0].x = 18.0;
        m.robots[0].y = 12.0;
        m.robots[1].x = 20.0;
        m.robots[1].y = 12.0;
        m.step(&json!({"red":{"2":{"skill":true}}}));
        assert_eq!(m.robots[0].hp, 145.0);
        assert_eq!(m.robots[1].energy, 50.0);
        assert_eq!(m.robots[1].skill_cooldown, 15.0);
    }
    #[test]
    fn terrain_and_economy() {
        let mut m = Engine::new(42, 25.0, "foundry").unwrap();
        assert!((height_at(&m.arena, 16.0, 4.0) - 0.6).abs() < 1e-8);
        assert_eq!(height_at(&m.arena, 20.0, 4.0), 1.2);
        m.robots[0].x = 20.0;
        m.robots[0].y = 12.0;
        for _ in 0..500 {
            m.step(&json!({}));
        }
        assert_eq!(m.zones["center"].owner.as_deref(), Some("red"));
        assert!(m.robots[0].level > 1);
        assert_eq!(m.winner.as_deref(), Some("red"));
    }
    #[test]
    fn invalid_fields_and_large_numbers_fail_closed() {
        let mut m = Engine::new(42, 10.0, "foundry").unwrap();
        let raw: Value = serde_json::from_str(&format!(
            "{{\"red\":{{\"1\":{{\"move\":[{},0],\"fire\":\"yes\"}}}}}}",
            "9".repeat(500)
        ))
        .unwrap();
        m.step(&raw);
        assert_eq!(m.robots[0].x, 3.5);
        assert_eq!(
            m.events
                .iter()
                .filter(|e| e["type"] == "invalid_action")
                .count(),
            2
        );
    }
    #[test]
    fn ended_matches_are_immutable() {
        let mut m = Engine::new(42, 10.0, "foundry").unwrap();
        m.bases.get_mut("blue").unwrap().hp = 0.0;
        m.step(&json!({}));
        assert_eq!(m.reason.as_deref(), Some("base_destroyed"));
        let hash = m.digest();
        m.step(&json!({}));
        assert_eq!(m.digest(), hash);
    }
    #[test]
    fn falling_projectile_hits_a_cylinder_after_entering_horizontal_radius() {
        let p = Projectile {
            id: 1,
            source: "red-1".into(),
            team: "red".into(),
            role: "hero".into(),
            x: 0.0,
            y: 0.0,
            z: 3.0,
            vx: 0.0,
            vy: 0.0,
            vz: 0.0,
            remaining: 10.0,
            damage: 60.0,
            radius: 0.0,
        };
        let t = segment_cylinder(&p, 10.0, 0.0, -4.0, 5.0, 0.0, 1.0, 0.0, 1.0).unwrap();
        assert!((t - 0.5).abs() < 1e-8);
    }
}
