"""Symmetric robot hardware designs within the supplied construction limits.

Compliance bounds come from the manual. Chosen hardware and material values
are design inputs, not invented rulebook speed, friction or mass requirements.
"""
import copy
import math
try:
    from .manual_sources import source_metadata
except ImportError:
    from manual_sources import source_metadata


def construction_limits():
    return dict(source=source_metadata("construction"),
      envelope=dict(hero=dict(mass_excluding_referee_kg=35,referee_kg=4.21,battery_wh=300,voltage_v=30,stowed_m=[.8,.8,.8],extended_m=[1.2,1.2,1.2],launcher='one_42mm',pages=[29,30]),
                    engineer=dict(mass_excluding_referee_kg=35,referee_kg=3.04,battery_wh=300,voltage_v=30,stowed_m=[.6,.6,.6],extended_m=[1.2,1.2,1.1],launcher='none',pages=[30,31,32]),
                    infantry=dict(mass_excluding_referee_kg=25,referee_kg=3.25,battery_wh=300,voltage_v=30,stowed_m=[.6,.6,.6],extended_m=[.8,.8,.8],launcher='one_17mm',pages=[32,33,34]),
                    aerial=dict(mass_excluding_referee_kg=13,referee_kg=.66,battery_wh=900,voltage_v=52,stowed_m=[1.4,1.4,1.1],extended_m=[1.7,1.7,.8],mast_excluded_from_envelope=True,launcher='one_17mm',laser_module_removed_by_user=True,pages=[34,35])),
      energy=dict(electric_ground_drive=True,supercap_allowed=['hero','infantry'],supercap_groups_max=1,supercap_nominal_max_j=2000,supercap_measured_max_j=2200,supercap_module_current_max_a=15,other_chassis_capacitance_max_f=.01,pages=[12,13,95]),
      armor=dict(count=4,normal_to_up_deg=75,axis_alignment_tolerance_deg=5,xy_center_offset_max_m=.05,lower_edge_height_max_m=.4,lower_edge_height_difference_max_m=.1,rigid_mount_test_force_n=60,rigid_mount_deflection_max_deg=2.5,bumper_required=True,unobstructed_cone_deg=dict(lower=105,upper=120,left_right=145),pages=[68,69,72,73]),
      charging=dict(max_transfer_w=120,max_face_area_m2=.01,max_gap_m=.03,transmitter_max_size_m=[.5,.5,.3],receivers_allowed=['hero','infantry'],receiver_max_count=1,frequency_hz=[100000,148500],pages=[24,25]),
      aerial=dict(full_rotor_enclosure=True,guard_test_force_n=20,guard_collision_test_mps=[1.1,1.3],guard_blocks_42mm=True,recommended_max_mesh_area_m2=.0009,mast_above_rotor_plane_m=[.30,.40],backup_safety_rope=True,nav_light_length_min_m=1.5,nav_lights_upward_only=True,flight_test_min_s=10,indicator_count_max=6,pages=[34,35,36,37]),
      weapon=dict(friction_wheel_electric=True,min_17mm_hardware_rate_hz=10,min_17mm_test_speed_mps=20,one_launcher_per_robot=True,engineer_has_no_launcher=True,muzzle_sensor_after_acceleration=True,pages=[19,23,30,31,33,34,81,82]),
      appearance=dict(gloss_max_gs=30,protected_wiring=True,no_sharp_edges=True,armor_unmodified=True,team_color_on_shell_or_rulebook_modules_only=True,pages=[17,18,19,66]))


# Wheeled ground robots: chassis underside 100 mm above the ground at static ride, so the
# base plate passes the 70 mm road humps (figure 4-34).
CLEARANCE = .10
# Suspension: hub 90 mm below its mount at full extension (rest) plus 60 mm droop; the body
# rides 18 mm into it as before, but on a softer spring (35 mm sag, longer free length) so
# the wheels follow the humps while the chassis stays nearly level.
SUSPENSION = dict(rest=.09, droop=.06, ride=.018, sag=.035)
SUSPENSION_DAMPING = .8  # times sqrt(k m/4): about 0.4 of critical damping


def suspension(mass, aerial=False):
    if aerial:  # aerial landing gear and wheel-legged placeholders; unchanged
        k = mass*9.81/(4*.018)
        return dict(suspension_rest_m=.09, suspension_travel_m=.045, suspension_static_compression_m=.018,
                    suspension_stiffness_npm=round(k, 3), suspension_damping_nspm=round((mass/4*k)**.5*1.25, 3))
    s = SUSPENSION; k = mass*9.81/(4*s['sag'])
    return dict(suspension_rest_m=s['rest'], suspension_travel_m=s['droop'], suspension_static_compression_m=s['ride'],
                suspension_sag_m=s['sag'], suspension_free_length_m=round(s['rest']-s['ride']+s['sag'], 4),
                suspension_stiffness_npm=round(k, 3), suspension_damping_nspm=round((mass/4*k)**.5*SUSPENSION_DAMPING, 3))
# Wheel-legged robots: a compliant leg (static sag) and its damping, so the body glides over
# the road humps while the legs fold under it.
LEG_SAG = .07
LEG_DAMPING = (220, 300)


def make_designs():
    rows=[
      (1,'hero','H42 重型英雄','远程支援',29.8,4.21,[.74,.70,.76],[1.08,1.08,1.12],[.64,.60,.21],.235,.53,.53,.09,3.6,1.10,240,24,'ranged','hp','cooling',.60,.38,.32),
      (2,'engineer','E35 搬运工程','载重与机械臂',31.6,3.04,[.59,.59,.59],[1.18,1.18,1.06],[.55,.55,.18],.205,.41,.44,.085,3.1,1.05,280,24,'ranged','hp','cooling',0,0,.275),
      (3,'infantry','W3 双轮足步兵','越障与机动',18.4,3.25,[.50,.52,.58],[.56,.56,.76],[.42,.36,.12],.28,0,.44,.10,4.6,1.0,200,24,'ranged','power','cooling',.47,.22,.28),
      (4,'infantry','I4 突击步兵','短时爆发',23.4,3.25,[.59,.59,.59],[.75,.75,.74],[.54,.54,.17],.215,.43,.43,.080,4.2,.95,240,24,'ranged','power','burst',.48,.280,.285),
      (7,'infantry','I7 稳健步兵','生存与持续压制',24.1,3.25,[.59,.59,.57],[.74,.74,.70],[.55,.55,.105],.175,.41,.45,.085,3.8,1.22,260,24,'ranged','hp','cooling',.45,.280,.175),
      (6,'aerial','A13 护罩四旋翼','空中支援',10.8,.66,[1.22,1.22,.52],[1.22,1.22,.52],[.38,.30,.16],.215,.66,.66,.235,3.0,0,720,44.4,'ranged','hp','cooling',.14,.260,0),
    ]
    result={}
    for slot,role,name,focus,bare,ref,stowed,extended,chassis,com,wb,track,wheel,maxspeed,mu,wh,volts,hero,chassis_profile,weapon,muzzle,reach,armor in rows:
      mass=bare+ref
      # The chassis box is thinner by the rise of its underside (from 35 mm), keeping the deck.
      clearance=CLEARANCE if role!='aerial' and slot!=3 else .035
      chassis=[chassis[0],chassis[1],round(chassis[2]-(clearance-.035),3)]
      # Axles 2.5 (hero) or 1.5 hump pitches apart: one axle rolls down a hump while the
      # other climbs, so a power-limited chassis keeps moving over the bumps.
      if role in ('hero','engineer','infantry') and slot!=3:wb=.60 if role=='hero' else .36
      if role=='hero':stowed=[max(stowed[0],round(wb+2*wheel+.02,3)),*stowed[1:]]
      # Ground robots were rebuilt for the road bumps (clearance, suspension, wheelbase).
      version='v2' if role=='aerial' else 'v4'
      result[str(slot)]=dict(slot=slot,role=role,name=name,focus=focus,revision='construction-2026-v2' if role=='aerial' else 'construction-2026-v3',
        asset=f'/assets/robot-{slot}-spec2026{version}.glb',
        bare_mass_kg=bare,referee_mass_kg=ref,mass_kg=round(mass,3),battery_wh=wh,voltage_v=volts,stowed_m=stowed,extended_m=extended,
        chassis_size_m=chassis,ground_clearance_m=clearance,com_m=[0,0,com],wheelbase_m=wb,track_m=track,wheel_radius_m=wheel,wheel_width_m=.045 if slot==3 else .055,
        chassis_type='quadrotor' if role=='aerial' else 'mecanum',speed_reference_mps=maxspeed,tire_friction=mu,lateral_friction_ratio=.72 if slot==3 else .82,
        drive_efficiency=.82 if slot==3 else .76 if role=='aerial' else .85,rolling_resistance=.018 if slot==3 else .025,drag_area_m2=.11 if slot==3 else .18,
        motor_force_max_n=110 if role=='hero' else 125 if role=='engineer' else 95 if slot==7 else 100,brake_force_max_n=130 if slot==7 else 100,
        yaw_torque_max_nm=7 if role in ('hero','engineer') else 5,velocity_gain_per_s=4,yaw_gain_per_s=5,
        **suspension(mass, role=='aerial' or slot==3),
        inertia_kgm2=[round(mass*(chassis[1]**2+chassis[2]**2)/12,5),round(mass*(chassis[0]**2+chassis[2]**2)/12,5),round(mass*(chassis[0]**2+chassis[1]**2)/12,5)],
        supercap_nominal_j=1800 if role in ('hero','infantry') else 0,supercap_max_current_a=12 if role in ('hero','infantry') else 0,
        charge_receiver=role in ('hero','infantry'),coil_size_m=[.10,.10],coil_offset_m=[chassis[0]/2,0,.16],
        hero_profile=hero,chassis_profile=chassis_profile,weapon_profile=weapon,
        armor_count=0 if role=='aerial' else 4,armor_width_m=.23 if role=='hero' else .135,armor_height_m=.125,
        armor_center_z_m=armor,armor_inset_m=.032,armor_normal_to_up_deg=75,
        armor_mount_offset_m=.03 if slot==3 else 0.0,armor_hit_face_offset_m=.011,
        turret_yaw_rate_rad_s=5.0 if role=='hero' else 6.5 if slot==3 else 5.5,turret_pitch_rate_rad_s=2.5,
        pitch_limits_rad=[-.2617993878,.7853981634],muzzle_z_m=muzzle,muzzle_reach_m=reach,
        trigger_interval_s=.2 if role=='hero' else .05,finish_gloss_gs=20,contact_restitution=.08,
        source_status='chosen engineering parameters within construction limits; not rulebook speed or tire specification')
      if role=='aerial':
        result[str(slot)].update(rotor_radius_m=.235,guard_radius_m=.275,guard_height_m=.16,guard_mesh_pitch_m=.025,rotor_plane_z_m=.30,
          mast_top_z_m=.65,mast_offset_above_rotor_m=.35,nav_light_length_m=1.76,nav_light_lux_at_40mm=500,backup_rope_diameter_m=.004,
          thrust_max_n=230,flight_tilt_limit_rad=.261799,flight_power_max_w=2600)
        result[str(slot)]['inertia_kgm2']=[.32,.32,.48]
      if slot==3:
        # Two-wheel-legged balancing chassis: five-bar legs per side, hub motors at the
        # feet. The body balances actively; leg joints are not chassis power (S, p.49).
        result['3'].update(chassis_type='wheel_legged',leg_type='five_bar',wheel_width_m=.05,lateral_friction_ratio=1.0,drive_efficiency=.80,
          rolling_resistance=.015,drag_area_m2=.12,motor_force_max_n=170,brake_force_max_n=120,yaw_torque_max_nm=9,
          inertia_kgm2=[.40,.46,.62],hip_height_m=.30,leg_min_m=.12,leg_max_m=.34,leg_nominal_m=.20+LEG_SAG-.025,leg_speed_mps=1.2,
          leg_stiffness_npm=round((18.4+3.25)*9.81/(2*LEG_SAG),1),leg_damping_nspm=LEG_DAMPING[0],leg_passive_ratio=.2,
          jump_duration_s=.16,jump_thrust_gain=1.7,jump_cooldown_s=.8,jump_tuck_s=.35,
          balance_kp_nm_per_rad=180,balance_kd_nms_per_rad=19,balance_torque_max_nm=45,air_torque_max_nm=5,
          stand_torque_max_nm=80,coast_friction=.10,leg_holding_power_w=18,
          suspension_rest_m=.20,suspension_travel_m=.16,
          source_status='chosen wheel-legged parameters within the infantry envelope; balance and leg control are simulation choices, not rulebook')
      elif role!='aerial':
        result[str(slot)]['coast_friction']=.22
      if role=='engineer':
        # Two-stage lift mast at the chassis centre, telescoping boom and a three-axis
        # wrist. Joint order: slew, lift, reach, wrist yaw, wrist pitch (+ = tool down),
        # wrist roll, gripper opening. Lengths in metres from the robot ground origin.
        result[str(slot)]['arm']=dict(
          joints=['slew','lift','reach','wrist_yaw','wrist_pitch','wrist_roll','grip'],
          base_m=[0,0,.245],shoulder_rest_z_m=.30,tool_length_m=.15,jaw_travel_m=.032,
          limits=[[-2.97,2.97],[0,.50],[.22,.70],[-1.75,1.75],[-1.66,1.75],[-3.14159,3.14159],[0,1]],
          rates=[2.4,.6,.7,3.0,3.0,4.0,4.0],stowed=[0,0,.22,0,-1.5708,0,0],
          boom_tail_m=.12,mast_half_size_m=[.05,.05,.16],
          grip_force_max_n=320,grasp_tolerance_m=.05,rescue_upright_cos=.93,
          source_status='chosen lift/boom/wrist hardware inside the 600 mm stowed and 1200x1200x1100 mm extended envelopes')
    add_variants(result)
    english={101:'H-S Swerve Hero',102:'H-O Omni Assault Hero',103:'H-W Wheel-legged Hero',201:'E-D Dual-arm Engineer',202:'E-S Swerve Rescue Engineer',203:'E-O Omni Assembly Engineer',301:'I-T Transforming Tunnel Infantry',302:'I-S Swerve Assault Infantry',303:'I-O Light Omni Infantry',304:'I-W Long-stroke Wheel-legged Infantry',305:'I-L Serial-leg Self-righting Infantry',601:'A-Q Compact Quadrotor',602:'A-H Endurance Hexarotor'}
    focus_english={101:'High-traction swerve support platform',102:'Light omnidirectional chassis and melee firepower',103:'Wheel-legged jumps and fly-slopes; no deployment hardware',201:'Two independent manipulators for pickup and rescue',202:'High-traction swerve drive and single-arm rescue',203:'Light omni drive and faster manipulator joints',301:'Telescoping turret for low side tunnels',302:'High-traction swerve drive and burst launcher',303:'Light omni drive and sustained cooling',304:'Longer legs and stronger jumps; smaller battery',305:'Full-turn hip joints flip it back upright after a fall',601:'Compact guards, faster flight and smaller battery',602:'Six enclosed rotors, larger battery and slower flight'}
    for design in result.values():
        if design['slot'] in english:design['name_en']=english[design['slot']];design['focus_en']=focus_english[design['slot']]
        design.setdefault('deploy_allowed',design['role']=='hero')
        design.setdefault('transform_allowed',False)
        design.setdefault('arm_count',1 if design['role']=='engineer' else 0)
        design.setdefault('rotor_count',4 if design['role']=='aerial' else 0)
        design['capabilities']={'deployment':design['deploy_allowed'],'transformation':design['transform_allowed'],
            'jump':design['chassis_type']=='wheel_legged','self_righting':design.get('leg_type')=='serial','tunnel':design.get('folded_height_m',1)>0 and design.get('folded_height_m',1)<=.25,
            'arms':design['arm_count'],'drive':design['chassis_type']}
    return result


def add_variants(designs):
    def variant(model,base,name,focus,**changes):
        ground=designs[str(base)]['role']!='aerial'
        d=copy.deepcopy(designs[str(base)]);d.update(changes,slot=model,name=name,focus=focus,
            revision='construction-2026-model-v2' if ground else 'construction-2026-model-v1',
            asset=f'/assets/robot-{model}-spec2026{"v4" if ground else "v3"}.glb',base_model=base)
        d['mass_kg']=round(d['bare_mass_kg']+d['referee_mass_kg'],3)
        size=d['chassis_size_m'];mass=d['mass_kg']
        d['inertia_kgm2']=[round(mass*(size[1]**2+size[2]**2)/12,5),round(mass*(size[0]**2+size[2]**2)/12,5),round(mass*(size[0]**2+size[1]**2)/12,5)]
        if d['chassis_type'] in ('quadrotor','wheel_legged'):
            d['suspension_stiffness_npm']=round(mass*9.81/(4*d['suspension_static_compression_m']),3)
            d['suspension_damping_nspm']=round((mass/4*d['suspension_stiffness_npm'])**.5*1.25,3)
            for key in ('suspension_free_length_m','suspension_sag_m'):d.pop(key,None)
            d['ground_clearance_m']=.035
        else:d.update(suspension(mass))
        designs[str(model)]=d;return d
    variant(101,1,'H-S 舵轮支援英雄','转向轮组、稳态精射',chassis_type='swerve',steer_rate_rad_s=4.5,
        bare_mass_kg=32.1,speed_reference_mps=3.8,tire_friction=1.2,lateral_friction_ratio=1.0,drive_efficiency=.84)
    variant(102,1,'H-O 全向突击英雄','轻量全向底盘、近战火力',chassis_type='omni',bare_mass_kg=26.8,
        speed_reference_mps=4.1,tire_friction=.9,lateral_friction_ratio=.72,hero_profile='melee',yaw_torque_max_nm=10)
    leg=variant(103,1,'H-W 双轮足英雄','飞坡与跨越、无部署机构',chassis_type='wheel_legged',deploy_allowed=False,
        bare_mass_kg=28.9,hero_profile='melee',stowed_m=[.74,.74,.78],extended_m=[1.1,1.1,1.18],
        chassis_size_m=[.52,.46,.16],com_m=[0,0,.30],wheelbase_m=0,track_m=.58,wheel_radius_m=.105,
        muzzle_z_m=.54,muzzle_reach_m=.32,armor_center_z_m=.30,armor_mount_offset_m=.03,speed_reference_mps=4.4)
    for key in ['leg_type','hip_height_m','leg_min_m','leg_max_m','leg_nominal_m','leg_speed_mps','leg_stiffness_npm','leg_damping_nspm',
        'leg_passive_ratio','jump_duration_s','jump_thrust_gain','jump_cooldown_s','jump_tuck_s','balance_kp_nm_per_rad',
        'balance_kd_nms_per_rad','balance_torque_max_nm','air_torque_max_nm','stand_torque_max_nm','leg_holding_power_w']:
        leg[key]=designs['3'][key]
    leg.update(inertia_kgm2=[.66,.78,1.02],motor_force_max_n=220,brake_force_max_n=155,yaw_torque_max_nm=12,
        hip_height_m=.33,leg_min_m=.13,leg_max_m=.37,leg_nominal_m=.23+LEG_SAG-.025,leg_stiffness_npm=leg['mass_kg']*9.81/(2*LEG_SAG),
        leg_damping_nspm=LEG_DAMPING[1],balance_kp_nm_per_rad=260,balance_kd_nms_per_rad=28,balance_torque_max_nm=72,
        stand_torque_max_nm=115,air_torque_max_nm=8,jump_thrust_gain=2.4,jump_duration_s=.20,leg_upper_m=.15,leg_lower_m=.31,suspension_rest_m=.23,suspension_travel_m=.18,
        drive_efficiency=.84,rolling_resistance=.015,drag_area_m2=.14,lateral_friction_ratio=1.0,coast_friction=.1)
    dual=variant(201,2,'E-D 双臂工程','两只独立机械臂、持物与救援配合',bare_mass_kg=33.5,arm_count=2,
        stowed_m=[.60,.60,.60],extended_m=[1.20,1.20,1.08],speed_reference_mps=2.6)
    dual['arm']['base_m']=[0,-.085,.245];dual['arm']['limits'][2]=[.18,.62]
    dual['arm'].update(workspace_half_m=.54,moving_mass_kg=1.8)
    dual['arm2']=copy.deepcopy(dual['arm']);dual['arm2']['base_m']=[0,.085,.245]
    variant(202,2,'E-S 舵轮救援工程','高牵引力、快速转向与扶正',chassis_type='swerve',steer_rate_rad_s=5.5,
        bare_mass_kg=29.4,speed_reference_mps=3.5,motor_force_max_n=150,tire_friction=1.35,lateral_friction_ratio=1.0)
    variant(203,2,'E-O 全向装配工程','轻量全向底盘、快速腕部',chassis_type='omni',bare_mass_kg=27.6,
        speed_reference_mps=3.8,yaw_torque_max_nm=10,tire_friction=.95)
    designs['203']['arm']['rates']=[3.2,.75,.85,4.0,4.0,5.0,5.0]
    fold=variant(301,7,'I-T 变形隧道步兵','折叠炮塔、穿过两侧低矮隧道',bare_mass_kg=20.6,
        chassis_size_m=[.46,.44,round(.09-(CLEARANCE-.035),3)],stowed_m=[.56,.55,.56],extended_m=[.70,.70,.68],
        com_m=[0,0,.13],wheelbase_m=.36,track_m=.36,wheel_radius_m=.076,wheel_width_m=.045,
        muzzle_z_m=.40,muzzle_reach_m=.23,armor_center_z_m=.15,speed_reference_mps=3.8,
        transform_allowed=True,folded_muzzle_z_m=.145,folded_height_m=.235,transform_time_s=.8)
    fold['coil_offset_m']=[.23,0,.13]
    variant(302,4,'I-S 舵轮重装步兵','高抓地力、定向加速与爆发',chassis_type='swerve',steer_rate_rad_s=5,
        bare_mass_kg=24.3,speed_reference_mps=4.4,tire_friction=1.25,lateral_friction_ratio=1.0,drive_efficiency=.84)
    variant(303,7,'I-O 全向轻步兵','轻量全向、快速横移与持续射击',chassis_type='omni',bare_mass_kg=18.8,
        speed_reference_mps=5.1,tire_friction=.9,lateral_friction_ratio=.75,chassis_profile='power',
        motor_force_max_n=105,yaw_torque_max_nm=8,battery_wh=220)
    athletic=variant(304,3,'I-W 长行程轮足步兵','更高跃升、较慢转向与较小续航',bare_mass_kg=20.9,battery_wh=180,
        muzzle_z_m=.435,leg_max_m=.38,leg_upper_m=.15,leg_lower_m=.33,leg_speed_mps=1.45,jump_thrust_gain=1.9,jump_cooldown_s=1.15,
        speed_reference_mps=4.1,yaw_torque_max_nm=7,extended_m=[.64,.64,.80])
    athletic['leg_stiffness_npm']=athletic['mass_kg']*9.81/(2*LEG_SAG)
    # Serial legs: hip joint motor, thigh, knee joint (belt-driven from a coaxial motor at
    # the hip), shank and hub wheel. The hip joints have no end stops, so after a fall the
    # legs swing round to the floor and the hip motors turn the body back over the axle.
    # The hip joints sit on the axle line beside the body, so the side armor hangs below them
    # (front/rear plates stay above the charging receiver) and the wheels run outboard.
    serial=variant(305,3,'I-L 串联腿步兵','髋关节整周旋转、翻倒后自行翻正',bare_mass_kg=19.8,
        leg_type='serial',leg_upper_m=.17,leg_lower_m=.20,leg_max_m=.35,leg_speed_mps=1.3,
        jump_thrust_gain=1.8,jump_cooldown_s=.95,speed_reference_mps=4.4,track_m=.50,armor_side_center_z_m=.215,
        stowed_m=[.50,.56,.58],extended_m=[.74,.60,.80],
        hip_speed_rad_s=8.0,self_right_delay_s=.4,self_right_torque_max_nm=70,self_right_roll_torque_max_nm=60)
    serial['leg_stiffness_npm']=serial['mass_kg']*9.81/(2*LEG_SAG)
    variant(601,6,'A-Q 轻量四旋翼','紧凑护罩、高机动与较小电池',bare_mass_kg=8.7,battery_wh=540,
        rotor_radius_m=.185,guard_radius_m=.23,rotor_count=4,stowed_m=[1.18,1.18,.66],extended_m=[1.18,1.18,.66],
        speed_reference_mps=3.8,thrust_max_n=205,flight_power_max_w=2250,nav_light_length_m=1.58)
    variant(602,6,'A-H 六旋翼支援机','六旋翼稳定平台、长续航与较慢机动',bare_mass_kg=12.3,battery_wh=850,
        rotor_count=6,rotor_radius_m=.16,guard_radius_m=.205,stowed_m=[1.38,1.38,.66],extended_m=[1.38,1.38,.66],
        speed_reference_mps=2.7,thrust_max_n=255,flight_power_max_w=2900,nav_light_length_m=1.86)
    designs['601']['inertia_kgm2']=[.24,.24,.36]
    designs['602']['inertia_kgm2']=[.48,.48,.68]


def validate_designs(designs,limits):
    for design in designs.values():
      limit=limits['envelope'][design['role']]
      assert design['bare_mass_kg']<=limit['mass_excluding_referee_kg']
      assert design['battery_wh']<=limit['battery_wh'] and design['voltage_v']<=limit['voltage_v']
      assert all(a<=b for a,b in zip(design['stowed_m'],limit['stowed_m']))
      assert all(a<=b for a,b in zip(design['extended_m'],limit['extended_m']))
      assert design['supercap_nominal_j']<=2000
      if design['role']=='aerial':
        assert .30<=design['mast_offset_above_rotor_m']<=.40
        assert design['guard_mesh_pitch_m']<.042 and design['nav_light_length_m']>1.5
      else:
        lower=design['armor_center_z_m']-.0625
        assert 0<lower<=.4 and design['armor_count']==4
        side=design.get('armor_side_center_z_m',design['armor_center_z_m'])-.0625
        assert 0<side<=.4 and abs(side-lower)<=limits['armor']['lower_edge_height_difference_max_m']
    assert {'1','2','3','4','6','7'}<=set(designs)
