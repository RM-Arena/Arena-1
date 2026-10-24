//! RMUC 2027 rules: lineups, inspection, economy, control, structures, aerial system,
//! heavy launcher, sentry postures, crossings and the timeout ranking.
use super::*;

fn match_() -> Engine {
    Engine::new(42, 420.0, "rmuc2027").unwrap()
}
fn robot(m: &Engine, id: &str) -> usize {
    m.robots.iter().position(|r| r.id == id).unwrap()
}
fn place(m: &mut Engine, i: usize, x: f64, y: f64) {
    let r = &mut m.robots[i];
    r.x = x;
    r.y = y;
    r.z = height_at(&m.arena, x, y);
}
fn zone_center(m: &Engine, id: &str) -> [f64; 2] {
    let z = m.arena.zones.iter().find(|z| z.id == id).unwrap();
    if z.polygon.is_empty() {
        return [z.x, z.y];
    }
    let n = z.polygon.len() as f64;
    [z.polygon.iter().map(|p| p[0]).sum::<f64>() / n, z.polygon.iter().map(|p| p[1]).sum::<f64>() / n]
}
fn lineup(models: &[(u32, u32)]) -> Option<BTreeMap<String, Vec<Deployment>>> {
    let list: Vec<Deployment> = models.iter().map(|(slot, model)| Deployment { slot: *slot, model: *model }).collect();
    Some([("red".into(), list.clone()), ("blue".into(), list)].into())
}

#[test]
fn default_lineup_fields_heavy_infantry_sentry_and_aerial_system() {
    let m = match_();
    assert_eq!(m.season, 2027);
    let slots: Vec<u32> = m.robots.iter().filter(|r| r.team == "red").map(|r| r.slot).collect();
    assert_eq!(slots, vec![1, 3, 4, 6, 7]);
    let heavy = &m.robots[robot(&m, "red-1")];
    assert_eq!((heavy.role.as_str(), heavy.design_slot(), heavy.hp, heavy.launcher.as_str()), ("heavy", 2711, 400.0, "locked"));
    let sentry = &m.robots[robot(&m, "red-7")];
    assert_eq!((sentry.role.as_str(), sentry.hp, sentry.ammo, sentry.max_heat, sentry.posture.as_str()), ("sentry", 400.0, 300, 260.0, "move"));
    let aerial = &m.robots[robot(&m, "red-6")];
    assert_eq!((aerial.role.as_str(), aerial.drones.len()), ("aerial", 4));
    assert!(aerial.drones.iter().all(|d| d.state == "docked"));
    assert_eq!((m.bases["red"].max_hp, m.outposts["red"].max_hp), (10000.0, 1000.0));
    assert_eq!(m.teams["red"].energy_units_left, Some(6));
    for id in ["red_outpost", "red_base", "blue_outpost", "blue_base"] {
        let p = &m.positions[id];
        assert_eq!((p.control.as_str(), p.controller.as_str()), ("full", p.owner.as_str()));
    }
    assert_eq!(m.snapshot()["rules"], "rmuc-2027-v1.0.0-arena-v1");
}

#[test]
fn each_season_admits_only_models_that_pass_its_construction_rules() {
    let hero = Engine::new_with_lineups(42, 10.0, "rmuc2027", lineup(&[(1, 1), (3, 3), (4, 4), (6, 2761), (7, 2771)]));
    assert!(hero.err().unwrap().contains("does not pass the 2027"));
    let heavy = Engine::new_with_lineups(42, 10.0, "rmuc2026", lineup(&[(1, 2711), (2, 2), (3, 3), (4, 4), (6, 6), (7, 7)]));
    assert!(heavy.err().unwrap().contains("does not pass the 2026"));
    let drone = Engine::new_with_lineups(42, 10.0, "rmuc2027", lineup(&[(1, 2711), (6, 6)]));
    assert!(drone.is_err());
    // A 2026 infantry passes the 2027 infantry limits and plays a 2027 slot.
    let mixed = Engine::new_with_lineups(42, 10.0, "rmuc2027", lineup(&[(1, 2712), (3, 301), (4, 304), (6, 2762), (7, 2772)])).unwrap();
    assert_eq!(mixed.robots[robot(&mixed, "red-3")].design_slot(), 301);
    let twice = Engine::new_with_lineups(42, 10.0, "rmuc2027", lineup(&[(1, 2761), (2, 2762)]));
    assert!(twice.err().unwrap().contains("one aerial system"));
}

#[test]
fn coins_follow_the_2027_schedule() {
    let mut m = match_();
    m.tick = 20;
    m.step(&json!({}));
    assert_eq!(m.teams["red"].resources, 800.0);
    m.tick = 1220;
    m.step(&json!({}));
    assert_eq!(m.teams["red"].resources, 900.0);
    m.tick = 7220;
    m.step(&json!({}));
    assert_eq!(m.teams["red"].resources, 1200.0);
}

#[test]
fn occupying_an_outpost_position_takes_temporary_control_and_strips_the_base_defense() {
    let mut m = match_();
    let blue = robot(&m, "blue-3");
    let card = zone_center(&m, "red_outpost");
    place(&mut m, blue, card[0], card[1]);
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    assert_eq!(m.structure_defense("red", false), 1.0);
    for _ in 0..140 {
        m.robots[blue].x = card[0];
        m.robots[blue].y = card[1];
        m.step(&json!({}));
        if m.positions["red_outpost"].control == "temporary" {
            break;
        }
    }
    let p = &m.positions["red_outpost"];
    assert_eq!((p.control.as_str(), p.controller.as_str()), ("temporary", "blue"));
    assert_eq!(m.structure_defense("red", false), 0.0);
    assert!(m.fortress_active("red"));
    // Absent for five seconds, the temporary holder hands it back.
    place(&mut m, blue, 20.0, 7.5);
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    for _ in 0..200 {
        m.step(&json!({}));
    }
    let p = &m.positions["red_outpost"];
    assert_eq!((p.control.as_str(), p.controller.as_str()), ("full", "red"));
}

#[test]
fn a_destroyed_outpost_is_rebuilt_for_the_team_that_takes_full_control() {
    let mut m = match_();
    m.outposts.get_mut("red").unwrap().hp = 0.0;
    m.outposts.get_mut("red").unwrap().ever_destroyed = true;
    m.outpost_destroyed("red");
    assert_eq!(m.positions["red_outpost"].control, "temporary");
    assert_eq!(m.positions["red_outpost"].controller, "red");
    for _ in 0..120 {
        m.step(&json!({}));
    }
    let p = &m.positions["red_outpost"];
    assert_eq!((p.control.as_str(), p.controller.as_str()), ("full", "blue"));
    let o = &m.outposts["red"];
    assert_eq!((o.hp, o.owner.as_deref()), (500.0, Some("blue")));
    // Holding both outpost positions builds control degree for blue.
    for _ in 0..40 {
        m.step(&json!({}));
    }
    assert!(m.teams["blue"].control.unwrap() >= 1.9);
    assert_eq!(m.teams["red"].control.unwrap(), 0.0);
}

#[test]
fn an_aerial_robot_strike_damages_enemy_outpost_armor_and_wears_its_guard() {
    let mut m = match_();
    m.tick = 3620; // outposts stop rotating after 3 minutes
    let a = robot(&m, "blue-6");
    m.step(&json!({"blue":{"6":{"drones":{"1":{"launch":true}}}}}));
    let plate = Engine::structure_plates_2027(&m.outposts["red"], true)[0];
    let n = plate.normal;
    let start = [plate.center[0] + n[0] * 0.5, plate.center[1] + n[1] * 0.5, plate.center[2]];
    let speed = 3.0;
    m.robots[a].drones[0].state = "flying".into();
    m.robots[a].drones[0].launch_until = 0.0;
    m.physics.as_mut().unwrap().place_drone(a, 0, start, [-n[0] * speed, -n[1] * speed, 0.0]);
    let before = m.outposts["red"].hp;
    let mut struck = false;
    for _ in 0..20 {
        m.step(&json!({"blue":{"6":{"drones":{"1":{"move":[-n[0],-n[1],0.0]}}}}}));
        struck |= m.events.iter().any(|e| e["type"] == "drone_strike" && e["valid"] == true);
        if struck {
            break;
        }
    }
    assert!(struck, "{:?}", m.robots[a].drones[0].z);
    assert_eq!(m.outposts["red"].hp, before - 200.0);
    assert_eq!(m.robots[a].drones[0].integrity, 2.0);
    assert_eq!(m.teams["blue"].attack_damage, 200.0);
}

#[test]
fn the_heavy_launcher_unlocks_fits_at_the_workbench_and_installs_with_its_first_shot() {
    let mut m = match_();
    let h = robot(&m, "red-1");
    m.teams.get_mut("red").unwrap().completed_difficulties = vec![1, 2, 3];
    m.step(&json!({}));
    assert_eq!(m.robots[h].launcher, "unlocked");
    let dock = m.arena.zones.iter().find(|z| z.id == "red_workbench").map(|z| [z.x, z.y]).unwrap();
    place(&mut m, h, dock[0], dock[1]);
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    for _ in 0..160 {
        m.step(&json!({"red":{"1":{"install_launcher":true,"brake":true}}}));
        if m.robots[h].launcher == "fitted" {
            break;
        }
    }
    assert_eq!(m.robots[h].launcher, "fitted");
    m.robots[h].ammo = 3;
    let mut shots = 0;
    for _ in 0..10 {
        m.step(&json!({"red":{"1":{"fire":true,"aim":0.0,"pitch":0.1,"brake":true}}}));
        shots += m.events.iter().filter(|e| e["type"] == "shot").count();
        if m.robots[h].launcher == "installed" {
            break;
        }
    }
    assert_eq!(m.robots[h].launcher, "installed");
    assert!(shots >= 1);
    assert_eq!(m.robots[h].max_hp, 600.0);
    assert_eq!(m.robots[h].max_heat, 300.0);
    assert!(m.projectiles.iter().any(|p| p.source == "red-1" && p.damage == 0.0) || shots == 1);
}

#[test]
fn the_heavy_launcher_can_be_fitted_before_its_usage_right_but_stays_unpowered() {
    let mut m = match_();
    let h = robot(&m, "red-1");
    let dock = m.arena.zones.iter().find(|z| z.id == "red_workbench").map(|z| [z.x, z.y]).unwrap();
    place(&mut m, h, dock[0], dock[1]);
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    for _ in 0..6 {
        m.step(&json!({"red":{"1":{"install_launcher":true,"brake":true}}}));
    }
    assert_eq!(m.robots[h].launcher, "installing");
    m.step(&json!({"red":{"1":{"brake":true}}}));
    assert_eq!((m.robots[h].launcher.as_str(), m.robots[h].launcher_progress), ("locked", 0.0));
    for _ in 0..160 {
        m.step(&json!({"red":{"1":{"install_launcher":true,"brake":true}}}));
        if m.robots[h].launcher == "fitted_locked" {
            break;
        }
    }
    assert_eq!(m.robots[h].launcher, "fitted_locked");
    assert!(m.events.iter().any(|e| e["type"] == "launcher_fitted" && e["powered"] == false));
    m.robots[h].ammo = 3;
    for _ in 0..10 {
        m.step(&json!({"red":{"1":{"fire":true,"aim":0.0,"pitch":0.1,"brake":true}}}));
        assert!(!m.events.iter().any(|e| e["type"] == "shot" && e["robot"] == "red-1"));
    }
    assert_eq!((m.robots[h].launcher.as_str(), m.robots[h].ammo), ("fitted_locked", 3));
    m.teams.get_mut("red").unwrap().completed_difficulties = vec![1, 2, 3];
    m.step(&json!({"red":{"1":{"brake":true}}}));
    assert_eq!(m.robots[h].launcher, "fitted");
    for _ in 0..10 {
        m.step(&json!({"red":{"1":{"fire":true,"aim":0.0,"pitch":0.1,"brake":true}}}));
        if m.robots[h].launcher == "installed" {
            break;
        }
    }
    assert_eq!(m.robots[h].launcher, "installed");
}

#[test]
fn launcher_unlocks_earlier_for_the_team_that_falls_behind() {
    let mut m = match_();
    m.bases.get_mut("red").unwrap().hp = 7500.0; // blue leads by 2500 HP: 300 - 50 = 250 s
    m.step(&json!({}));
    assert_eq!(m.teams["red"].launcher_unlock_s, Some(250.0));
    assert_eq!(m.teams["blue"].launcher_unlock_s, Some(300.0));
    m.tick = 250 * 20;
    m.step(&json!({}));
    assert_eq!(m.robots[robot(&m, "red-1")].launcher, "unlocked");
    assert_eq!(m.robots[robot(&m, "blue-1")].launcher, "locked");
}

#[test]
fn a_locked_heavy_fits_early_but_cannot_fire_until_the_unlock() {
    let mut m = match_();
    let h = robot(&m, "red-1");
    m.step(&json!({}));
    assert_eq!(m.robots[h].launcher, "locked");
    let dock = m.arena.zones.iter().find(|z| z.id == "red_workbench").map(|z| [z.x, z.y]).unwrap();
    place(&mut m, h, dock[0], dock[1]);
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    // Installing is allowed at any time in the match, before the rules' unlock.
    for _ in 0..200 {
        m.step(&json!({"red":{"1":{"install_launcher":true,"brake":true}}}));
        if ["fitted", "fitted_locked"].contains(&m.robots[h].launcher.as_str()) {
            break;
        }
    }
    assert_eq!(m.robots[h].launcher, "fitted_locked");
    assert!(m.teams["red"].launcher_unlock_s.unwrap() > 200.0);
    // …but the trigger stays dead while the team has not unlocked it: no round leaves the magazine.
    m.robots[h].ammo = 5;
    for _ in 0..40 {
        m.step(&json!({"red":{"1":{"fire":true,"aim":0.0,"pitch":0.1,"brake":true}}}));
    }
    assert_eq!(m.robots[h].ammo, 5);
    assert!(!m.events.iter().any(|e| e["type"] == "shot" && e["robot"] == "red-1"));
    assert_eq!(m.robots[h].launcher, "fitted_locked");
    // Finish difficulty 3 and the same trigger fires, installing the module on its first shot.
    m.teams.get_mut("red").unwrap().completed_difficulties = vec![1, 2, 3];
    for _ in 0..20 {
        m.step(&json!({"red":{"1":{"fire":true,"aim":0.0,"pitch":0.1,"brake":true}}}));
        if m.robots[h].ammo < 5 {
            break;
        }
    }
    assert!(m.events.iter().any(|e| e["type"] == "shot" && e["robot"] == "red-1"));
    assert_eq!(m.robots[h].launcher, "installed");
}

#[test]
fn sentry_postures_trade_power_cooling_and_protection() {
    let mut m = match_();
    let s = robot(&m, "red-7");
    m.step(&json!({}));
    assert_eq!(m.robots[s].power_limit, 150.0); // move posture: 100 W x 1.5
    assert_eq!(m.robots[s].vulnerability, 0.25);
    m.tick = 200;
    m.step(&json!({"red":{"7":{"posture":"attack"}}}));
    assert_eq!(m.robots[s].posture, "attack");
    assert_eq!((m.robots[s].power_limit, m.robots[s].cooling_multiplier), (50.0, 3.0));
    m.step(&json!({"red":{"7":{"posture":"defense"}}}));
    assert_eq!(m.robots[s].posture, "attack", "5 s switch cooldown");
    m.tick = 320;
    m.step(&json!({"red":{"7":{"posture":"defense","posture_enhanced":true}}}));
    assert_eq!((m.robots[s].posture.as_str(), m.robots[s].posture_enhanced), ("defense", true));
    assert_eq!(m.robots[s].defense_buff, 0.99);
    for _ in 0..320 {
        m.step(&json!({}));
    }
    assert!(!m.robots[s].posture_enhanced, "15 s enhanced budget");
    assert_eq!(m.robots[s].defense_buff, 0.5);
}

#[test]
fn sentry_collects_one_hundred_rounds_per_minute_at_its_supply_area() {
    let mut m = match_();
    let s = robot(&m, "red-7");
    m.tick = 20 * 125;
    let supply = zone_center(&m, "red_supply");
    place(&mut m, s, supply[0], supply[1]);
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    m.step(&json!({}));
    assert_eq!(m.robots[s].ammo, 500);
    m.step(&json!({}));
    assert_eq!(m.robots[s].ammo, 500);
}

#[test]
fn lost_base_hp_slows_respawn_and_remote_healing() {
    let mut m = match_();
    assert_eq!(m.logistics("red"), 1.0);
    m.bases.get_mut("red").unwrap().hp = 6000.0;
    assert!((m.logistics("red") - 0.8).abs() < 1e-12);
    let i = robot(&m, "red-3");
    let p = Projectile { id: 1, source: "blue-4".into(), team: "blue".into(), role: "infantry".into(), x: 0.0, y: 0.0, z: 0.0,
        vx: -25.0, vy: 0.0, vz: 0.0, remaining: 1.0, damage: 20.0, radius: 0.0084, deployed: false };
    m.robots[i].hp = 5.0;
    m.tick = 2000; // 100 s: (10 + 10) / 0.8 = 25
    let r = m.robots[i].clone();
    let (origin, _) = physics::muzzle(&r);
    let face = [r.x + r.chassis_size_m[0] / 2.0, r.y, r.z + r.armor_center_z_m];
    let _ = origin;
    m.robot_hit_2027(i, &Projectile { x: face[0] + 0.2, y: face[1], z: face[2], ..p }, face[0], face[1], face[2]);
    assert!(!m.robots[i].alive);
    assert_eq!(m.robots[i].respawn_required, 25.0);
}

#[test]
fn a_fully_controlled_outpost_heals_at_half_the_supply_rate_and_clears_weakness() {
    let mut m = match_();
    let i = robot(&m, "red-3");
    let spot = zone_center(&m, "red_outpost");
    place(&mut m, i, spot[0], spot[1]);
    m.robots[i].last_shot_time = -1000.0;
    m.robots[i].last_damage_time = -1000.0;
    for _ in 0..4 {
        m.step(&json!({}));
    }
    assert!(m.contacted_zone_2027(i, "outpost", Some("red")));
    let cap = m.robots[i].max_hp;
    m.tick = 20;
    m.robots[i].hp = (cap * 0.25).round();
    let low = m.robots[i].hp;
    m.step(&json!({}));
    let gained = m.robots[i].hp - low;
    let expected = cap * 0.05;
    assert!((gained - expected).abs() <= 2.0, "outpost healed {gained:+}, expected about {expected:+} (half of the supply rate)");
    // The buff card also lifts weakness and the protection that came with it.
    m.robots[i].weak = true;
    m.robots[i].respawned_at = m.time() - 20.0;
    m.robots[i].invulnerable_until = m.time() + 30.0;
    for _ in 0..4 {
        m.step(&json!({}));
    }
    assert!(!m.robots[i].weak);
    assert!(m.robots[i].invulnerable_until <= m.time() + 1e-6);
}

#[test]
fn supercap_drain_includes_the_forty_percent_conversion_loss() {
    let mut m = match_();
    let i = robot(&m, "red-3");
    place(&mut m, i, 5.0, 7.5);
    m.robots[i].supercap_energy_j = 1500.0;
    let order = json!({"red": {"3": {"move": [1.0, 0.0], "heading": 0.0, "power": 200.0}}});
    for _ in 0..10 {
        m.step(&order);
    }
    let limit = m.robots[i].power_limit;
    let e0 = m.robots[i].supercap_energy_j;
    let before = m.robots[i].motor_power_w;
    m.step(&order);
    let drop = e0 - m.robots[i].supercap_energy_j;
    let motor = (before + m.robots[i].motor_power_w) / 2.0;
    let excess = motor - limit;
    assert!(excess > 10.0, "chassis drew only {motor} W against a {limit} W limit");
    let ideal = excess * DT;
    assert!(drop > ideal * 1.25, "supercap dropped {drop} J, near the loss-free {ideal} J");
    assert!(drop < ideal / 0.5, "supercap dropped {drop} J, beyond the 40% loss model of {ideal}");
}

#[test]
fn tunnel_cards_in_order_give_the_through_or_over_buffs() {
    for (cards, buff) in [(vec![0, 1, 2], "tunnel_through"), (vec![2, 0], "tunnel_over")] {
        let mut m = match_();
        let i = robot(&m, "red-4");
        for card in cards {
            let c = zone_center(&m, &format!("red_far_tunnel_{card}"));
            place(&mut m, i, c[0], c[1]);
            m.update_buffs_2027();
            m.tick += 4;
        }
        assert!(m.robots[i].crossing_buffs.contains_key(buff), "{buff}: {:?}", m.robots[i].crossing_buffs);
    }
}

#[test]
fn timeout_ranks_control_degree_before_damage() {
    let mut m = Engine::new(42, 2.0, "rmuc2027").unwrap();
    m.teams.get_mut("red").unwrap().control = Some(3.0);
    m.teams.get_mut("blue").unwrap().attack_damage = 900.0;
    for _ in 0..40 {
        m.step(&json!({}));
    }
    assert_eq!((m.winner.as_deref(), m.reason.as_deref()), (Some("red"), Some("timeout")));
}

#[test]
fn the_2027_heavy_completes_a_level_one_assembly_physically() {
    let mut m = match_();
    let h = robot(&m, "red-1");
    let zone = m.arena.zones.iter().find(|z| z.id == "red_assembly").unwrap().clone();
    place(&mut m, h, zone.x + 0.14, zone.y + 0.14);
    let r = &mut m.robots[h];
    r.heading = std::f64::consts::FRAC_PI_4;
    r.quaternion = [0.0, 0.0, (r.heading / 2.0).sin(), (r.heading / 2.0).cos()];
    r.carried_units = 1;
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    for _ in 0..500 {
        m.step(&json!({"red":{"1":{"assembly":1,"assembly_insert":true,"assembly_confirm":true,"brake":true}}}));
        if ["complete", "failed"].contains(&m.assemblies["red"].stage.as_str()) {
            break;
        }
    }
    assert_eq!(m.assemblies["red"].stage, "complete", "{}", m.assembly_snapshots()["red"]);
    assert_eq!(m.robots[h].level, 5);
    assert_eq!(m.robots[h].max_hp, 450.0);
    assert_eq!(m.teams["red"].tech_income, 40.0);
}

#[test]
fn every_heavy_picks_two_energy_units_at_the_resource_hub() {
    // The arm masts stand at the front corners beside the central gimbal; from the SDK's hub
    // approach (resource_pickup_point) each heavy still reaches the 0.70 m units.
    for model in [2711, 2712, 2713] {
        let mut m = Engine::new_with_lineups(42, 420.0, "rmuc2027", lineup(&[(1, model), (3, 2731), (4, 2732), (6, 2761), (7, 2771)])).unwrap();
        let h = robot(&m, "red-1");
        let station = m.arena.field_geometry["fixtures"].as_array().unwrap().iter()
            .find(|f| f["kind"] == "resource" && f["team"] == "red").unwrap().clone();
        let (point, dir) = (&station["pick_point"], &station["pick_dir"]);
        let (dx, dy) = (dir[0].as_f64().unwrap(), dir[1].as_f64().unwrap());
        let reach = if model == 2712 { 0.48 } else { 0.60 };
        place(&mut m, h, point[0].as_f64().unwrap() - dx * reach, point[1].as_f64().unwrap() - dy * reach);
        let r = &mut m.robots[h];
        r.heading = dy.atan2(dx);
        r.aim = r.heading;
        r.quaternion = [0.0, 0.0, (r.heading / 2.0).sin(), (r.heading / 2.0).cos()];
        m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
        for _ in 0..600 {
            m.step(&json!({"red":{"1":{"pick_unit":true,"brake":true,"heading":dy.atan2(dx)}}}));
            if m.robots[h].carried_units == 2 {
                break;
            }
        }
        assert_eq!(m.robots[h].carried_units, 2, "{model}: {:?}", m.robots[h].unit_pickup.as_ref().map(|p| p.stage.clone()));
        assert_eq!(m.teams["red"].energy_units_left, Some(4), "{model}");
    }
}

#[test]
fn a_heavy_carries_a_third_unit_in_its_gripper() {
    // Two bays fill first; the third unit the rules allow rides clamped in the gripper until a core
    // takes it, so the heavy can shuttle three cores back to back.
    let model = 2711;
    let mut m = Engine::new_with_lineups(42, 420.0, "rmuc2027", lineup(&[(1, model), (3, 2731), (4, 2732), (6, 2761), (7, 2771)])).unwrap();
    let h = robot(&m, "red-1");
    let station = m.arena.field_geometry["fixtures"].as_array().unwrap().iter()
        .find(|f| f["kind"] == "resource" && f["team"] == "red").unwrap().clone();
    let (point, dir) = (&station["pick_point"], &station["pick_dir"]);
    let (dx, dy) = (dir[0].as_f64().unwrap(), dir[1].as_f64().unwrap());
    let reach = if model == 2712 { 0.48 } else { 0.60 };
    place(&mut m, h, point[0].as_f64().unwrap() - dx * reach, point[1].as_f64().unwrap() - dy * reach);
    let r = &mut m.robots[h];
    r.heading = dy.atan2(dx);
    r.aim = r.heading;
    r.quaternion = [0.0, 0.0, (r.heading / 2.0).sin(), (r.heading / 2.0).cos()];
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    let command = json!({"red":{"1":{"pick_unit":true,"brake":true,"heading":dy.atan2(dx)}}});
    for _ in 0..900 {
        m.step(&command);
        if m.robots[h].units_on_board() == 3 {
            break;
        }
    }
    assert_eq!(m.robots[h].carried_units, 2, "the bays fill before the gripper: {:?}", m.robots[h].unit_pickup.as_ref().map(|p| p.stage.clone()));
    assert!(m.robots[h].gripper_unit(), "the third unit has to stay in the gripper");
    assert_eq!(m.robots[h].unit_pickup.as_ref().map(|p| p.stage.as_str()), Some("carrying"));
    assert!(m.robots[h].unit_pickup.as_ref().unwrap().held);
    assert_eq!(m.robots[h].units_on_board(), 3);
    assert_eq!(m.teams["red"].energy_units_left, Some(3), "the third unit comes out of the team's stock");
    // Carrying across the field must not cancel the third unit, and asking again must not restart it.
    m.robots[h].x += 3.0;
    for _ in 0..20 {
        m.step(&json!({"red":{"1":{"brake":true}}}));
    }
    assert_eq!(m.robots[h].units_on_board(), 3, "a carried unit survives leaving the resource zone");
    m.step(&command);
    assert_eq!(m.robots[h].units_on_board(), 3, "a full robot cannot grab a fourth unit");
}

#[test]
fn launcher_fitting_restarts_when_the_heavy_robot_stops_asking_or_leaves_the_workbench() {
    let mut m = match_();
    let h = robot(&m, "red-1");
    m.teams.get_mut("red").unwrap().completed_difficulties = vec![1, 2, 3];
    m.step(&json!({}));
    let dock = m.arena.zones.iter().find(|z| z.id == "red_workbench").map(|z| [z.x, z.y]).unwrap();
    place(&mut m, h, dock[0], dock[1]);
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    for _ in 0..6 {
        m.step(&json!({"red":{"1":{"install_launcher":true,"brake":true}}}));
    }
    assert_eq!(m.robots[h].launcher, "installing");
    assert!(m.robots[h].launcher_progress > 0.0);
    for _ in 0..4 {
        m.step(&json!({"red":{"1":{"brake":true}}}));
    }
    assert_eq!((m.robots[h].launcher.as_str(), m.robots[h].launcher_progress), ("unlocked", 0.0));
}

#[test]
fn tunnel_passages_match_the_road_area_plan() {
    // Figure 4-35: the near-highland tunnel's 800 mm passage lies between its rail on the
    // central highland's edge and the far tunnel's north rail, which the tunnels share; the
    // road tunnel has only its portal posts, 800 mm apart, over the top of its ramp.
    let m = match_();
    let walls = |id: &str| m.arena.obstacles.iter().filter(|w| w.id == id).cloned().collect::<Vec<_>>();
    let (near, far) = (walls("red_near_tunnel_side"), walls("red_far_tunnel_side"));
    assert_eq!((near.len(), far.len()), (1, 2));
    assert!((far[0].y - (near[0].y + near[0].h) - 0.8).abs() < 0.005, "near passage {}", far[0].y - near[0].y - near[0].h);
    assert!((far[1].y - (far[0].y + far[0].h) - 0.8).abs() < 0.005);
    assert!(walls("red_road_tunnel_side").is_empty());
    let posts = walls("red_road_tunnel_post");
    assert_eq!(posts.len(), 2);
    // Posts run along y (rotated a quarter turn): their centres sit 0.8 + 0.1 m apart.
    let centre = |w: &Wall| w.x + w.w / 2.0;
    assert!(((centre(&posts[1]) - centre(&posts[0])).abs() - 0.9).abs() < 1e-6);
    let ramp = m.arena.terrain.iter().find(|t| t.id == "red_road_tunnel_ramp").unwrap();
    // Heights above the tilted floor (1.5 degrees toward the long sides).
    let above = |y: f64| height_at(&m.arena, 9.32, y) - (15.0 - y) * m.arena.floor_slope_deg.to_radians().tan();
    let (foot, top) = (above(ramp.y + 0.01), above(12.9));
    assert!(foot < 0.01 && (top - 0.2).abs() < 0.01, "ramp {foot} .. {top}");
}

#[test]
fn a_folded_infantry_drives_up_the_road_tunnel_ramp_under_its_portal() {
    let mut m = Engine::new_with_lineups(42, 60.0, "rmuc2027", lineup(&[(1, 2711), (3, 2731), (4, 2732), (6, 2761), (7, 2771)])).unwrap();
    let i = robot(&m, "red-4");
    let x = 9.32;
    place(&mut m, i, x, 11.7);
    let r = &mut m.robots[i];
    r.heading = std::f64::consts::FRAC_PI_2;
    r.quaternion = [0.0, 0.0, (r.heading / 2.0).sin(), (r.heading / 2.0).cos()];
    m.physics = Some(physics::PhysicsWorld::new(&m.arena, &m.robots, &config().robot_designs));
    for _ in 0..60 {
        m.step(&json!({"red":{"4":{"transform":true,"heading":std::f64::consts::FRAC_PI_2}}}));
    }
    for _ in 0..400 {
        let r = &m.robots[i];
        m.step(&json!({"red":{"4":{"move":[(x - r.x) * 1.5, 0.6],"heading":std::f64::consts::FRAC_PI_2,"transform":true,"power":120}}}));
        if m.robots[i].y > 13.5 {
            break;
        }
    }
    let r = &m.robots[i];
    assert!(r.y > 13.4 && r.z > 0.15 && r.upright > 0.8 && !r.tipped, "stopped at y {} z {} up {}", r.y, r.z, r.upright);
    assert!(r.crossing_buffs.contains_key("tunnel_through"), "{:?}", r.crossing_buffs);
}

#[test]
fn drones_pushed_into_a_spinning_outpost_stay_outside_its_armor_and_tower() {
    // A drone steered at the outpost's axis, slower than a strike at first and then at full
    // speed, never ends a tick inside an armor module, the collar or the tower.
    let mut m = match_();
    m.tick = 600;
    let a = robot(&m, "blue-6");
    m.step(&json!({"blue":{"6":{"drones":{"1":{"launch":true}}}}}));
    let radius = m.robot_models["2761"]["drone"]["radius_m"].as_f64().unwrap();
    let plate = Engine::structure_plates_2027(&m.outposts["red"], true)[1];
    let n = plate.normal;
    let start = [plate.center[0] + n[0] * 0.4, plate.center[1] + n[1] * 0.4, plate.center[2]];
    m.robots[a].drones[0].state = "flying".into();
    m.robots[a].drones[0].launch_until = 0.0;
    m.physics.as_mut().unwrap().place_drone(a, 0, start, [-n[0] * 0.8, -n[1] * 0.8, 0.0]);
    let mut contacts = 0;
    for tick in 0..150 {
        let (o, d) = (&m.outposts["red"], &m.robots[a].drones[0]);
        let to = [o.x - d.x, o.y - d.y, plate.center[2] - d.z];
        let length = (to[0] * to[0] + to[1] * to[1]).sqrt().max(1e-9);
        let gain = if tick < 60 { 0.2 } else { 1.0 };
        m.step(&json!({"blue":{"6":{"drones":{"1":{"move":[gain * to[0] / length, gain * to[1] / length, to[2]]}}}}}));
        let (o, d) = (&m.outposts["red"], &m.robots[a].drones[0]);
        let p = [d.x, d.y, d.z];
        assert!(structures::outpost_overlap(o, p, radius * 0.98, radius * 0.39).is_none(), "tick {tick}: drone inside the outpost at {p:?}");
        contacts += structures::outpost_overlap(o, p, radius * 1.3, radius * 0.6).is_some() as u32;
    }
    assert!(contacts > 20, "the drone should rest against the outpost, contacts {contacts}");
}
