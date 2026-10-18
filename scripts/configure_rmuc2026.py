"""Transcribe the user-provided 2026 V1.0.0 manual into auditable config.

Normative rule numbers and explicit simulation hardware assumptions are kept
separate. This script does not fetch a newer season manual.
"""
import json
import math
from pathlib import Path
from exchange_difficulties import ASSEMBLY_DIFFICULTIES
from manual_sources import source_metadata

ROOT = Path(__file__).resolve().parents[1]

def tiers(hp,power,heat,cooling):
    return [{'level':i+1,'hp':h,'power_w':p,'max_heat':q,'cooling':c} for i,(h,p,q,c) in enumerate(zip(hp,power,heat,cooling))]

rulebook = {
    'source': source_metadata("rules"),
    'terrain_geometry': {'central_ramp_deg':10.5,'assembly_ramp_deg':10,'road_ramp_deg':11,'fly_ramp_deg':17,'fortress_ramp_deg':20,'trapezoid_ramps_deg':[43,23],'trapezoid_height_m_range':[.2,.4],'source_pages':[52,53,54,55,60,61]},
    'match': {'duration_s':420,'field_length_m':28,'field_width_m':15,'fence_height_m':2.4,'prep_s':180,'self_check_s':15,'countdown_s':5,'source_pages':[22,32,113,119]},
    'adaptations': {'excluded_systems':['dart','radar'],'sentry_uses_infantry_rules':True,'team_size':6,'slots':[1,2,3,4,6,7],'former_sentry_ammo_bonus_removed':True,'radar_debuff_and_aircraft_laser_removed':True},
    'damage': {'17mm':20,'42mm':200,'collision_sensor':2,'normal_speed_min_17_mps':12,'normal_speed_min_42_mps':10,'armor_interval_s':.05,'armor_interval_42_max_s':.2,'weakspot_width_m':.01,'weakspot_height_m':.01,'weakspot_attack_multiplier':1.5,'hero_idle_42_mask_s':4,'hero_dead_42_mask_s':3,'rounding':'half_up_integer','source_pages':[66,67,92]},
    'projectiles': {'17mm':{'diameter_m':.0168,'diameter_tolerance_m':.0002,'mass_kg':.0032,'mass_tolerance_kg':.0001,'muzzle_limit_mps':25,'heat_per_shot':10},'42mm':{'diameter_m':.0425,'diameter_tolerance_m':.0005,'mass_kg':.0445,'mass_tolerance_kg':.0005,'muzzle_limit_mps':12,'deployed_muzzle_limit_mps':16.5,'heat_per_shot':100},'source_pages':[24,26,28,64,68]},
    'heat': {'settlement_hz':10,'lock_when_above_limit':True,'unlock_heat':0,'permanent_extra_17':100,'permanent_extra_42':200,'permanent_boundary':'at_or_above_Q2_per_figure_5_1','source_pages':[68,69]},
    'overspeed': {'17mm':[{'excess_from':0,'excess_to':5,'lock_s':15},{'excess_from':5,'excess_to':10,'lock_s':20},{'excess_from':10,'permanent':True}], '42mm':[{'ratio_from':1,'ratio_to':1.1,'lock_s':15},{'ratio_from':1.1,'ratio_to':1.2,'lock_s':20},{'speed_above_mps':18,'permanent':True}], 'source_page':67,'ambiguous_42_gap_policy':'reject_invalid_speed_requests; do_not_invent_gap_penalty'},
    'power': {'settlement_hz':10,'buffer_capacity_j':60,'cutoff_s':5,'initial_energy_j':20000,'max_energy_j':40000,'energy_saving_power_w':35,'enhanced_threshold_j':25000,'enhanced_multiplier':1.25,'absolute_cap_w':200,'charge_energy_multiplier':8,'wireless_supply_max_w':200,'source_pages':[50,69,70,112]},
    'heal': {'disengage_s':6,'supply_ratio_per_s':.1,'late_start_s':240,'late_disengaged_supply_ratio_per_s':.25,'remote_delay_s':6,'remote_ratio':.6,'source_pages':[18,74]},
    'respawn': {'progress_base':10,'elapsed_divisor':10,'instant_purchase_progress_penalty':20,'normal_progress_per_s':1,'supply_or_base_below_2000_progress_per_s':4,'base_low_hp_strict_threshold':2000,'normal_hp_ratio':.1,'normal_invulnerability_s':30,'instant_hp_ratio':1,'instant_invulnerability_s':3,'instant_power_multiplier':2,'instant_power_cap_w':200,'instant_power_duration_s':4,'weak_blocks_fire_and_buffs':True,'source_page':75},
    'economy': {'initial_coins':400,'initial_coin_time_s':1,'periodic_schedule':[{'elapsed_s':61,'coins':50},{'elapsed_s':121,'coins':50},{'elapsed_s':181,'coins':50},{'elapsed_s':241,'coins':50},{'elapsed_s':301,'coins':50},{'elapsed_s':361,'coins':150}],
        'document_rating_bonus':{'S':50,'A':25,'B':0,'C':-25,'D':-50},'technical_rating_bonus':{'S':150,'A':75,'B':0,'C':-25,'D':-50},
        'ammo':{'17mm':{'local_batch':10,'local_cost':10,'remote_batch':100,'remote_cost':150,'team_purchase_cap':1000},'42mm':{'local_batch':1,'local_cost':10,'remote_batch':10,'remote_cost':150,'team_purchase_cap':100}},
        'remote_delay_s':6,'remote_heal_cost':'50 + ceil(elapsed_seconds/60*20)','instant_respawn_cost':'ceil(elapsed_seconds/60)*80 + robot_level*20','air_support_coin_per_s':1,'source_pages':[76,77,78,79]},
    'initial_ammo': {'hero':0,'engineer':0,'infantry':0,'aerial':750,'source_pages':[24,26,28,78]},
    'experience': {'thresholds':[0,550,1100,1650,2200,2750,3300,3850,4400,5000],'initial_cap':5,'cap_after_assembly_2':7,'cap_after_assembly_3':10,'shot_xp_17':1,'shot_xp_42':10,'robot_damage_xp_per_hp':4,'outpost_damage_xp_per_hp':2,'base_damage_xp_per_hp':.5,'kill_base_xp':50,'kill_level_gap_factor':.2,'terrain_first_xp':300,'deployed_damage_extra_xp':100,'stop_gain_at_cap':True,'source_pages':[83,84,85,86,87]},
    'profiles': {
      'defaults':{'hero':'ranged','infantry_chassis':'hp','infantry_weapon':'cooling'},
      'hero':{'melee':tiers([200,225,250,275,300,325,350,375,400,450],[70,75,80,85,90,95,100,105,110,120],[140,150,160,170,180,190,200,210,220,240],[12,14,16,18,20,22,24,26,28,30]),'ranged':tiers([150,165,180,195,210,225,240,255,270,300],[50,55,60,65,70,75,80,85,90,100],[100,102,104,106,108,110,115,120,125,130],[20,23,26,29,32,35,38,41,44,50])},
      'infantry_chassis':{'power':[{'level':i+1,'hp':h,'power_w':p} for i,(h,p) in enumerate(zip([150,175,200,225,250,275,300,325,350,400],[60,65,70,75,80,85,90,95,100,100]))],'hp':[{'level':i+1,'hp':h,'power_w':p} for i,(h,p) in enumerate(zip([200,225,250,275,300,325,350,375,400,400],[45,50,55,60,65,70,75,80,90,100]))]},
      'infantry_weapon':{'burst':[{'level':i+1,'max_heat':h,'cooling':c} for i,(h,c) in enumerate(zip([170,180,190,200,210,220,230,240,250,260],[5,7,9,11,12,13,14,16,18,20]))],'cooling':[{'level':i+1,'max_heat':h,'cooling':c} for i,(h,c) in enumerate(zip([40,48,56,64,72,80,88,96,114,120],[12,14,16,18,20,22,24,26,28,30]))]},
      'aerial':[{'level':i+1,'max_heat':h,'cooling':c} for i,(h,c) in enumerate(zip([100,110,120,130,140,150,160,170,180,200],[20,30,40,50,60,70,80,90,100,120]))],
      'engineer':{'hp':250,'power_w':120,'can_fire':False,'uses_experience':False},'locked_after_start':True,'level_up_adds_hp_delta':True,'source_pages':[25,26,87,88,89,90,91,92]},
    'structures': {'base_hp':5000,'outpost_hp':1500,'base_invulnerable_while_outpost_alive':True,'base_opens_at_hp_lte':2000,'rebuild_loss_step_hp':1000,'rebuild_hp':750,'rebuild_hold_hero_infantry_s':10,'rebuild_hold_engineer_s':5,'rebuild_disabled_at_s':300,'outpost_rotor_speed_rad_s':.8*3.141592653589793,'outpost_acceleration_s':5,'outpost_stop_after_s':180,'outpost_return_initial_s':10,'source_pages':[92,93,94]},
    'buffs': {'release_delay_s':2,'same_kind_combine':'maximum','base_defense':.5,'central_defense':.25,'trapezoid_defense':.5,'outpost_defense':.25,'engineer_initial_defense':.5,'engineer_initial_defense_until_s':180,'assembly_invulnerability_budget_s':180,'resource_engineer_invulnerable':True,
       'crossings':{'road':{'window_s':3,'defense':.25,'duration_s':5,'cooldown_s':15,'low_to_high':True},'highland':{'window_s':5,'defense':.5,'duration_s':30,'low_to_high':True},'fly':{'window_s':10,'defense':.25,'duration_s':30},'tunnel':{'window_s':3,'cooling_multiplier':2,'duration_s':120}},'repeat_defensive_crossing_defense':.5,
       'fortress':{'active_after_own_outpost_first_death':True,'own_defense':.5,'cooling_bonus':'min(75,floor(base_missing_hp/40))','reserve_ammo':'min(500,100+2*floor(base_missing_hp/15))','enemy_activation_after_s':180,'enemy_requires_own_outpost_destroyed':True,'enemy_vulnerability':1,'enemy_occupation_to_open_base_s':20,'enemy_timer_retention_s':3},'source_pages':[99,101,102,103,104,106]},
    'aerial': {'initial_support_s':30,'support_increment_s':20,'support_schedule_s':[60,120,180,240,300,360],'initial_allowed_ammo':750,'can_receive_ammo':False,'damageable':False,'alive_iff_support_active':True,'tether_length_m':2.4,'wire_stop_from_own_edge_m':14,'lowest_point_min_altitude_m':1.5,'speed_module_max_altitude_m':2.4,'cannot_fire_on_pad':True,'source_pages':[28,61,62,106,129]},
    'deployment': {'profile':'ranged','transition_s':2,'own_half_only':True,'chassis_disabled':True,'own_fpv_disabled':True,'defense':.25,'muzzle_limit_mps':16.5,'base_attack_multiplier':1.5,'source_pages':[105,106]},
    'assembly': {'unlock_times_s':[0,60,120,180],'required_previous_difficulty':True,'income_period_s':10,'first_income_per_period':[50,25,25,50],'repeat_income_per_period':[5,10,15,0],'team_defense_after_3':.25,'team_defense_after_4':.5,'base_heal_after_4':2000,'overflow_as_virtual_shield':True,'difficulty_4_once':True,'difficulty_4_time_limit_s':45,'difficulty_4_retry_lock_s':90,'difficulty_4_secondary_insert_window_s':3,'other_active_core_buffer_s':15,'interrupted_level_4_failure_permanent_lock':True,'interrupted_level_4_failure_income_penalty':25,
       'insert_depth_m':.1,'translation_m':.1,'allowed_rotation_deg':90,'rotation_tolerance_deg':5,'initial_core_pose':[-.2,.2,.8,0,90,0],'pose_ranges':{'1':{'x':[-.1,0],'y':[-.1,.1],'z':[.8,.8],'theta':[0,0],'phi':[90,90],'alpha':[0,0]},'2-4':{'x':[-.1,0],'y':[-.1,.1],'z':[.7,.9],'theta':[-90,90],'phi':[0,90],'alpha':[-45,45]}},'source_pages':[79,80,82,83,84,85]},
    'rune': {'arms':5,'arm_radius_m':.7,'target_radius_m':.15,'center_above_mount_m':2.3,'small_until_s':180,'small_chances_s':[0,90],'large_chances_s':[180,255,330],'activation_timeout_s':20,'hit_timeout_s':2.5,'large_secondary_hit_s':1,'small_speed_rad_s':3.141592653589793/3,'large_a':[.780,1.045],'large_omega':[1.884,2],'large_b':'2.090-a','small_defense':.25,'small_duration_s':45,'small_xp_multiplier':2,'small_team_extra_xp_cap':1200,'large_shared_xp':750,'large_bands':[{'min':1,'max':3,'attack':1.5,'defense':.25,'cooling':1},{'min':3,'max':7,'attack':1.5,'defense':.25,'cooling':2},{'min':7,'max':8,'attack':2,'defense':.25,'cooling':2},{'min':8,'max':9,'attack':2,'defense':.25,'cooling':3},{'min':9,'max':10,'attack':3,'defense':.5,'cooling':5}],'duration_by_hits':{'5':30,'6':35,'7':40,'8':45,'9':50,'10':60},'source_pages':[56,57,94,95,96,97,98,99]},
    'winner': {'early_finish':'base_destroyed_only','timeout_order':['base_hp','outpost_never_destroyed','outpost_hp_if_both_never_destroyed','team_attack_damage','alive_ground_robot_hp_sum'],'all_robots_dead_is_not_victory':True,'source_page':113},
    'hardware_fault_rules':{'main_ground_offline_hp_fraction_per_s':.05,'armor_capacitor_offline_hp_per_module_per_500ms':4,'module_check_hz':2,'muzzle_sensor_offline_locks_weapon':True,'default_virtual_hardware_online':True,'source_pages':[70,71,72,73]},
    'document_ambiguities':[{'pages':[67],'issue':'42mm overspeed final row contains a 17mm label and leaves an interval ambiguous','resolution':'public actions enforce legal muzzle speed; retain verbatim numeric boundaries in config; no invented sanction'},{'pages':[68],'issue':'text uses Q1>Q2 while flowchart uses Q1>=Q2','resolution':'use figure 5-1 >= boundary'},{'pages':[104],'issue':'fortress example 150 cooling contradicts stated cap75','resolution':'use normative min(75,floor(delta/40))'}]
}

sim = {'note':'Only these robot hardware, sensor and geometric assumptions are not specified by this PDF.',
       'robot_radius_m':.28,'muzzle_height_m':.55,'aerial_muzzle_offset_m':.25,'aerial_initial_altitude_m':0,'aerial_flight_altitude_m':1.9,'gravity_mps2':9.81,'tether_wire_height_m':3.9,
       'max_move_speed_mps':{'hero':3.2,'engineer':3.0,'infantry':4.0,'aerial':3.0},'acceleration_mps2':{'hero':6,'engineer':6,'infantry':8,'aerial':5},'vision_range_m':{'hero':18,'engineer':15,'infantry':18,'aerial':24},'turret_yaw_rate_rad_s':6,'turret_pitch_rate_rad_s':2,'infantry_trigger_interval_s':.05,'hero_trigger_interval_s':.2,
       'wireless_input_w':100,'max_carried_units':2,'resource_stock':'unlimited_virtual_dispenser','arm_insert_speed_mps':.2,'arm_translate_speed_mps':.2,'arm_rotate_speed_deg_s':90,
       'manual_judging':'Illegal target and zone commands prevented; subjective human penalties and real hardware failures are not randomly simulated.',
       'map_fidelity':'28x15 and published dimensions enforced; unlabelled module footprints and interaction regions traced/approximated from figures4-4/4-5. CAD and robot construction manual not supplied.',
       'trapezoid_elevation_m':.3,'central_elevation_m':.4,'core_move_delay_s':2.0,'floor_slope_deg':1.5,'armor_model':'four rectangular robot armor faces; base/outpost armor discs, not full CAD collision meshes'}

from chapter4_layout import CHARGER, CHARGER_NORMAL, make_arena, mirrored
arena = make_arena()
sim['map_fidelity'] = 'Chapter 4 dimensioned module footprints and figure4-5 placement; unlabelled joints reconstructed from the plan, not rulebook CAD.'
rulebook['penalties'] = {'offender_hp_ratio': 0.15, 'teammate_hp_ratio': 0.05, 'repeat_window_s': 30, 'offender_fpv_s': 5, 'teammate_fpv_s': 2, 'engineer_yellow_limit': 2, 'other_yellow_limit': 3, 'yellow_min_hp': 1, 'source_pages': [122, 123], 'card_authority': 'trusted_referee_only; subjective intent is not randomly judged'}
rulebook['adaptations']['all_runes_variable_speed'] = True
sim.update({
    'arm_insert_speed_mps': .1,
    'arm_translate_speed_mps': .15,
    'arm_rotate_speed_deg_s': 120,
    'assembly_repeat_reset_s': 20.,
    'assembly_difficulties': ASSEMBLY_DIFFICULTIES,
    'projectile_spread_half_angle_deg': {'17mm': 1.8, '42mm': 1.3},
    'projectile_color': '#66ee55',
    'rune_motor': {
        'profile': 'seeded_smooth_aperiodic',
        'small_amplitude_rad_s': .32,
        'secondary_weight': .28,
        'secondary_frequency_ratio': .6180339887498948,
        'mode_transition_s': 3.,
        'note': "Both small and large runes use smoothly varying shaft speed throughout the match; both faces share the same motor. This overrides the manual's constant small-rune speed.",
    },
})
sim['structure_geometry'] = {'base_lower_center_above_pedestal_m': 0.287, 'base_lower_radius_m': 0.34, 'base_lower_width_m': 0.23, 'base_top_center_above_pedestal_m': 1.043, 'outpost_middle_center_m': [1.116, 1.216, 1.316], 'outpost_top_center_m': 1.5, 'armor_height_m': 0.125, 'base_open_duration_s': 1.5, 'note': 'Finite proxies reconstructed from manual figures 4-10/11/32; unlabelled armor centers and motion are simulation assumptions, not rulebook CAD.'}
sim['pickup_phases'] = {'approach_hold_s': 0.2, 'grip_hold_s': 0.35, 'lift_hold_s': 0.3, 'stow_hold_s': 0.4, 'position_tolerance_m': 0.045, 'note': 'Requires actual arm contact, closing, lift and storage. Keep pick_unit true; leaving, destruction, weakness or manual arm control cancels.'}
sim['central_cover_height_above_deck_m'] = .15
sim['overheat_vision_range_multiplier'] = .35
sim['ground_camera_fov_deg'] = {'horizontal':100.0,'vertical':70.0,'note':'Ground FPV follows the physical muzzle direction and chassis pose. Own robot state and referee telemetry remain unrestricted; aerial vision keeps its existing coverage.'}
sim['central_elevation_m'] = .4
sim.pop('trapezoid_elevation_m',None)
sim['trapezoid_elevations_m'] = [.2,.4]
rulebook['terrain_geometry']['chapter4_dimensions'] = {'base_x_m':2.407,'fortress_x_m':6.6,'outpost_x_blue_m':17.008,'outpost_y_blue_m':3.643,'central_width_m':7.7,'central_depth_m':10.82,'fortress_width_m':2.24,'fortress_depth_m':1.939,'fortress_height_m':.15,'helipad_width_m':2.2,'helipad_height_m':.9,'trapezoid_segments_m':[6.707,3.798],'trapezoid_depth_m':4.38,'highway_width_segments_m':[1.561,2.09],'tunnel_width_m':.8,'tunnel_clearance_m':.25,'fly_gap_m':.65,'fly_run_m':1.145,'fly_width_m':1.143,'road_bump_height_m':.07,'road_bump_pitch_m':.24,'assembly_plinth_height_m':.1,'source_pages':[35,43,52,53,54,55,59,60,61]}

specs={}
for role,hp,power,heat,cooling,ammo,damage,muzzle in [('hero',150,50,100,20,0,200,12),('engineer',250,120,0,0,0,0,0),('infantry',200,45,40,12,0,20,25),('aerial',0,0,100,20,750,20,25)]:
    specs[role]={'hp':hp,'power_w':power,'speed':sim['max_move_speed_mps'][role],'acceleration':sim['acceleration_mps2'][role],'damage':damage,'cooldown':sim['hero_trigger_interval_s'] if role=='hero' else sim['infantry_trigger_interval_s'],'ammo':ammo,'vision':sim['vision_range_m'][role],'range':40,'armor':0,'heat_per_shot':100 if role=='hero' else 0 if role=='engineer' else 10,'max_heat':heat,'cooling':cooling,'projectile_speed':muzzle,'asset':'/assets/robot-'+role+'.glb'}
from robot_designs import construction_limits, make_designs, validate_designs
construction=construction_limits();designs=make_designs();validate_designs(designs,construction)
rulebook['construction']=construction
rulebook['power']['wireless_transfer_max_w']=120
sim['physics_engine']='rapier3d-f64 0.26.1 enhanced-determinism; 120Hz rigid bodies and ray suspension'
sim['physics_dt_s']=1/120
sim['robot_hardware']='18 selectable symmetric hardware designs; default six-model lineup preserved; construction bounds enforced'
sim['hardware_authority']='robot_designs is authoritative; family specs speed/acceleration are retained only for old SDK compatibility'
sim['armor_model']='finite rectangular robot/base/outpost armor planes with separate solid body and opening-cover occlusion; approximate structure geometry is public'
sim['air_density_kgpm3']=1.225
sim['sphere_drag_coefficient']=.47
for old in ['robot_radius_m','muzzle_height_m','aerial_muzzle_offset_m','max_move_speed_mps','acceleration_mps2','turret_yaw_rate_rad_s','turret_pitch_rate_rad_s']:
    sim.pop(old,None)
arena['charging_docks']={'red':{'transmitter':[*CHARGER,.16],'normal':CHARGER_NORMAL},
                         'blue':{'transmitter':[*mirrored(CHARGER),.16],'normal':[-v for v in CHARGER_NORMAL]}}
rules={'version':'rmuc-2026-v1.0.0-arena-v3','dt':.05,'policy_interval':2,'rulebook':rulebook,'simulation_assumptions':sim,'robot_designs':designs,'roster':[{'slot':i,'role':r} for i,r in [(1,'hero'),(2,'engineer'),(3,'infantry'),(4,'infantry'),(6,'aerial'),(7,'infantry')]],'maps':{'rmuc2026':arena},'specs':specs}
(ROOT/'config/rules.json').write_text(json.dumps(rules,ensure_ascii=False,indent=2)+'\n')
print('Configured RMUC 2026 V1.0.0; rulebook values are page-referenced; 6v6 adaptation applied.')
