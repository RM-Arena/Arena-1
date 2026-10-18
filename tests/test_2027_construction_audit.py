"""Construction checks reject the audited omissions without changing legal rosters."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('construction_audit', ROOT/'scripts/robot_compliance.py')
COMPLIANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPLIANCE)


class ConstructionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT/'config/rules.json').read_text())
        cls.designs = copy.deepcopy(cls.config['robot_designs'])
        COMPLIANCE.add_builtin_construction_inspections(cls.designs)
        cls.limits = COMPLIANCE.construction_2027(cls.config['rulebook_2027']['construction']['source'])

    def model(self, key):
        return copy.deepcopy(self.designs[str(key)])

    def codes(self, design):
        return {i['code'] for i in COMPLIANCE.check_2027(design, self.limits)}

    def test_existing_legal_models_still_pass(self):
        expected = {key for key, d in self.config['robot_designs'].items() if d['seasons']['2027']['legal']}
        for key in expected:
            with self.subTest(model=key):
                self.assertEqual(COMPLIANCE.check_2027(self.model(key), self.limits), [])

    def test_hangar_voltage_limit_and_missing_voltage(self):
        for value in (30.001, 99, float('nan'), None):
            design = self.model(2761)
            design['voltage_v'] = value
            with self.subTest(voltage=value):
                self.assertIn('hangar_power', self.codes(design))
        design['voltage_v'] = 30
        self.assertNotIn('hangar_power', self.codes(design))

    def test_launcher_module_electric_limits_are_required(self):
        for key, value, code in [('launcher_module_voltage_v', 140.001, 'launcher_power'),
                                 ('launcher_module_voltage_v', None, 'launcher_power'),
                                 ('launcher_module_battery_wh', 1, 'launcher_battery'),
                                 ('launcher_module_battery_wh', None, 'launcher_battery')]:
            design = self.model(2711)
            design[key] = value
            with self.subTest(field=key, value=value):
                self.assertIn(code, self.codes(design))
        design = self.model(2711)
        design['launcher_module_voltage_v'] = 140
        self.assertEqual(self.codes(design), set())

    def test_missing_geometry_evidence_does_not_approve_a_new_model(self):
        design = self.model(2731)
        design.pop('construction_inspection')
        new_models = {'9999': design}
        COMPLIANCE.add_builtin_construction_inspections(new_models)
        self.assertNotIn('construction_inspection', design)
        self.assertIn('armor_inspection', self.codes(design))

    def test_actual_geometry_changes_invalidate_the_inspection(self):
        for key, value, code in [('armor_normal_to_up_deg', 0, 'armor_angle'),
                                 ('armor_inset_m', .5, 'armor_geometry')]:
            design = self.model(2731)
            design[key] = value
            with self.subTest(field=key):
                self.assertIn('armor_inspection', self.codes(design))
                self.assertIn(code, self.codes(design))

    def test_armor_alignment_offset_and_missing_clearance_are_checked(self):
        design = self.model(2731)
        mount = design['construction_inspection']['armor_mounts'][0]
        mount['normal'] = [.95, .2, (1-.95**2-.2**2)**.5]
        self.assertIn('armor_alignment', self.codes(design))
        design = self.model(2731)
        design['construction_inspection']['armor_mounts'][0]['center_m'][1] = .051
        self.assertIn('armor_offset', self.codes(design))
        design = self.model(2731)
        design['construction_inspection']['armor_mounts'][0].pop('unobstructed_cone_deg')
        self.assertIn('armor_clearance', self.codes(design))

    def test_real_box_in_front_of_a_plate_is_rejected(self):
        design = self.model(2731)
        x, y, z = design['construction_inspection']['armor_mounts'][0]['center_m']
        design['construction_inspection']['obstruction_boxes_m'] = [
            [[x+.03, y-.1, z-.1], [x+.08, y+.1, z+.1]]]
        self.assertIn('armor_obstructed', self.codes(design))
        design['construction_inspection']['obstruction_boxes_m'] = [
            [[x-.2, y-.1, z-.1], [x-.1, y+.1, z+.1]]]
        self.assertNotIn('armor_obstructed', self.codes(design))

    def test_actual_chassis_obstruction_cannot_be_cleared_by_declared_angles(self):
        design = self.model(2731)
        design['armor_inset_m'] = .1
        COMPLIANCE.add_builtin_construction_inspections({'2731': design})
        self.assertNotIn('armor_inspection', self.codes(design))
        self.assertIn('armor_obstructed', self.codes(design))

    def test_only_one_heavy_plate_may_use_conditional_obstruction(self):
        design = self.model(2711)
        for mount in design['construction_inspection']['armor_mounts'][:2]:
            mount['unobstructed_cone_deg']['upper'] = 90
            mount['conditional_obstruction_m'] = {'upper': .151}
        self.assertIn('armor_clearance', self.codes(design))
        design['construction_inspection']['armor_mounts'][1]['unobstructed_cone_deg']['upper'] = 120
        self.assertNotIn('armor_clearance', self.codes(design))
        design['construction_inspection']['armor_mounts'][0]['conditional_obstruction_m']['upper'] = .15
        self.assertIn('armor_clearance', self.codes(design))

    def test_heavy_requirement_two_needs_both_fixed_origin_envelopes(self):
        design = self.model(2711)
        design['extended_m'] = [.8, 1.3, 1.2]
        self.assertIn('envelope', self.codes(design))
        design['heavy_extended_inspection'] = {
            'coverage': 'directional_reachable_states',
            'front_origin_m': [design['chassis_size_m'][0]/2, 0, 0],
            'rear_origin_m': [-design['chassis_size_m'][0]/2, 0, 0],
            'front_bounds_m': [[-.8, -.65, 0], [0, .65, 1.2]],
            'rear_bounds_m': [[0, -.65, 0], [.8, .65, 1.2]]}
        self.assertNotIn('envelope', self.codes(design))
        design['heavy_extended_inspection']['rear_bounds_m'][1][0] = .901
        self.assertIn('envelope', self.codes(design))
        design['heavy_extended_inspection']['rear_bounds_m'][1][0] = .8
        design['heavy_extended_inspection']['rear_bounds_m'][1][1] = .60
        self.assertIn('envelope', self.codes(design))
        design['heavy_extended_inspection']['rear_bounds_m'][1][1] = .65
        design['heavy_extended_inspection']['rear_origin_m'][0] = 0
        self.assertIn('envelope', self.codes(design))


if __name__ == '__main__':
    unittest.main()
