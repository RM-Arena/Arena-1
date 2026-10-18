"""RMUC 2027 robot hardware designs, built within the 2027 construction manual V1.0.0.

The 2027 season merges the hero and engineer into the heavy robot (重装机器人: arm for
energy units plus a modular 42 mm launcher fitted at the workbench), adds the sentry and
turns the aerial robot into an aerial system (a hangar on the central platform carrying up
to four autonomous micro aerial robots that strike base/outpost armor by impact).
Chassis, suspension, legs and arm kinematics reuse the tuned 2026 hardware; every number
that the manual does not fix is a design choice, stated per model.
"""
import copy
import math

# 2027 model ids carry the season prefix: 27 + role digit + variant.
HEAVY, INFANTRY, SENTRY, AERIAL = (2711, 2712, 2713), (2731, 2732), (2771, 2772), (2761, 2762, 2763)
DEFAULT_LINEUP_2027 = {'1': 2711, '3': 2731, '4': 2732, '6': 2761, '7': 2771}
# Heavy referee kit (table 3-3): main controller, power management, light bar, four small
# armor modules, video transmitter, field interaction, positioning and supercap manager.
# The manual gives 3.25 kg for the infantry/sentry kit with its 17 mm speed module and UV
# charger; without those the heavy carries an estimated 2.9 kg.
HEAVY_REFEREE_KG = 2.9
INFANTRY_REFEREE_KG = 3.25
# Hangar kit: main controller, power management and video transmitter.
HANGAR_REFEREE_KG = .55


def inertia(mass, size):
    return [round(mass*(size[1]**2+size[2]**2)/12, 5), round(mass*(size[0]**2+size[2]**2)/12, 5),
            round(mass*(size[0]**2+size[1]**2)/12, 5)]


def finish(d, designs):
    d['mass_kg'] = round(d['bare_mass_kg']+d['referee_mass_kg'], 3)
    if d['role'] != 'aerial':
        d['inertia_kgm2'] = inertia(d['mass_kg'], d['chassis_size_m'])
        if d['chassis_type'] == 'wheel_legged':
            d['leg_stiffness_npm'] = round(d['mass_kg']*9.81/(2*.07), 3)
            d['suspension_stiffness_npm'] = round(d['mass_kg']*9.81/(4*d['suspension_static_compression_m']), 3)
            d['suspension_damping_nspm'] = round((d['mass_kg']/4*d['suspension_stiffness_npm'])**.5*1.25, 3)
        else:
            k = d['mass_kg']*9.81/(4*.035)
            d['suspension_stiffness_npm'] = round(k, 3)
            d['suspension_damping_nspm'] = round((d['mass_kg']/4*k)**.5*.8, 3)
    d['capabilities'] = {
        'deployment': False, 'transformation': d.get('transform_allowed', False),
        'jump': d['chassis_type'] == 'wheel_legged', 'self_righting': d.get('leg_type') == 'serial',
        'tunnel': 0 < d.get('folded_height_m', 1) <= .25, 'arms': d.get('arm_count', 0), 'drive': d['chassis_type'],
        'launcher': d.get('launcher', 'none'), 'drones': d.get('drone_count', 0),
        'step_climb_m': d.get('step_climb_m', 0)}
    designs[str(d['slot'])] = d
    return d


def base(designs, model, slot, role, name, focus, name_en, focus_en, **changes):
    d = copy.deepcopy(designs[str(model)])
    for key in ('hero_profile', 'deploy_allowed', 'charge_receiver', 'coil_size_m', 'coil_offset_m', 'base_model'):
        d.pop(key, None)
    d.update(changes, slot=slot, role=role, name=name, focus=focus, name_en=name_en, focus_en=focus_en,
             season='2027', revision='construction-2027-v1', asset=f'/assets/robot-{slot}-spec2027.glb', base_model=model,
             deploy_allowed=False, charge_receiver=False, hero_profile='ranged')
    d.setdefault('transform_allowed', False)
    return d


def tall_lift(d):
    """The 2027 resource hub holds its units 0.70 m up (4.2.6): the heavy robot's lift stage
    travels 0.64 m instead of the 2026 engineer's 0.50 m, so the tool can raise a unit
    clear of the hub while the fully raised arm stays under the 1.1 m extended height."""
    for key in ('arm', 'arm2'):
        if isinstance(d.get(key), dict):
            d[key]['limits'][1] = [0, .64]
            d[key]['source_status'] = d[key].get('source_status', '') + '; 2027 lift stage 0.64 m for the 0.70 m resource hub'
    return d


# Lift masts at the front corners, 0.275 m from the gimbal axis: carriage and boom stay
# outside the yaw sweep of the gimbal and launcher module (0.205 m with the magazine tipped
# back at full elevation) at every lift, with the boom overhang behind the carriage cut to
# 60 mm, and the boom crosses in front of the muzzle on a hub pick. Only the barrel itself,
# aimed into the raised arm's corner, can still meet it.
HEAVY_MAST_XY = (.18, .21)
HEAVY_BOOM_TAIL_M = .06
# Stowed: folded across the front of the chassis with the tool level (a 35-55 degree swing
# to the hub), lifted over the front armor module and below the gimbal and its barrel at any
# yaw and pitch; the dual arm's left arm folds 80 mm above the right one.
HEAVY_STOW_LIFT_M = (.09, .17)


def beside_gimbal(d):
    """The heavy robot's 42 mm gimbal stands on a column at the chassis centre, coaxial with
    the engine's muzzle pivot; the engineer arm (arm: right side, arm2: left) moves to a
    front corner beside it. Off-centre, the single arm's tool tip is held within 0.84 m of
    the chassis centre (workspace_half_m, applied by the engine and the asset build, as the
    dual arm already does) so it keeps to the 1.2 m extended envelope."""
    for key, side, lift in (('arm', -1, HEAVY_STOW_LIFT_M[0]), ('arm2', 1, HEAVY_STOW_LIFT_M[1])):
        arm = d.get(key)
        if not isinstance(arm, dict):
            continue
        arm['base_m'] = [HEAVY_MAST_XY[0], side*HEAVY_MAST_XY[1], arm['base_m'][2]]
        arm['boom_tail_m'] = HEAVY_BOOM_TAIL_M
        arm['stowed'] = [round(-side*math.pi/2, 4), lift, arm['limits'][2][0], 0, 0, 0, 0]
        arm.setdefault('workspace_half_m', .84)
        arm['source_status'] += '; 2027 mast at a front corner beside the central 42 mm gimbal'
    return d


def heavy(designs):
    """Engineer chassis and arm(s) beside a central column carrying the 42 mm gimbal."""
    launcher = dict(launcher='modular_42mm', launcher_module_kg=5.2, launcher_module_stowed_m=[.38, .30, .26],
                    launcher_module_voltage_v=24, launcher_module_battery_wh=0, launcher_capacitance_mf=40, launcher_install_s=6.0,
                    muzzle_speed_mps=15.6, turret_yaw_rate_rad_s=4.5, turret_pitch_rate_rad_s=2.2, trigger_interval_s=.2,
                    muzzle_z_m=.64, muzzle_reach_m=.30, armor_width_m=.135, carried_units_max=2,
                    referee_modules=['main_controller', 'power_management', 'light_bar', 'small_armor_x4', 'video_transmitter',
                                     'field_interaction', 'positioning', 'supercap_manager', 'speed_42mm_on_module'],
                    supercap_nominal_j=1800, supercap_max_current_a=12, step_climb_m=0)
    a = base(designs, 2, 2711, 'heavy', 'HV-A 单臂重装', '单臂取放能量单元、工作台装模块化42mm',
             'HV-A Single-arm Heavy', 'One arm for energy units; modular 42 mm launcher from the workbench',
             bare_mass_kg=28.9, referee_mass_kg=HEAVY_REFEREE_KG, battery_wh=280, voltage_v=24,
             stowed_m=[.59, .59, .59], extended_m=[1.18, 1.18, 1.08], speed_reference_mps=3.2, **launcher)
    finish(beside_gimbal(tall_lift(a)), designs)
    d = base(designs, 201, 2712, 'heavy', 'HV-D 双臂重装', '双臂同时操作两枚能量单元，适合四级双核心',
             'HV-D Dual-arm Heavy', 'Two arms handle both cores of a level-4 assembly',
             bare_mass_kg=31.2, referee_mass_kg=HEAVY_REFEREE_KG, battery_wh=290, voltage_v=24, chassis_type='swerve',
             steer_rate_rad_s=5.0, stowed_m=[.60, .60, .60], extended_m=[1.20, 1.20, 1.08], speed_reference_mps=2.8,
             tire_friction=1.2, lateral_friction_ratio=1.0, drive_efficiency=.84, motor_force_max_n=150, **launcher)
    d['launcher_module_kg'] = 5.6
    finish(beside_gimbal(tall_lift(d)), designs)
    o = base(designs, 203, 2713, 'heavy', 'HV-O 全向轻装重装', '轻量全向底盘、快速腕部与较轻发射模块',
             'HV-O Light Omni Heavy', 'Light omni chassis, fast wrist and a lighter launcher module',
             bare_mass_kg=26.4, referee_mass_kg=HEAVY_REFEREE_KG, battery_wh=260, voltage_v=24,
             stowed_m=[.59, .59, .59], extended_m=[1.18, 1.18, 1.06], speed_reference_mps=3.7, **launcher)
    o.update(launcher_module_kg=4.6, muzzle_speed_mps=15.2)
    finish(beside_gimbal(tall_lift(o)), designs)


def infantry(designs):
    kit = dict(referee_modules=['main_controller', 'power_management', 'light_bar', 'small_armor_x4', 'speed_17mm',
                                'video_transmitter', 'field_interaction', 'positioning', 'uv_charger', 'supercap_manager'],
               launcher='one_17mm', supercap_nominal_j=1800, supercap_max_current_a=12, muzzle_speed_mps=24.6)
    w = base(designs, 304, 2731, 'infantry', 'I27-W 登阶轮足步兵', '强跳腿组，登上制高点三级台阶、跨越隧道顶',
             'I27-W Stair-climbing Wheel-legged Infantry', 'Strong legs climb the high-point steps and hop tunnel roofs',
             bare_mass_kg=20.6, referee_mass_kg=INFANTRY_REFEREE_KG, battery_wh=220, voltage_v=24,
             jump_thrust_gain=2.2, jump_cooldown_s=.9, leg_max_m=.39, leg_speed_mps=1.6, speed_reference_mps=4.3,
             extended_m=[.66, .66, .80], chassis_profile='power', weapon_profile='cooling', step_climb_m=.2, **kit)
    finish(w, designs)
    m = base(designs, 301, 2732, 'infantry', 'I27-T 折叠麦轮步兵', '折叠炮塔钻过250mm隧道，取得穿越隧道冷却增益',
             'I27-T Folding Mecanum Infantry', 'Folds under the 250 mm tunnel roofs for the tunnel cooling buff',
             bare_mass_kg=21.1, referee_mass_kg=INFANTRY_REFEREE_KG, battery_wh=260, voltage_v=24,
             speed_reference_mps=3.9, chassis_profile='hp', weapon_profile='burst', step_climb_m=0, **kit)
    finish(m, designs)


def sentry(designs):
    kit = dict(referee_modules=['main_controller', 'power_management', 'light_bar', 'small_armor_x4', 'speed_17mm',
                                'field_interaction', 'positioning', 'uv_charger', 'supercap_manager', 'video_transmitter'],
               launcher='one_17mm', supercap_nominal_j=1800, supercap_max_current_a=12, muzzle_speed_mps=24.6,
               control='automatic', magazine_capacity=700)
    o = base(designs, 303, 2771, 'sentry', 'S27-O 全向自动哨兵', '全向底盘、快速云台与大弹仓，自主巡防',
             'S27-O Omni Automatic Sentry', 'Omni chassis, fast gimbal and a large magazine for autonomous patrol',
             bare_mass_kg=23.9, referee_mass_kg=INFANTRY_REFEREE_KG, battery_wh=290, voltage_v=24, speed_reference_mps=3.9,
             turret_yaw_rate_rad_s=8.0, turret_pitch_rate_rad_s=3.0, stowed_m=[.59, .59, .59], extended_m=[.74, .74, .72],
             chassis_profile='hp', weapon_profile='cooling', step_climb_m=0, **kit)
    finish(o, designs)
    w = base(designs, 305, 2772, 'sentry', 'S27-L 串联腿哨兵', '串联腿自翻正、登阶，可守制高点',
             'S27-L Serial-leg Sentry', 'Self-righting serial legs climb to the high point and hold it',
             bare_mass_kg=21.4, referee_mass_kg=INFANTRY_REFEREE_KG, battery_wh=240, voltage_v=24, speed_reference_mps=4.1,
             jump_thrust_gain=2.1, turret_yaw_rate_rad_s=7.0, chassis_profile='hp', weapon_profile='cooling', step_climb_m=.2, **kit)
    finish(w, designs)


def drone_size_limit_m(mass_kg):
    """S76: maximum extended size y (mm) for an aerial robot of mass x (kg)."""
    if mass_kg < .15:
        return .141
    return round((.3225-mass_kg)/.001225)/1000


def aerial(designs):
    """Hangar on the central platform plus up to four guarded micro aerial robots (S75-S83)."""
    rows = [
        (2761, 'AS-4 四机机库', '四架141mm轻型空中机器人，快而脆', 'AS-4 Four-drone Hangar', 'Four light 141 mm drones; fast but fragile',
         4, .145, .141, .028, 3.8, 7.4, 3.3, 6.0, 3),
        (2762, 'AS-2 重型双机机库', '两架加固小机，护罩更耐撞，续航短', 'AS-2 Twin Heavy-guard Hangar', 'Two compact reinforced drones survive more strikes',
         2, .205, .095, .020, 3.9, 11.1, 4.6, 4.6, 6),
        (2763, 'AS-3 均衡三机机库', '三架中型机，速度与耐撞折中', 'AS-3 Balanced Three-drone Hangar', 'Three mid-size drones balance speed and robustness',
         3, .175, .120, .024, 3.9, 7.4, 3.9, 5.3, 4),
    ]
    for slot, name, focus, name_en, focus_en, count, mass, size, rotor, wh, volts, thrust, speed, integrity in rows:
        d = dict(slot=slot, role='aerial', name=name, focus=focus, name_en=name_en, focus_en=focus_en, season='2027',
                 revision='construction-2027-v1', asset=f'/assets/robot-{slot}-spec2027.glb',
                 # The hangar is the system's body on the hangar platform; it carries the referee kit.
                 bare_mass_kg=round(2.6+count*.12, 2), referee_mass_kg=HANGAR_REFEREE_KG, battery_wh=120, voltage_v=24,
                 stowed_m=[.30, .30, .20], extended_m=[.58, .30, .38], chassis_size_m=[.30, .30, .20], ground_clearance_m=0,
                 com_m=[0, 0, .08], wheelbase_m=0, track_m=0, wheel_radius_m=0, wheel_width_m=0, chassis_type='hangar',
                 speed_reference_mps=speed, tire_friction=0, lateral_friction_ratio=0, drive_efficiency=0, rolling_resistance=0,
                 drag_area_m2=0, motor_force_max_n=0, brake_force_max_n=0, yaw_torque_max_nm=0, velocity_gain_per_s=0, yaw_gain_per_s=0,
                 suspension_rest_m=0, suspension_travel_m=0, suspension_static_compression_m=.018, suspension_stiffness_npm=0,
                 suspension_damping_nspm=0, inertia_kgm2=[.02, .02, .02], supercap_nominal_j=0, supercap_max_current_a=0,
                 charge_receiver=False, hero_profile='ranged', chassis_profile='hp', weapon_profile='cooling',
                 armor_count=0, armor_width_m=0, armor_height_m=0, armor_center_z_m=0, armor_inset_m=0, armor_normal_to_up_deg=75,
                 armor_mount_offset_m=0, armor_hit_face_offset_m=0, turret_yaw_rate_rad_s=0, turret_pitch_rate_rad_s=0,
                 pitch_limits_rad=[0, 0], muzzle_z_m=.12, muzzle_reach_m=0, trigger_interval_s=0, finish_gloss_gs=20,
                 contact_restitution=.1, launcher='none', deploy_allowed=False, transform_allowed=False, arm_count=0,
                 rotor_count=4, drone_count=count, hangar_capacity=4,
                 referee_modules=['main_controller', 'power_management', 'video_transmitter'],
                 drone=dict(mass_kg=mass, size_m=size, size_limit_m=drone_size_limit_m(mass), battery_wh=wh, voltage_v=volts,
                            rotor_count=4, rotor_radius_m=rotor, guard_hole_m=.012, guard='enclosed above, below and around every rotor',
                            thrust_max_n=thrust, speed_reference_mps=speed, climb_mps=2.0, tilt_limit_rad=.6, impact_integrity=integrity,
                            radius_m=round(size/2, 4), nav_light='7 x XL-3528SURUBC, 22 mm circle, top centre', emergency_stop_rc=True,
                            hover_efficiency=.48, avionics_w=2.0),
                 source_status='chosen hangar and micro-drone parameters; impact thresholds are simulation assumptions (manual: TBD)')
        finish(d, designs)


def make_designs_2027(designs):
    heavy(designs); infantry(designs); sentry(designs); aerial(designs)
    return designs
