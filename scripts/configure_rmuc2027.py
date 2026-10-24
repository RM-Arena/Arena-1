"""Add the RMUC 2027 V1.0.0 season (2026-10-15 manuals) to config/rules.json.

The 2026 sections stay byte-for-byte as configured by configure_rmuc2026.py; this script
adds `rulebook_2027`, the `seasons` table, the `rmuc2027` map, 2027 robot designs and the
per-season construction compliance of every design. Page numbers are the printed pages of
the 2027 rules manual (rules) and construction manual (construction).
Darts, radar and electronic countermeasures (radar marking, information/jamming waves and
the radar-commanded adaptive armor) are excluded by the user, as in 2026.
"""
import copy
import json
import math
from pathlib import Path

from chapter4_2027_layout import make_arena, RESOURCE_UNITS
from exchange_difficulties import ASSEMBLY_DIFFICULTIES
from robot_compliance import construction_2027, season_compliance, add_builtin_construction_inspections
from robot_designs_2027 import DEFAULT_LINEUP_2027, make_designs_2027

ROOT = Path(__file__).resolve().parents[1]
RULES_PROFILE_2026 = 'rmuc-2026-v1.0.0-arena-v3'
RULES_PROFILE_2027 = 'rmuc-2027-v1.0.0-arena-v1'
SOURCES = {
    'rules': dict(title='RoboMaster 2027 机甲大师超级对抗赛比赛规则手册', version='1.0.0', date='2026-10-15',
                  sha256='9e2eed9295536c6fd547b62d634df1d5e70a2e1e2250e5dff3521d557e5d54be'),
    'construction': dict(title='RoboMaster 2027 机甲大师高校系列赛机器人制作规范手册', version='1.0.0', date='2026-10-15',
                         sha256='3287fe5f521f8801ce69632032ea17a9c8d8a099091558f58618cd7721154a3c'),
}


def tiers(rows, keys):
    return [dict(level=i+1, **dict(zip(keys, row))) for i, row in enumerate(rows)]


def rulebook_2027():
    infantry_chassis = {
        'power': tiers(zip([150, 175, 200, 225, 250, 275, 300, 325, 350, 400], [60, 65, 70, 75, 80, 85, 90, 95, 100, 100]), ('hp', 'power_w')),
        'hp': tiers(zip([200, 225, 250, 275, 300, 325, 350, 375, 400, 400], [45, 50, 55, 60, 65, 70, 75, 80, 90, 100]), ('hp', 'power_w'))}
    infantry_weapon = {
        'burst': tiers(zip([170, 180, 190, 200, 210, 220, 230, 240, 250, 260], [5, 7, 9, 11, 12, 13, 14, 16, 18, 20]), ('max_heat', 'cooling')),
        'cooling': tiers(zip([40, 48, 56, 64, 72, 80, 88, 96, 104, 120], [12, 14, 16, 18, 20, 22, 24, 26, 28, 30]), ('max_heat', 'cooling'))}
    return {
        'source': SOURCES['rules'],
        'season': '2027',
        'match': {'duration_s': 420, 'field_length_m': 28, 'field_width_m': 15, 'fence_height_m': 2.4, 'prep_s': 180,
                  'self_check_s': 15, 'countdown_s': 5, 'source_pages': [20, 29, 115, 118, 121]},
        'adaptations': {'excluded_systems': ['dart', 'radar', 'electronic_countermeasures'], 'team_size': 5, 'slots': [1, 3, 4, 6, 7],
                        'roles': {'1': 'heavy', '3': 'infantry', '4': 'infantry', '6': 'aerial', '7': 'sentry'},
                        'sentry_control': 'automatic', 'semi_automatic_sentry_unavailable': 'no human commander exists in this arena',
                        'adaptive_armor_excluded': 'only the radar can select the reinforced centre (5.2); all armor stays default x1',
                        'radar_marking_and_double_vulnerability_excluded': True, 'information_and_jamming_waves_excluded': True,
                        'dart_hits_and_dart_buff_suspension_excluded': True, 'commander_interventions_excluded': True,
                        'minimum_first_game_lineup_ground_robots': 3, 'aerial_systems_per_team_max': 1, 'source_pages': [13, 20, 21, 72, 108, 110, 112]},
        'damage': {'17mm': 20, '42mm': 200, 'aerial_impact': 200, 'collision': 2,
                   'normal_speed_min_17_mps': 12, 'normal_speed_min_42_mps': 8, 'rune_normal_speed_min_17_mps': 12,
                   'armor_interval_17_s': .05, 'armor_interval_42_s': .2,
                   'aerial_impact_targets': ['base_armor', 'outpost_middle_armor'], 'aerial_impact_robot_armor': False,
                   'aerial_impact_detection': 'contact time and surface impulse thresholds are TBD in V1.0.0; see seasons.2027.simulation_assumptions.drone_impact',
                   'heavy_idle_42_mask_s': 4, 'heavy_dead_42_mask_s': 3, 'heavy_dead_shot_mask_count': 3, 'heavy_overfire_masks_42': True,
                   'rune_42mm_forbidden': True, 'rounding': 'half_up_integer', 'source_pages': [64, 65, 76, 77]},
        'projectiles': {'17mm': {'diameter_m': .0168, 'mass_kg': .0032, 'muzzle_limit_mps': 25, 'heat_per_shot': 10, 'rated_per_game': 3000},
                        '42mm': {'diameter_m': .0425, 'mass_kg': .0445, 'muzzle_limit_mps': 16.5, 'heat_per_shot': 100, 'rated_per_game': 100},
                        'source_pages': [22, 24, 61, 66]},
        'heat': {'settlement_hz': 10, 'lock_when_above_limit': True, 'unlock_heat': 0, 'permanent_extra_17': 100, 'permanent_extra_42': 200,
                 'permanent_boundary': 'at_or_above_Q2_per_figure_5_1', 'source_pages': [66, 67]},
        'overspeed': {'17mm': [{'excess_from': 0, 'excess_to': 5, 'lock_s': 15}, {'excess_from': 5, 'excess_to': 10, 'lock_s': 20}, {'excess_from': 10, 'permanent': True}],
                      '42mm': [{'speed_above_limit_to_mps': 18, 'lock_s': 15}, {'speed_above_mps': 18, 'permanent': True}], 'source_page': 66},
        'power': {'settlement_hz': 10, 'buffer_capacity_j': 60, 'cutoff_s': 5, 'absolute_cap_w': 200, 'chassis_energy_pool': False,
                  'wireless_charging': False, 'source_pages': [67, 68]},
        'heal': {'disengage_s': 6, 'supply_ratio_per_s': .1, 'late_start_s': 240, 'late_disengaged_supply_ratio_per_s': .25,
                 'outpost_ratio_of_supply': .5, 'remote_delay_s': 6, 'remote_ratio': .6, 'source_pages': [16, 73]},
        'respawn': {'progress_base': 10, 'elapsed_divisor': 10, 'instant_purchase_progress_penalty': 20, 'normal_progress_per_s': 1,
                    'fast_progress_per_s': 4, 'fast_when_base_hp_below': 4000, 'normal_hp_ratio': .1, 'normal_invulnerability_s': 30,
                    'weak_clear_invulnerability_min_s': 10, 'instant_hp_ratio': 1, 'instant_invulnerability_s': 3,
                    'instant_power_multiplier': 2, 'instant_power_cap_w': 200, 'instant_power_duration_s': 4,
                    'weak_blocks_fire_and_buffs': True, 'source_pages': [74, 75]},
        'logistics': {'base_loss_divisor_hp': 20000, 'formula': 'lambda = 1 - base_hp_lost/20000',
                      'respawn_required': 'x/lambda', 'supply_heal_rate': 'x*lambda', 'remote_heal_ratio': 'x*lambda', 'source_pages': [94, 95]},
        'economy': {'initial_coins': 800, 'initial_coin_time_s': 1,
                    'periodic_schedule': [{'elapsed_s': 61, 'coins': 100}, {'elapsed_s': 121, 'coins': 100}, {'elapsed_s': 181, 'coins': 100},
                                          {'elapsed_s': 241, 'coins': 100}, {'elapsed_s': 301, 'coins': 100}, {'elapsed_s': 361, 'coins': 300}],
                    'ammo': {'17mm': {'local_batch': 10, 'local_cost': 10, 'remote_batch': 100, 'remote_cost': 150, 'team_purchase_cap': 1000},
                             '42mm': {'local_batch': 1, 'local_cost': 10, 'remote_batch': 10, 'remote_cost': 150, 'team_purchase_cap': 100}},
                    'remote_delay_s': 6, 'remote_heal_cost': '50 + ceil(elapsed_seconds/60*20)',
                    'instant_respawn_cost': 'ceil(elapsed_seconds/60)*80 + robot_level*20',
                    'local_exchange_points': ['base', 'supply', 'controlled_outpost', 'own_high_point'], 'source_pages': [75, 76, 77, 106, 107]},
        'initial_ammo': {'heavy': 0, 'infantry': 0, 'sentry': 300, 'aerial': 0, 'source_pages': [22, 24, 25]},
        'heavy': {'stages': [{'after': 'start', 'hp': 400, 'power_w': 50}, {'after': 'assembly_1', 'hp': 450, 'power_w': 50},
                             {'after': 'assembly_2', 'hp': 500, 'power_w': 50},
                             {'after': 'assembly_3_or_launcher', 'hp': 600, 'power_w': 50, 'max_heat': 300, 'cooling': 100, 'muzzle_limit_mps': 16.5}],
                  'levels': {'initial': 1, 'assembly_1': 5, 'assembly_2': 7, 'assembly_3': 10}, 'uses_experience': False,
                  'early_defense': .5, 'early_defense_until_s': 180, 'early_defense_ends_with_launcher': True,
                  'launcher_unlock': {'assembly_difficulty': 3, 'elapsed_s': '300 - M/50 - 2N/3',
                                      'M': 'max over the game of (opponent base hp - own base hp)', 'N': 'max over the game of (opponent control - own control)'},
                  'launcher_install': 'at the own workbench; the first referee-detected 42 mm shot completes the installation and counts no heat, speed or damage',
                  'launcher_install_before_unlock': 'allowed (rules Q&A clarification); the fitted launcher stays unpowered and the opponent shields 42 mm damage until the usage right is unlocked',
                  'supply_invulnerable': True, 'source_pages': [22, 23, 91, 92, 107, 108]},
        'sentry': {'mode': 'automatic', 'automatic': {'hp': 400, 'max_heat': 260, 'cooling': 30, 'power_w': 100},
                   'semi_automatic': {'hp': 200, 'max_heat': 100, 'cooling': 10, 'power_w': 60}, 'initial_ammo': 300,
                   'supply_grant': {'interval_s': 60, 'amount': 100, 'accumulates': True}, 'self_service_via_serial': True,
                   'posture': {'default': 'move', 'switch_cooldown_s': 5, 'decay_after_s': 180, 'enhanced_budget_s': 15,
                               'attack': {'normal': {'cooling_multiplier': 3, 'power_ratio': .5, 'vulnerability': .25},
                                          'decayed': {'cooling_multiplier': 2, 'power_ratio': .5, 'vulnerability': .25},
                                          'enhanced': {'no_heat': True, 'power_ratio': .5, 'vulnerability': .25}},
                               'defense': {'normal': {'defense': .5, 'power_ratio': .5, 'cooling_ratio': 1/3},
                                           'decayed': {'defense': .25, 'power_ratio': .5, 'cooling_ratio': 1/3},
                                           'enhanced': {'defense': .99, 'power_ratio': .5, 'cooling_ratio': 1/3}},
                               'move': {'normal': {'power_multiplier': 1.5, 'vulnerability': .25, 'cooling_ratio': 1/3},
                                        'decayed': {'power_multiplier': 1.2, 'vulnerability': .25, 'cooling_ratio': 1/3},
                                        'enhanced': {'power_w': 200, 'vulnerability': .25, 'cooling_ratio': 1/3}},
                               'note': 'reductions multiply after the other cooling and power buffs; results are integers'},
                   'uses_experience': False, 'level_for_experience': 1, 'source_pages': [25, 26, 76, 77, 108, 109, 110]},
        'experience': {'thresholds': [0, 550, 1100, 1650, 2200, 2750, 3300, 3850, 4400, 5000], 'gainers': ['infantry'],
                       'initial_cap': 5, 'cap_after_assembly_2': 7, 'cap_after_assembly_3': 10, 'shot_xp_17': 1,
                       'robot_damage_xp_per_hp': 4, 'outpost_damage_xp_per_hp': 2, 'base_damage_xp_per_hp': .5,
                       'kill_base_xp': 50, 'kill_level_gap_factor': .2, 'terrain_first_xp': 300,
                       'terrain_first_kinds': ['road', 'highland', 'tunnel', 'high_point'], 'stop_gain_at_cap': True, 'source_pages': [89, 90, 91]},
        'profiles': {'defaults': {'infantry_chassis': 'hp', 'infantry_weapon': 'cooling'}, 'infantry_chassis': infantry_chassis,
                     'infantry_weapon': infantry_weapon, 'locked_after_start': True, 'level_up_adds_hp_delta': True, 'source_pages': [91, 92, 93, 94]},
        'structures': {'base_hp': 10000, 'outpost_hp': 1000, 'rebuilt_outpost_hp': 500, 'base_defense_while_own_outpost_position_fully_controlled': 1.0,
                       'outpost_rotor_speed_rad_s': .8*math.pi, 'outpost_acceleration_s': 5, 'outpost_stop_after_s': 180,
                       'outpost_return_initial_s': 10, 'base_armor_opens_by': ['enemy_fortress_hold_10s'],
                       'base_armor_by_dart_excluded': True, 'source_pages': [37, 56, 94, 95, 96]},
        'control': {'positions': {'outpost': ['outpost', 'central'], 'base': ['base', 'fortress']}, 'capture_s': 5, 'release_s': 5,
                    'interrupted_progress': 'decays at the same rate; paused while both teams activate',
                    'outpost_destroyed': 'fully controlled -> same team temporary; temporary -> same team full; a full-control change by destruction rebuilds the outpost for the new owner at 500 HP',
                    'base_full_control': 'original owner only', 'outpost_pair_rate_per_s': 1, 'base_pair_rate_per_s': 3, 'source_pages': [96, 97]},
        'buffs': {'release_delay_s': 2, 'same_kind_combine': 'maximum', 'base_defense': .5, 'high_point_defense': .5, 'central_defense': .25,
                  'central_exclusive': True, 'assembly_invulnerability_budget_s': 45, 'assembly_budget_resets_on_new_best': True,
                  'supply_heavy_invulnerable': True,
                  'crossings': {'road': {'window_s': 3, 'defense': .25, 'duration_s': 5, 'cooldown_s': 15, 'low_to_high': True},
                                'highland': {'window_s': 5, 'defense': .25, 'duration_s': 30, 'low_to_high': True},
                                'tunnel_over': {'window_s': 3, 'defense': .25, 'duration_s': 30},
                                'tunnel_through': {'window_s': 3, 'cooling_multiplier': 1.5, 'duration_s': 120}},
                  'different_crossing_defense': .5,
                  'fortress': {'active_when_own_outpost_position_not_controlled_by_owner': True, 'own_defense': .5, 'one_own_robot': True,
                               'cooling_bonus': 'min(75,floor(base_drop/80))', 'reserve_ammo': 'min(500,100+floor(base_drop/15))',
                               'base_drop': 'base max hp minus the lowest base hp this game', 'heavy_reserve_per_42mm': 10,
                               'enemy_activation_after_s': 180, 'enemy_requires_controlling_owner_outpost_position': True,
                               'enemy_vulnerability': 1, 'enemy_hold_to_open_base_s': 10, 'enemy_timer_retention_s': 3},
                  'source_pages': [102, 103, 104, 105, 106, 107]},
        'assembly': {'unlock_times_s': [0, 60, 120, 180], 'required_previous_difficulty': True, 'income_period_s': 10,
                     'first_rewards': [{'heavy_level': 5, 'income': 40}, {'heavy_level': 7, 'level_cap': 7, 'income': 20},
                                       {'heavy_level': 10, 'level_cap': 10, 'team_defense': .25, 'unlock_launcher': True, 'income': 20},
                                       {'team_defense': .5, 'income': 40}],
                     'repeat_income_per_period': [4, 8, 12, 0], 'difficulty_4_once': True, 'difficulty_4_time_limit_s': 45,
                     'difficulty_4_pair_window_s': 5, 'difficulty_4_borrowed_core_max_offset_m': .4,
                     'difficulty_4_blocks_other_entry': True, 'other_attempt_blocks_difficulty_4': True,
                     'card_absence_fail_s': 15, 'insert_depth_m': .1, 'lift_m': .1, 'flip_deg': 90, 'rotation_range_deg': 90,
                     'rotation_tolerance_deg': 5, 'hold_before_prompt_s': [.3, .5], 'confirm_retry_lock_s': 1,
                     'steps': {'1': [2, 6], '2': [2, 3, 6], '3': [2, 3, 4, 5, 6], '4': [2, 3, 4, 5, 6]},
                     'initial_core_pose': [-.2, .2, .8, 0, 90, 0],
                     'pose_ranges': {'1': {'x': [-.1, 0], 'y': [.1, .3], 'z': [.5, .7], 'theta': [0, 0], 'phi': [90, 90], 'alpha': [0, 0]},
                                     '2-4': {'x': [-.1, 0], 'y': [.1, .3], 'z': [.5, .7], 'theta': [-90, 90], 'phi': [0, 90], 'alpha': [-45, 45]}},
                     'units_per_resource_station': RESOURCE_UNITS, 'source_pages': [45, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89]},
        'rune': {'arms': 5, 'arm_radius_m': .7, 'target_radius_m': .15, 'center_above_mount_m': 2.3, 'small_until_s': 180,
                 'small_chances_s': [0, 90], 'large_chances_s': [180, 255, 330], 'activation_timeout_s': 20, 'hit_timeout_s': 2.5,
                 'large_secondary_hit_s': 1, 'small_speed_rad_s': math.pi/3, 'large_a': [.780, 1.045], 'large_omega': [1.884, 2],
                 'large_b': '2.090-a', 'small_defense': .25, 'small_duration_s': 45, 'small_xp_multiplier': 2,
                 'small_team_extra_xp_cap': 1200, 'large_shared_xp': 750, 'large_xp_recipients': 'alive infantry',
                 'trigger_roles': ['infantry', 'sentry'],
                 'large_bands': [{'min': 1, 'max': 3, 'attack': 1.5, 'defense': .25, 'cooling': 1}, {'min': 3, 'max': 7, 'attack': 1.5, 'defense': .25, 'cooling': 2},
                                 {'min': 7, 'max': 8, 'attack': 2, 'defense': .25, 'cooling': 2}, {'min': 8, 'max': 9, 'attack': 2, 'defense': .25, 'cooling': 3},
                                 {'min': 9, 'max': 10, 'attack': 3, 'defense': .5, 'cooling': 5}],
                 'duration_by_hits': {'5': 30, '6': 35, '7': 40, '8': 45, '9': 50, '10': 60},
                 'large_rings_after_activations': {'1': [4, 10], '2': [7, 10]}, 'source_pages': [54, 55, 97, 98, 99, 100, 101]},
        'winner': {'early_finish': 'base_destroyed', 'early_rule': 'higher remaining base hp wins',
                   'timeout_order': ['control_degree', 'team_attack_damage', 'alive_ground_robot_hp_sum'], 'source_page': 114},
        'forbidden_zones': {'supply': 'own_only', 'assembly': 'own_only', 'base': 'nobody', 'dart_station': 'nobody', 'source_page': 133},
        'aerial': {'system': 'hangar on the own hangar platform plus up to four fully automatic aerial robots',
                   'impact_damage': 200, 'impact_targets': ['base_armor', 'outpost_middle_armor'], 'forbidden_targets': ['rune', 'hangar'],
                   'damageable': False, 'communication': 'only through the hangar', 'leaving_field': 'red card',
                   'source_pages': [27, 53, 64, 65, 129, 134]},
        'penalties': {'offender_hp_ratio': .15, 'teammate_hp_ratio': .05, 'repeat_window_s': 30, 'offender_fpv_s': 5, 'teammate_fpv_s': 2,
                      'sentry_chassis_off_s': 2, 'yellow_limit': 3, 'yellow_min_hp': 1, 'card_authority': 'trusted_referee_only; subjective intent is not randomly judged',
                      'source_pages': [123, 124]},
        'hardware_fault_rules': {'main_ground_offline_hp_fraction_per_s': .05, 'armor_capacitor_offline_hp_per_module_per_500ms': 4, 'module_check_hz': 2,
                                 'muzzle_sensor_offline_locks_weapon': True, 'default_virtual_hardware_online': True, 'source_pages': [68, 69, 70, 71]},
        'terrain_geometry': {'central_deck_m': .3, 'central_band_m': .2, 'central_rim_m': .4, 'central_end_ramp_deg': 12,
                             'assembly_plinth_top_m': .4, 'assembly_ramps_deg': [12, 14, 46], 'trapezoid_m': .2, 'trapezoid_ramp_deg': 23,
                             'high_point_m': .8, 'high_point_steps': 3, 'high_point_south_risers': 4, 'fortress_m': .15, 'fortress_ramp_deg': 20, 'road_ramps_deg': [10, 11, 15],
                             'tunnel_passage_m': .8, 'tunnel_clearance_m': [.25, .26], 'far_tunnel_length_m': 2.9, 'far_tunnel_roof_m': .35,
                             'road_bump_height_m': .07, 'road_bump_pitch_m': .24, 'hangar_platform_m': .4, 'hangar_platform_above_plinth_m': 1.2,
                             'source_pages': [36, 37, 41, 46, 48, 49, 50, 51, 52, 53, 54, 56, 57, 58, 59]},
        'document_ambiguities': [
            {'pages': [50, 57], 'issue': 'the central highland end ramps are labelled 12 degrees but drawn 0.555 m long for the 100 mm drop (figures 4-27 and 4-35)', 'resolution': 'plan geometry follows the drawings (10.2 degrees); the stated angle stays in terrain_geometry'},
            {'pages': [41, 32], 'issue': 'the text names only the three steps from the trapezoid highland; section B-B of figure 4-17 and figure 4-5 also show a 1200 mm flight of four 200 mm risers from the field on the south side', 'resolution': 'both flights are modelled'},
            {'pages': [64], 'issue': 'aerial impact contact time and impulse thresholds are TBD', 'resolution': 'simulation threshold disclosed in seasons.2027.simulation_assumptions.drone_impact'},
            {'pages': [50], 'issue': 'section A-A gives 200/350/400/300/360 without naming every surface', 'resolution': 'deck 300, fortress-side band 200, 150 mm rim 400; disclosed reconstruction'},
            {'pages': [37, 95], 'issue': 'no 17 mm restriction on base modules while closed is stated', 'resolution': 'every exposed base module accepts 17 mm, 42 mm and aerial impact; the closed shells still cover the large modules'},
            {'pages': [96], 'issue': 'temporary control release conditions name only the absent team', 'resolution': 'a temporary controller absent for 5 s hands full control to the other team; both present pauses'},
            {'pages': [45], 'issue': 'refilling the six energy units during a game is not stated', 'resolution': 'six units per station per game; assembled or failed units are recovered by the core'}],
    }


def simulation_2027(base_sim):
    sim = {
        'note': '2027 additions and replacements over simulation_assumptions; manual-silent hardware and timing choices.',
        'max_carried_units': 2, 'resource_stock': 'six physical units per station (rules 4.2.6)',
        'launcher_install': {'stationary_s': 6.0, 'dock_radius_m': .45, 'max_speed_mps': .05,
                             'note': 'workbench fitting time and tolerance are design choices; the module adds its mass to the chassis'},
        'drone_impact': {'min_normal_speed_mps': 1.5, 'min_impulse_n_s': .18, 'plate_interval_s': .2, 'restitution': .35,
                         'recovery_s': .8, 'note': 'manual thresholds are TBD; a valid strike also wears one guard integrity point'},
        'drone_projectile_hits': {'17mm_integrity_wear': .25, '42mm_knocks_down': True,
                                  'note': 'projectiles push drones by their momentum; guards stop them from reaching the rotors'},
        'drone_flight': {'hover_power_model': 'momentum theory / efficiency + avionics', 'ceiling_m': 2.35, 'floor_margin_m': .25,
                         'launch_s': 1.0, 'dock_radius_m': .25, 'dock_speed_mps': .4},
        'hangar_recharge_w': 0, 'sentry_supply_card': 'supply zone polygon',
        'assembly_difficulties': copy.deepcopy(ASSEMBLY_DIFFICULTIES),
        'assembly_repeat_reset_s': 0,
        'rune_motor': {'profile': 'rulebook_2027',
                       'note': 'Small and idle large runes rotate at pi/3 rad/s; active large runes use a*sin(omega*t)+2.090-a, reset on each new large activation; both faces share the shaft.'},
        'arm_lift_speed_mps': .15, 'arm_flip_speed_deg_s': 180,
        'central_elevation_m': .3,
    }
    for profile in sim['assembly_difficulties']:
        profile.pop('pose_ranges', None)
        profile.pop('target_rotation_deg', None)
        profile['attempt_timeout_s'] = 45 if profile is sim['assembly_difficulties'][-1] else None
        profile['confirm_hold_s'] = .4
        profile['rotation_tolerance_deg'] = 5
    return sim


def specs_2027():
    rows = {'heavy': (400, 3.2, 6, 200, .2, 0, 18, 100, 300, 100, 15.6),
            'infantry': (200, 4.0, 8, 20, .05, 0, 18, 10, 40, 12, 25),
            'sentry': (400, 4.0, 8, 20, .05, 300, 20, 10, 260, 30, 25),
            'aerial': (0, 5.0, 6, 200, 0, 0, 24, 0, 0, 0, 0)}
    return {role: dict(hp=hp, power_w=0, speed=speed, acceleration=acc, damage=damage, cooldown=cooldown, ammo=ammo, vision=vision,
                       range=40, armor=0, heat_per_shot=heat, max_heat=max_heat, cooling=cooling, projectile_speed=muzzle,
                       asset=f'/assets/robot-{role}.glb')
            for role, (hp, speed, acc, damage, cooldown, ammo, vision, heat, max_heat, cooling, muzzle) in rows.items()}


def main():
    path = ROOT/'config/rules.json'
    rules = json.loads(path.read_text(encoding='utf-8'))
    designs = rules['robot_designs']
    for key in [k for k in designs if designs[k].get('season') == '2027']:
        del designs[key]
    make_designs_2027(designs)
    add_builtin_construction_inspections(designs)
    rulebook = rulebook_2027()
    rulebook['construction'] = construction_2027(SOURCES['construction'])
    rules['rulebook_2027'] = rulebook
    arena = make_arena()
    rules['maps']['rmuc2026'].update(season='2026', ruleset='rmuc2026')
    rules['maps']['rmuc2027'] = arena
    compliance = season_compliance(designs, {'2026': rules['rulebook']['construction'], '2027': rulebook['construction']})
    for key, design in designs.items():
        design['seasons'] = compliance[key]
    roster = lambda pairs: [{'slot': s, 'role': r} for s, r in pairs]
    rules['seasons'] = {
        '2026': {'label': 'RMUC 2026', 'rules_profile': RULES_PROFILE_2026, 'rules_key': 'rulebook', 'map': 'rmuc2026',
                 'roster': roster([(1, 'hero'), (2, 'engineer'), (3, 'infantry'), (4, 'infantry'), (6, 'aerial'), (7, 'infantry')]),
                 'default_lineup': {'1': 1, '2': 2, '3': 3, '4': 4, '6': 6, '7': 7}, 'specs_key': 'specs', 'simulation_overrides': {}},
        '2027': {'label': 'RMUC 2027', 'rules_profile': RULES_PROFILE_2027, 'rules_key': 'rulebook_2027', 'map': 'rmuc2027',
                 'roster': roster([(1, 'heavy'), (3, 'infantry'), (4, 'infantry'), (6, 'aerial'), (7, 'sentry')]),
                 'default_lineup': DEFAULT_LINEUP_2027, 'specs': specs_2027(),
                 'simulation_overrides': simulation_2027(rules['simulation_assumptions'])},
    }
    rules['default_season'] = '2027'
    bad = [k for k, v in DEFAULT_LINEUP_2027.items() if not designs[str(v)]['seasons']['2027']['legal']]
    assert not bad, f'default 2027 lineup has illegal models in slots {bad}'
    path.write_text(json.dumps(rules, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    legal = {s: sorted(int(k) for k, d in designs.items() if d['seasons'][s]['legal']) for s in ('2026', '2027')}
    print('Configured RMUC 2027 V1.0.0 alongside 2026; legal models:', json.dumps(legal))


if __name__ == '__main__':
    main()
