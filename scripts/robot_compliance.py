"""Per-season inspection of robot designs against each construction manual.

A model may enter a season's lineup only in that season's role for it and only if it
passes that season's construction limits. Checks use the machine-readable limits in
config/rules.json (2026: official.construction; 2027: official_2027.construction); items
that need physical testing (gloss, EMI, edge radii, drop tests) are not claimed.
"""
import math

ROLE_LABELS = {'hero': ('英雄', 'hero'), 'engineer': ('工程', 'engineer'), 'infantry': ('步兵', 'infantry'),
               'aerial': ('空中', 'aerial'), 'heavy': ('重装', 'heavy'), 'sentry': ('哨兵', 'sentry')}


def construction_2027(source):
    """Table 2-1, 2-5..2-10 and chapter 3 of the 2027 construction manual (V1.0.0)."""
    ground_armor = dict(count=4, normal_to_up_deg=75, axis_alignment_tolerance_deg=5, xy_center_offset_max_m=.05,
                        lower_edge_height_max_m=.4, lower_edge_height_difference_max_m=.1, rigid_mount_test_force_n=60,
                        rigid_mount_deflection_max_deg=2.5, bumper_required=True, module='small',
                        unobstructed_cone_deg=dict(lower=105, upper=120, left_right=145), pages=[61, 62, 63, 66, 67])
    return dict(source=source,
        envelope=dict(
            heavy=dict(mass_including_battery_and_referee_kg=36, mass_with_launcher_module_kg=41, battery_wh=300, voltage_v=30,
                       stowed_m=[.6, .6, .6], stowed_excludes_launcher_module=True, extended_m=[1.2, 1.2, 1.1],
                       extended_alternative='requirement 2: 900 mm deep x 1800 wide x 1250 high, front or rear (table 2-5)',
                       launcher='modular_42mm', must_grip_energy_units=True,
                       launcher_module=dict(mass_kg=6, stowed_m=[.4, .4, .4], voltage_v=140, no_battery=True, capacitance_max_mf=80, pages=[29]),
                       referee=['small_armor_x4', 'video_transmitter', 'field_interaction', 'positioning', 'main_controller', 'power_management', 'light_bar'],
                       pages=[26, 27, 28, 29]),
            infantry=dict(mass_including_battery_and_referee_kg=28, referee_kg=3.25, battery_wh=300, voltage_v=30,
                          stowed_m=[.6, .6, .6], extended_m=[.8, .8, .8], launcher='one_17mm',
                          referee=['small_armor_x4', 'speed_17mm', 'video_transmitter', 'field_interaction', 'positioning',
                                   'main_controller', 'power_management', 'light_bar', 'uv_charger', 'supercap_manager'], pages=[29, 30]),
            sentry=dict(mass_including_battery_and_referee_kg=28, referee_kg=3.25, battery_wh=300, voltage_v=30,
                        stowed_m=[.6, .6, .6], extended_m=[.8, .8, .8], launcher='one_17mm', remote_controllers=1,
                        referee=['small_armor_x4', 'speed_17mm', 'field_interaction', 'positioning', 'main_controller',
                                 'power_management', 'light_bar', 'uv_charger', 'supercap_manager', 'video_transmitter'], pages=[30, 31]),
            aerial=dict(drone_count_max=4, drone_mass_max_kg=.249, drone_size_formula_m='y=(0.3225-x)/0.001225 mm for x in [0.15,0.249]; 141 mm below 0.15 kg',
                        drone_battery_wh=4, drone_voltage_v=30, drone_launcher='none', guard_hole_max_m=.017, hover_min_s=10,
                        nav_light_leds=7, nav_light_circle_max_m=.024, emergency_stop_rc=True,
                        hangar=dict(battery_wh=300, voltage_v=30, stowed_m=[.3, .3, .2], extended_m=[.6, .3, .4], capacity=4,
                                    referee=['main_controller', 'power_management', 'video_transmitter']), pages=[31, 32, 33, 34, 35])),
        energy=dict(electric_ground_drive=True, supercap_allowed=['heavy', 'infantry', 'sentry'], supercap_groups_max=1,
                    supercap_nominal_max_j=2000, supercap_measured_max_j=2200, other_chassis_capacitance_max_f=.01,
                    batteries=dict(ground='DJI or regular dry cells only', aerial='DJI, dry cells or regular lithium'), pages=[10, 11]),
        armor=ground_armor,
        weapon=dict(friction_or_compressed_air=True, gas_acceleration_max_m=.2, min_17mm_hardware_rate_hz=10, min_17mm_test_speed_mps=20,
                    stable_burst=dict(shots_17mm=10, shots_42mm=5), speed_module_required=True, one_launcher_per_robot=True, pages=[17, 19]),
        appearance=dict(gloss_max_gs=30, edge_radius_min_m_below_400mm=.01, protected_wiring=True, no_sharp_edges=True,
                        armor_unmodified=True, team_color_areas_max=4, pages=[15, 16]),
        safety=dict(rotor_full_enclosure=True, guard_hole_max_m=.017, drop_test_m=.5, auto_stop_on_signal_loss=True, pages=[33]),
        not_checked=['gloss', 'edge radii', 'EMI', 'drop tests', 'rigid-mount force tests', 'referee wiring'])


def _fits(size, limit):
    return all(a <= b+1e-9 for a, b in zip(size, limit))


def _issue(code, zh, en):
    return dict(code=code, zh=zh, en=en)


def _armor_issues(design, armor):
    issues = []
    if design.get('armor_count') != armor['count']:
        issues.append(_issue('armor', '需安装4块装甲模块', 'Four armor modules are required'))
        return issues
    half = design.get('armor_height_m', .125)/2
    front = design['armor_center_z_m']-half
    side = design.get('armor_side_center_z_m', design['armor_center_z_m'])-half
    if not (0 < front <= armor['lower_edge_height_max_m'] and 0 < side <= armor['lower_edge_height_max_m']):
        issues.append(_issue('armor_height', '装甲下边缘须高于地面且不超过400mm', 'Armor lower edges must be above ground and at most 400 mm'))
    if abs(front-side) > armor['lower_edge_height_difference_max_m']+1e-9:
        issues.append(_issue('armor_height', '任意两块装甲下边缘高度差不得超过100mm', 'Armor lower edges must be within 100 mm of each other'))
    return issues


def launcher_of(design):
    if 'launcher' in design:
        return design['launcher']
    return {'hero': 'fixed_42mm', 'engineer': 'none', 'infantry': 'one_17mm', 'aerial': 'one_17mm'}.get(design['role'], 'none')


def check_2026(design, limits):
    role = design['role']
    if role not in limits['envelope']:
        zh, en = ROLE_LABELS.get(role, (role, role))
        why = {'heavy': ('2026版本没有重装机器人（英雄与工程分立）', 'The 2026 lineup has separate hero and engineer robots, no heavy robot'),
               'sentry': ('2026版本未启用哨兵，7号按步兵规则出场', 'The 2026 adaptation fields slot 7 as an infantry robot, not a sentry')}.get(role, (f'2026版本没有{zh}', f'No {en} role in 2026'))
        return [_issue('role', *why)]
    limit = limits['envelope'][role]
    issues = []
    if design['bare_mass_kg'] > limit['mass_excluding_referee_kg']+1e-9:
        issues.append(_issue('mass', f"本体{design['bare_mass_kg']}kg超过2026限重{limit['mass_excluding_referee_kg']}kg（不含裁判系统）",
                             f"Body {design['bare_mass_kg']} kg exceeds the 2026 {limit['mass_excluding_referee_kg']} kg limit"))
    if design['battery_wh'] > limit['battery_wh']+1e-9 or design['voltage_v'] > limit['voltage_v']+1e-9:
        issues.append(_issue('power', '电池容量或电压超出2026限制', 'Battery capacity or voltage exceeds the 2026 limit'))
    if not _fits(design['stowed_m'], limit['stowed_m']) or not _fits(design['extended_m'], limit['extended_m']):
        issues.append(_issue('envelope', '收纳或伸展尺寸超出2026限制', 'Stowed or extended size exceeds the 2026 limit'))
    if design.get('supercap_nominal_j', 0) > limits['energy']['supercap_nominal_max_j']:
        issues.append(_issue('supercap', '超级电容超过2000J', 'Supercapacitor exceeds 2000 J'))
    launcher = launcher_of(design)
    wanted = {'hero': 'fixed_42mm', 'engineer': 'none', 'infantry': 'one_17mm', 'aerial': 'one_17mm'}[role]
    if launcher != wanted:
        issues.append(_issue('launcher', {'aerial': '2026空中机器人须搭载17mm发射机构', 'hero': '2026英雄须固定安装42mm发射机构'}.get(role, '发射机构类型不符'),
                             {'aerial': 'A 2026 aerial robot needs a 17 mm launcher', 'hero': 'A 2026 hero needs a fixed 42 mm launcher'}.get(role, 'Launcher type does not match')))
    if role == 'aerial':
        if not (.30 <= design.get('mast_offset_above_rotor_m', 0) <= .40) or design.get('nav_light_length_m', 0) <= 1.5:
            issues.append(_issue('aerial', '缺少2026要求的保护杆与1.5m以上航行灯', 'Missing the 2026 safety mast and 1.5 m navigation lights'))
    else:
        issues += _armor_issues(design, limits['armor'])
    return issues


def check_2027(design, limits):
    role = design['role']
    env = limits['envelope']
    if role not in env:
        why = {'hero': ('2027赛季英雄与工程合并为重装机器人，英雄型号不能出场', '2027 merges hero and engineer into the heavy robot; hero models cannot enter'),
               'engineer': ('2027赛季英雄与工程合并为重装机器人，工程型号缺少模块化42mm发射机构接口', '2027 merges hero and engineer; engineer models lack the modular 42 mm launcher')}[role]
        return [_issue('role', *why)]
    issues = []
    if role == 'aerial':
        a = env['aerial']
        drone = design.get('drone')
        if not drone:
            return [_issue('aerial_system', f"2027空中系统为机库加≤0.249kg全自动空中机器人；本型号{design['mass_kg']}kg、带发射机构",
                           f"A 2027 aerial system is a hangar plus ≤0.249 kg autonomous drones; this model weighs {design['mass_kg']} kg and carries a launcher")]
        if design.get('drone_count', 0) > a['drone_count_max'] or design.get('drone_count', 0) < 1:
            issues.append(_issue('drones', '机库至多装载4架空中机器人', 'A hangar carries at most four aerial robots'))
        mass = drone['mass_kg']; limit = .141 if mass < .15 else (.3225-mass)/.001225/1000
        if mass > a['drone_mass_max_kg']+1e-9:
            issues.append(_issue('mass', f'空中机器人{mass}kg超过0.249kg', f'Aerial robot {mass} kg exceeds 0.249 kg'))
        elif drone['size_m'] > round(limit*1000)/1000+1e-9:
            issues.append(_issue('envelope', f"{mass}kg空中机器人最大尺寸{round(limit*1000)}mm，设计为{round(drone['size_m']*1000)}mm",
                                 f"A {mass} kg aerial robot may span {round(limit*1000)} mm; this one spans {round(drone['size_m']*1000)} mm"))
        if drone['battery_wh'] > a['drone_battery_wh']+1e-9 or drone['voltage_v'] > a['drone_voltage_v']:
            issues.append(_issue('power', '空中机器人电池超过4Wh或30V', 'Aerial robot battery exceeds 4 Wh or 30 V'))
        if drone.get('guard_hole_m', 1) >= a['guard_hole_max_m']:
            issues.append(_issue('guard', '桨保孔径须小于17mm', 'Rotor guard openings must be under 17 mm'))
        h = a['hangar']
        if not _fits(design['stowed_m'], h['stowed_m']) or not _fits(design['extended_m'], h['extended_m']) or design['battery_wh'] > h['battery_wh']:
            issues.append(_issue('hangar', '机库尺寸或电池超出限制', 'Hangar size or battery exceeds the limit'))
        return issues
    limit = env[role]
    mass = design['mass_kg']
    if mass > limit['mass_including_battery_and_referee_kg']+1e-9:
        issues.append(_issue('mass', f"整机{mass}kg超过2027限重{limit['mass_including_battery_and_referee_kg']}kg（含电池与裁判系统）",
                             f"Robot {mass} kg exceeds the 2027 {limit['mass_including_battery_and_referee_kg']} kg limit (battery and referee included)"))
    if design['battery_wh'] > limit['battery_wh']+1e-9 or design['voltage_v'] > limit['voltage_v']+1e-9:
        issues.append(_issue('power', '电池容量或电压超出2027限制', 'Battery capacity or voltage exceeds the 2027 limit'))
    if not _fits(design['stowed_m'], limit['stowed_m']) or not _fits(design['extended_m'], limit['extended_m']):
        issues.append(_issue('envelope', '收纳或伸展尺寸超出2027限制', 'Stowed or extended size exceeds the 2027 limit'))
    if design.get('supercap_nominal_j', 0) > limits['energy']['supercap_nominal_max_j']:
        issues.append(_issue('supercap', '超级电容超过2000J', 'Supercapacitor exceeds 2000 J'))
    launcher = launcher_of(design)
    if role == 'heavy':
        module = limit['launcher_module']
        if launcher != 'modular_42mm':
            issues.append(_issue('launcher', '重装机器人须使用可在工作台安装的模块化42mm发射机构', 'The heavy robot needs a modular 42 mm launcher fitted at the workbench'))
        elif design.get('launcher_module_kg', 99) > module['mass_kg'] or not _fits(design.get('launcher_module_stowed_m', [1, 1, 1]), module['stowed_m']):
            issues.append(_issue('launcher', '模块化42mm发射机构超过6kg或400mm收纳尺寸', 'The launcher module exceeds 6 kg or its 400 mm stowed size'))
        elif mass+design['launcher_module_kg'] > limit['mass_with_launcher_module_kg']+1e-9:
            issues.append(_issue('mass', '装上发射模块后超过41kg', 'Over 41 kg with the launcher module fitted'))
        if design.get('arm_count', 0) < 1:
            issues.append(_issue('arm', '重装机器人须能在资源站抓取能量单元', 'The heavy robot must grip energy units at the resource station'))
    elif launcher != 'one_17mm':
        issues.append(_issue('launcher', '须安装1个17mm发射机构', 'One 17 mm launcher is required'))
    if role != 'heavy' and design.get('referee_mass_kg', 0) < limit['referee_kg']-1e-9:
        issues.append(_issue('referee', '裁判系统套件不完整（2027需含定位模块、荧光充能装置等，重3.25kg）',
                             'Incomplete referee kit (2027 needs the positioning module and UV charger, 3.25 kg)'))
    issues += _armor_issues(design, limits['armor'])
    if design.get('armor_width_m', .135) > .14:
        issues.append(_issue('armor', '2027地面机器人统一使用小装甲模块', '2027 ground robots use small armor modules'))
    return issues


CHECKS = {'2026': check_2026, '2027': check_2027}


def season_compliance(designs, limits_by_season):
    result = {}
    for key, design in designs.items():
        result[key] = {}
        for season, check in CHECKS.items():
            issues = check(design, limits_by_season[season])
            result[key][season] = dict(legal=not issues, role=design['role'], issues=issues)
    return result
