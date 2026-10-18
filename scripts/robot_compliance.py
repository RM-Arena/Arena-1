"""Per-season inspection of robot designs against each construction manual.

A model may enter a season's lineup only in that season's role for it and only if it
passes that season's construction limits. Checks use the machine-readable limits in
config/rules.json (2026: rulebook.construction; 2027: rulebook_2027.construction); items
that need physical testing (gloss, EMI, edge radii, drop tests) are not claimed.
"""
import math
import hashlib
import json

# These are the existing generated models, not a default for arbitrary new hardware.
# New models must supply their own inspection evidence before being marked legal.
BUILTIN_2027_GROUND_MODELS = {3, 4, 7, 301, 302, 303, 304, 305, 2711, 2712, 2713, 2731, 2732, 2771, 2772}
ARMOR_GEOMETRY_FIELDS = ('chassis_size_m', 'ground_clearance_m', 'armor_count', 'armor_height_m',
    'armor_width_m', 'armor_center_z_m', 'armor_side_center_z_m', 'armor_inset_m',
    'armor_mount_offset_m', 'armor_hit_face_offset_m', 'armor_normal_to_up_deg',
    'chassis_type', 'hip_height_m', 'suspension_static_compression_m')

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
                       extended_alternative=dict(front_min_m=[-.9, -.9, 0], front_max_m=[0, .9, 1.25],
                                                 rear_min_m=[0, -.9, 0], rear_max_m=[.9, .9, 1.25], pages=[27, 28]),
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
    return _vector(size, 3) and _vector(limit, 3) and all(0 <= a <= b+1e-9 for a, b in zip(size, limit))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _vector(value, length):
    return isinstance(value, (list, tuple)) and len(value) == length and all(_number(v) for v in value)


def _armor_fingerprint(design):
    data = {k: design.get(k) for k in ARMOR_GEOMETRY_FIELDS}
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def armor_mount_geometry(design):
    """The four actual plate centres/normals used by physics.rs and robot_specs.py.

    Coordinates are in the chassis frame. This is an analytic geometry check, not
    a claim to have performed a physical inspection or checked every moving part.
    """
    angle = math.radians(design['armor_normal_to_up_deg'])
    mounts = []
    for face in range(4):
        yaw = face*math.pi/2
        normal = [math.cos(yaw)*math.sin(angle), math.sin(yaw)*math.sin(angle), math.cos(angle)]
        distance = design['chassis_size_m'][face % 2]/2-design['armor_inset_m']+design.get('armor_mount_offset_m', 0)
        center = [distance*math.cos(yaw), distance*math.sin(yaw),
                  design.get('armor_side_center_z_m', design['armor_center_z_m']) if face % 2 else design['armor_center_z_m']]
        center = [v+n*design.get('armor_hit_face_offset_m', 0) for v, n in zip(center, normal)]
        mounts.append(dict(center_m=center, normal=normal, edge_tilt_deg=0,
                           unobstructed_cone_deg=dict(lower=105, upper=120, left=145, right=145)))
    return mounts


def add_builtin_construction_inspections(designs):
    """Populate explicit inspection records for the existing generated models.

    Clearance angles record the intended built-in mounting layout. The checker
    additionally checks the actual plate/chassis geometry and any supplied solid
    obstruction boxes; full articulated-mesh cone sweeps remain outside its scope.
    Never call this to approve a user-supplied or newly introduced model.
    """
    for key, design in designs.items():
        if int(key) not in BUILTIN_2027_GROUND_MODELS:
            continue
        design['construction_inspection'] = dict(
            source='built-in cardinal armor mounts; analytic chassis geometry; declared clearance cones',
            armor_geometry_sha256=_armor_fingerprint(design), armor_mounts=armor_mount_geometry(design),
            obstruction_boxes_m=[])
    for key in ('2711', '2712', '2713'):
        if key in designs:
            designs[key]['launcher_module_battery_wh'] = 0
    return designs


def extended_envelope_2027(design, limit, size=None):
    """Accept S68 requirement 1, or both fixed-origin inspections in requirement 2.

    Requirement 2 uses two directional inspections: negative-X/lateral extension
    against the front edge, and positive-X/lateral extension against the rear edge.
    Each origin is fixed throughout that test (its Y coordinate may be chosen).
    Bounds must cover the declared/measured size; a bare pass flag is insufficient.
    """
    size = design.get('extended_m') if size is None else size
    if _fits(size, limit['extended_m']):
        return True
    evidence = design.get('heavy_extended_inspection')
    alternative = limit.get('extended_alternative')
    if not isinstance(evidence, dict) or not isinstance(alternative, dict) or evidence.get('coverage') != 'directional_reachable_states':
        return False
    if not _vector(size, 3):
        return False
    for side in ('front', 'rear'):
        origin = evidence.get(side+'_origin_m')
        edge_x = design['chassis_size_m'][0]/2*(1 if side == 'front' else -1)
        if not _vector(origin, 3) or abs(origin[0]-edge_x) > 1e-9 or abs(origin[2]) > 1e-9:
            return False
        bounds = evidence.get(side+'_bounds_m')
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2 or not all(_vector(v, 3) for v in bounds):
            return False
        low, high = bounds
        if any(a > b or a < m-1e-9 or b > n+1e-9 for a, b, m, n in zip(low, high, alternative[side+'_min_m'], alternative[side+'_max_m'])):
            return False
        if any(b-a+1e-9 < s for a, b, s in zip(low, high, size)):
            return False
    return True


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


def _ray_box(origin, direction, bounds):
    """Positive ray/closed AABB intersection, for definite frontal obstructions."""
    near, far = 0.0, float('inf')
    for p, v, low, high in zip(origin, direction, *bounds):
        if abs(v) < 1e-10:
            if p < low-1e-9 or p > high+1e-9:
                return False
        else:
            a, b = sorted(((low-p)/v, (high-p)/v))
            near, far = max(near, a), min(far, b)
    return far >= near and far > 1e-6


def _chassis_obstruction_box(design):
    """Solid inner core of the actual Rapier chassis collider (excludes bevel).

    physics.rs uses narrower colliders to keep the exposed plate faces clear;
    using the whole chassis dimension box would falsely fill wheel/armor cutouts.
    """
    length, width, height = design['chassis_size_m']
    legged = design['chassis_type'] == 'wheel_legged'
    z = design['hip_height_m'] if legged else design['ground_clearance_m']+design['suspension_static_compression_m']+.012+height/2
    x, y = length*(.45 if legged else .42), width*.42
    return [[-x, -y, z-height/2], [x, y, z+height/2]]


def _armor_2027_issues(design, armor):
    issues = _armor_issues(design, armor)
    record = design.get('construction_inspection')
    if not isinstance(record, dict) or not isinstance(record.get('armor_mounts'), list) or len(record['armor_mounts']) != 4:
        return issues+[_issue('armor_inspection', '缺少四块装甲的几何与遮挡检录记录', 'Missing geometry and clearance inspection for all four armor modules')]
    if not _number(design.get('armor_normal_to_up_deg')):
        return issues+[_issue('armor_angle', '缺少有效装甲安装角度', 'Missing valid armor mounting angle')]
    if abs(design['armor_normal_to_up_deg']-armor['normal_to_up_deg']) > 1e-6:
        issues.append(_issue('armor_angle', '装甲受击面法向须与向上轴成75°', 'Armor face normals must be 75 degrees from the upward axis'))
    if record.get('armor_geometry_sha256') != _armor_fingerprint(design):
        issues.append(_issue('armor_inspection', '装甲几何已改变，需重新检录', 'Armor geometry changed after its recorded inspection'))
    actual = armor_mount_geometry(design)
    boxes = record.get('obstruction_boxes_m')
    if not isinstance(boxes, list) or any(not isinstance(b, (list, tuple)) or len(b) != 2 or not all(_vector(v, 3) for v in b)
            or any(a > z for a, z in zip(*b)) for b in boxes):
        return issues+[_issue('armor_inspection', '装甲遮挡几何记录无效或缺失', 'Missing or invalid armor obstruction geometry')]
    boxes = [_chassis_obstruction_box(design), *boxes]
    restricted = 0
    for face, mount in enumerate(record['armor_mounts']):
        if not isinstance(mount, dict) or not _vector(mount.get('center_m'), 3) or not _vector(mount.get('normal'), 3):
            issues.append(_issue('armor_inspection', '装甲安装位置或法向记录不完整', 'Incomplete armor centre or normal record'))
            continue
        center, normal = mount['center_m'], mount['normal']
        length = math.sqrt(sum(v*v for v in normal))
        if abs(length-1) > 1e-6:
            issues.append(_issue('armor_angle', '装甲法向须为单位向量', 'Armor normals must be unit vectors'))
            continue
        up_angle = math.degrees(math.acos(max(-1, min(1, normal[2]))))
        expected_yaw = face*math.pi/2
        yaw = math.atan2(normal[1], normal[0])
        error = abs((yaw-expected_yaw+math.pi) % (2*math.pi)-math.pi)
        if abs(up_angle-armor['normal_to_up_deg']) > 1e-6 or not _number(mount.get('edge_tilt_deg')) or abs(mount['edge_tilt_deg']) >= 5:
            issues.append(_issue('armor_angle', '装甲法向或水平边缘角度不符', 'Armor normal or horizontal edge angle is outside the mounting limits'))
        if math.degrees(error) > armor['axis_alignment_tolerance_deg']+1e-9:
            issues.append(_issue('armor_alignment', '装甲方向与对应坐标轴误差超过5°', 'Armor direction differs from its corresponding chassis axis by over 5 degrees'))
        cross_offset = center[1] if face % 2 == 0 else center[0]
        if abs(cross_offset) > armor['xy_center_offset_max_m']+1e-9:
            issues.append(_issue('armor_offset', '装甲几何中心横向偏移超过50mm', 'Armor centre cross-axis offset exceeds 50 mm'))
        if any(abs(a-b) > 1e-6 for a, b in zip(center, actual[face]['center_m'])) or any(abs(a-b) > 1e-6 for a, b in zip(normal, actual[face]['normal'])):
            issues.append(_issue('armor_geometry', '检录装甲位置或法向与实际模型几何不一致', 'Recorded armor centre or normal differs from the model geometry'))
        geometry_center, geometry_normal = actual[face]['center_m'], actual[face]['normal']
        radial = geometry_center[0]*math.cos(expected_yaw)+geometry_center[1]*math.sin(expected_yaw)
        if radial <= 0:
            issues.append(_issue('armor_geometry', '装甲被埋入底盘或放置在错误的一侧', 'Armor is buried in the chassis or placed on the wrong side'))
        clear = mount.get('unobstructed_cone_deg')
        if not isinstance(clear, dict) or any(not _number(clear.get(k)) for k in ('lower', 'upper', 'left', 'right')):
            issues.append(_issue('armor_clearance', '缺少装甲四边禁止遮挡角度记录', 'Missing armor edge clearance angles'))
        elif clear['lower'] < 105 or clear['upper'] < 120 or clear['left'] < 145 or clear['right'] < 145:
            # S130 permits one heavy plate's upper/side obstruction, but only
            # beyond the stated distances on that armor plane.
            conditional = mount.get('conditional_obstruction_m', {})
            valid = design['role'] == 'heavy' and clear['lower'] >= 105 and all(
                clear[k] >= minimum or _number(conditional.get(k)) and conditional[k] > distance
                for k, minimum, distance in [('upper', 120, .15), ('left', 145, .17), ('right', 145, .17)])
            restricted += 1
            if not valid:
                issues.append(_issue('armor_clearance', '装甲禁止遮挡角度或重装有条件遮挡距离不符', 'Armor clearance cone or the heavy conditional obstruction distance is insufficient'))
        # Nine positive-normal rays detect a definite physical obstruction in
        # front of the actual plate. Cone edge evidence above covers the wider
        # forbidden zones; this does not substitute for a full mesh pose sweep.
        horizontal = [-math.sin(expected_yaw), math.cos(expected_yaw), 0]
        vertical = [-math.cos(expected_yaw)*normal[2], -math.sin(expected_yaw)*normal[2], math.sin(math.radians(up_angle))]
        blocked = any(_ray_box([p+h*x+v*y for p, h, v in zip(geometry_center, horizontal, vertical)], geometry_normal, box)
                      for x in (-design['armor_width_m']/2, 0, design['armor_width_m']/2)
                      for y in (-design['armor_height_m']/2, 0, design['armor_height_m']/2) for box in boxes)
        if blocked:
            issues.append(_issue('armor_obstructed', '装甲受击面前方存在实体结构遮挡', 'Solid model geometry obstructs the front of an armor face'))
    if restricted > (1 if design['role'] == 'heavy' else 0):
        issues.append(_issue('armor_clearance', '至多一块重装装甲可采用有条件遮挡', 'At most one heavy armor module may use conditional obstruction'))
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
               'engineer': ('2027赛季英雄与工程合并为重装机器人，工程型号缺少模块化42mm发射机构接口', '2027 merges hero and engineer; engineer models lack the modular 42 mm launcher')}.get(role, ('2027赛季没有此机器人兵种', 'Unknown robot role for 2027'))
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
        if not _number(design.get('voltage_v')) or not 0 < design['voltage_v'] <= h['voltage_v']:
            issues.append(_issue('hangar_power', '机库工作电压须有记录且不超过30V', 'Hangar voltage must be specified and at most 30 V'))
        if launcher_of(design) != 'none' or drone.get('launcher', 'none') != 'none':
            issues.append(_issue('launcher', '空中系统不能安装发射机构', 'An aerial system cannot carry a launcher'))
        return issues
    limit = env[role]
    mass = design['mass_kg']
    if mass > limit['mass_including_battery_and_referee_kg']+1e-9:
        issues.append(_issue('mass', f"整机{mass}kg超过2027限重{limit['mass_including_battery_and_referee_kg']}kg（含电池与裁判系统）",
                             f"Robot {mass} kg exceeds the 2027 {limit['mass_including_battery_and_referee_kg']} kg limit (battery and referee included)"))
    if design['battery_wh'] > limit['battery_wh']+1e-9 or design['voltage_v'] > limit['voltage_v']+1e-9:
        issues.append(_issue('power', '电池容量或电压超出2027限制', 'Battery capacity or voltage exceeds the 2027 limit'))
    extended_fits = extended_envelope_2027(design, limit) if role == 'heavy' else _fits(design['extended_m'], limit['extended_m'])
    if not _fits(design['stowed_m'], limit['stowed_m']) or not extended_fits:
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
        if not _number(design.get('launcher_module_voltage_v')) or not 0 < design['launcher_module_voltage_v'] <= module['voltage_v']:
            issues.append(_issue('launcher_power', '42mm模块工作电压须有记录且不超过140V', 'The 42 mm module voltage must be specified and at most 140 V'))
        if not _number(design.get('launcher_module_battery_wh')) or design['launcher_module_battery_wh'] != 0:
            issues.append(_issue('launcher_battery', '42mm模块不得安装独立电池，需明确记录为0Wh', 'The 42 mm module must explicitly have no independent battery (0 Wh)'))
        if design.get('arm_count', 0) < 1:
            issues.append(_issue('arm', '重装机器人须能在资源站抓取能量单元', 'The heavy robot must grip energy units at the resource station'))
    elif launcher != 'one_17mm':
        issues.append(_issue('launcher', '须安装1个17mm发射机构', 'One 17 mm launcher is required'))
    if role != 'heavy' and design.get('referee_mass_kg', 0) < limit['referee_kg']-1e-9:
        issues.append(_issue('referee', '裁判系统套件不完整（2027需含定位模块、荧光充能装置等，重3.25kg）',
                             'Incomplete referee kit (2027 needs the positioning module and UV charger, 3.25 kg)'))
    issues += _armor_2027_issues(design, limits['armor'])
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
