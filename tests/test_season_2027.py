"""RMUC 2027 alongside 2026: legal models, map selection, workspaces and real battles."""
import json
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from rmuc_arena import sdk
from rmuc_arena import seasons as season_rules
from rmuc_arena.engine import Match
from rmuc_arena.models import mirrored_lineups, normalize_team_lineup
from rmuc_arena.runner import Battle
from rmuc_arena.server import create_app
from rmuc_arena.showcase import load_profile
from rmuc_arena.submissions import ROOT, guide_path, load_submission
from tests.showcase_fixture import SHOWCASE_TEXT

LINEUP_2027 = {"1": 2712, "3": 2731, "4": 2732, "6": 2763, "7": 2772}


class SeasonRulesTests(unittest.TestCase):
    def test_2027_is_the_default_and_both_seasons_are_described(self):
        summary = season_rules.summary()
        self.assertEqual(season_rules.DEFAULT_SEASON, "2027")
        self.assertEqual(summary["2027"]["slots"], [1, 3, 4, 6, 7])
        self.assertEqual(summary["2026"]["slots"], [1, 2, 3, 4, 6, 7])
        self.assertEqual(summary["2027"]["map"], "rmuc2027")
        self.assertEqual(set(summary["2027"]["excluded_systems"]), {"dart", "radar", "electronic_countermeasures"})

    def test_lineups_admit_only_models_that_pass_the_season_construction_rules(self):
        self.assertEqual(normalize_team_lineup(LINEUP_2027, "2027"), LINEUP_2027)
        # Lineup slots alone identify the season.
        self.assertEqual(normalize_team_lineup(LINEUP_2027), LINEUP_2027)
        for slot, model in (("1", 1), ("1", 101), ("6", 6), ("6", 601), ("7", 7)):
            with self.subTest(slot=slot, model=model), self.assertRaises(ValueError):
                normalize_team_lineup({**LINEUP_2027, slot: model}, "2027")
        # 2027-only hardware cannot enter 2026 lineups; 2027 infantry can.
        base_2026 = season_rules.default_lineup("2026")
        for slot, model in (("1", 2711), ("6", 2761), ("2", 2711)):
            with self.subTest(slot=slot, model=model), self.assertRaises(ValueError):
                normalize_team_lineup({**base_2026, slot: model}, "2026")
        self.assertEqual(normalize_team_lineup({**base_2026, "3": 2731}, "2026")["3"], 2731)
        # 2026 infantry remain legal in the 2027 infantry slots.
        self.assertEqual(normalize_team_lineup({**LINEUP_2027, "3": 305}, "2027")["3"], 305)

    def test_the_engine_rejects_illegal_models_and_a_second_aerial_system(self):
        with self.assertRaises(ValueError):
            illegal = {team: [{"slot": int(s), "model": 1 if s == "1" else m} for s, m in LINEUP_2027.items()] for team in ("red", "blue")}
            Match(duration=1, map_name="rmuc2027", lineups=illegal).close()
        lineups = {team: [{"slot": 1, "model": 2761}, {"slot": 2, "model": 2762}] for team in ("red", "blue")}
        with self.assertRaises(ValueError):
            Match(duration=1, map_name="rmuc2027", lineups=lineups).close()
        with Match(duration=1, map_name="rmuc2027", lineups=mirrored_lineups(LINEUP_2027)) as match:
            frame = match.snapshot()
            self.assertEqual(frame["season"], "2027")
            self.assertEqual(sorted(frame["positions"]), ["blue_base", "blue_outpost", "red_base", "red_outpost"])
            aerial = next(r for r in frame["robots"] if r["role"] == "aerial" and r["team"] == "red")
            self.assertEqual(len(aerial["drones"]), 3)

    def test_sdk_reads_both_seasons(self):
        self.assertEqual(set(sdk.RULES_BY_SEASON), {"2026", "2027"})
        arena = sdk.ARENAS_BY_SEASON["2027"]
        for zone in arena["zones"]:
            if zone.get("polygon"):
                with self.subTest(zone=zone["id"]):
                    self.assertTrue(sdk.point_in_polygon(*sdk.zone_center(arena, zone["id"]), zone["polygon"]))
        self.assertTrue(sdk.can_fire({"role": "heavy", "launcher": "installed", "alive": True, "ammo": 3, "heat": 0, "max_heat": 300}))
        self.assertFalse(sdk.can_fire({"role": "heavy", "launcher": "unlocked", "alive": True, "ammo": 3, "heat": 0, "max_heat": 300}))


class SeasonApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.registry = root / "registry.json"
        self.app = create_app("trusted-local", root / "submissions", root / "data", test_mode=True, workspace_registry=self.registry)
        self.addCleanup(self.app.state.training.shutdown)
        self.addCleanup(self.app.state.arena.shutdown)
        self.client = TestClient(self.app)

    def wait(self, match_id):
        for _ in range(600):
            record = self.client.get(f"/api/matches/{match_id}").json()
            if record["status"] in ("finished", "failed"):
                return record
            time.sleep(.05)
        self.fail("match did not finish")

    def test_models_maps_and_catalog_name_their_seasons(self):
        models = self.client.get("/api/models").json()
        self.assertEqual(models["default_season"], "2027")
        self.assertEqual(models["default_team_lineup"], {"1": 2711, "3": 2731, "4": 2732, "6": 2761, "7": 2771})
        self.assertFalse(models["models"]["1"]["seasons"]["2027"]["legal"])
        self.assertTrue(models["models"]["1"]["seasons"]["2027"]["issues"])
        self.assertEqual(set(self.client.get("/api/maps").json()), {"rmuc2026", "rmuc2027"})
        catalog = self.client.get("/api/catalog", params={"season": "2027"}).json()
        self.assertEqual({catalog[k]["season"] for k in catalog}, {"2027"})
        self.assertIn("official_2027_team", catalog)
        self.assertNotIn("official_team", catalog)
        self.assertEqual(catalog["official_2027_team"]["agent"], {"provider": "anthropic", "model": "Claude Opus 5.5"})
        for key, entry in catalog.items():
            self.assertEqual(entry["agent"], load_profile(ROOT / "examples" / key)["agent"])
            self.assertNotRegex(entry["display_name"], r"(?i)official|官方")

    def test_a_match_without_a_map_follows_its_strategies_and_defaults_to_2027(self):
        started = self.client.post("/api/start", json={"duration": 2})
        self.assertEqual(started.status_code, 200, started.text)
        record = self.wait(started.json()["match_id"])
        self.assertEqual((record["status"], record["metadata"]["season"], record["metadata"]["map"]), ("finished", "2027", "rmuc2027"))
        self.assertEqual(record["result"]["policy_errors"], 0)
        for team in ("red", "blue"):
            self.assertEqual(record["metadata"]["teams"][team]["agent"], {"provider": "anthropic", "model": "Claude Opus 5.5"})
            for agent in record["metadata"]["agents"][team].values():
                self.assertEqual((agent["provider"], agent["model"]), ("anthropic", "Claude Opus 5.5"))
                self.assertNotRegex(agent["strategy"], r"(?i)official|官方")
        legacy = self.client.post("/api/start", json={"red": "official_team", "blue": "official_hold", "duration": 2})
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(self.wait(legacy.json()["match_id"])["metadata"]["map"], "rmuc2026")
        mixed = self.client.post("/api/start", json={"red": "official_team", "blue": "official_2027_hold", "map": "rmuc2027", "duration": 2})
        self.assertEqual(mixed.status_code, 409)

    def test_free_battle_lists_only_legal_models_and_limits_aerial_systems(self):
        cards = self.client.get("/api/robot-catalog", params={"season": "2027"}).json()
        models = {card["robot"] for card in cards.values()}
        self.assertTrue({2711, 2761, 2771, 3, 305} <= models)
        self.assertFalse({1, 2, 6, 101, 601} & models)
        deck = {"mode": "deck", "map": "rmuc2027", "duration": 2,
                "red_deck": ["official_2027_adaptive_2711", "official_2027_adaptive_2761", "official_2027_adaptive_305"],
                "blue_deck": ["official_2027_adaptive_2771_guard", "official_2027_adaptive_2732_assault"]}
        started = self.client.post("/api/start", json=deck)
        self.assertEqual(started.status_code, 200, started.text)
        record = self.wait(started.json()["match_id"])
        self.assertEqual(record["status"], "finished", record)
        self.assertEqual(record["result"]["policy_errors"], 0)
        illegal = dict(deck, red_deck=["official_adaptive_1"])
        self.assertEqual(self.client.post("/api/start", json=illegal).status_code, 409)
        twice = dict(deck, red_deck=["official_2027_adaptive_2761", "official_2027_adaptive_2762"])
        self.assertEqual(self.client.post("/api/start", json=twice).status_code, 409)

    def test_2027_workspaces_use_the_five_robot_roster_and_2027_guides(self):
        for mode, robot, files in (("team", None, ["strategy.py"]), ("robot", 7, ["strategy.py"]),
                                   ("distributed", None, ["robot_1.py", "robot_3.py", "robot_4.py", "robot_6.py", "robot_7.py"]),
                                   ("adaptive", 2711, ["strategy.py"])):
            with self.subTest(mode=mode):
                body = {"name": "t27-" + mode, "mode": mode, "minutes": 15, "season": "2027"}
                if robot is not None:
                    body["robot"] = robot
                if mode == "team":
                    body["team_lineup"] = LINEUP_2027
                response = self.client.post("/api/training-workspaces", json=body)
                self.assertEqual(response.status_code, 200, response.text)
                workspace = Path(response.json()["workspace"])
                agent = json.loads((workspace / "agent.json").read_text())
                self.assertEqual((agent["editable"], agent["rules_profile"]), (files, season_rules.rules_profile("2027")))
                guide = (workspace / "AGENT_GUIDE.md").read_text(encoding="utf-8")
                self.assertIn("RMUC 2027", guide)
                arena = json.loads((workspace / "arena.json").read_text())
                self.assertEqual((arena["season"], arena["map"]["name"]), ("2027", "rmuc2027"))
        refused = self.client.post("/api/training-workspaces", json={"name": "bad27", "mode": "adaptive", "robot": 1, "season": "2027"})
        self.assertEqual(refused.status_code, 400)
        refused = self.client.post("/api/training-workspaces", json={"name": "bad27b", "mode": "team", "season": "2027",
                                                                     "team_lineup": {**LINEUP_2027, "1": 1}})
        self.assertEqual(refused.status_code, 400)

    def test_guides_and_team_briefing_follow_the_season(self):
        self.assertIn("RMUC 2027", self.client.get("/api/agent-guide").text)
        self.assertEqual(self.client.get("/api/agent-guide", params={"mode": "adaptive", "robot": 2761}).text,
                         guide_path("adaptive", 2761, "zh", "2027").read_text(encoding="utf-8"))
        briefing = self.client.post("/api/team-briefing", json={"team_lineup": LINEUP_2027}).json()
        self.assertEqual(briefing["season"], "2027")
        self.assertIn("HV-D", briefing["task"]["zh"])
        self.assertIn("已锁定的双方共同阵容（RMUC 2027）", briefing["guides"]["zh"])

    def test_uploads_are_checked_against_the_season(self):
        entry = {"2711": 'def act(obs,state):\n return {obs["controlled_ids"][0]:{}},state\n'}
        ok = self.client.post("/api/submissions", json={"name": "heavy-27", "mode": "adaptive", "robot": 2711, "entries": entry, "showcase": SHOWCASE_TEXT})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["manifest"]["rules_profile"], season_rules.rules_profile("2027"))
        refused = self.client.post("/api/submissions", json={"name": "heavy-26", "mode": "adaptive", "robot": 2711, "season": "2026",
                                                             "entries": entry, "showcase": SHOWCASE_TEXT})
        self.assertEqual(refused.status_code, 400)


class Season2027ExampleTests(unittest.TestCase):
    def test_2027_examples_match_their_generator(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_examples_2027", ROOT / "scripts/build_examples_2027.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for path, data in module.outputs().items():
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual(path.read_bytes(), data)


class Season2027BattleTests(unittest.TestCase):
    def test_official_2027_strategies_play_without_errors(self):
        for red, blue in (("official_2027_team", "official_2027_hold"), ("official_2027_squad", "official_2027_distributed")):
            with self.subTest(red=red, blue=blue):
                with Battle(ROOT / "examples" / red, ROOT / "examples" / blue, 7, 12, None, "trusted-local") as battle:
                    result = battle.run()
                    self.assertEqual(result["policy_errors"], 0, battle.diagnostics)
                    self.assertEqual(battle.metadata["season"], "2027")
                    self.assertEqual(battle.match.snapshot()["arena"]["name"], "rmuc2027")
        manifest, _ = load_submission(ROOT / "examples/official_2027_team")
        self.assertEqual(manifest["team_lineup"], season_rules.default_lineup("2027"))


if __name__ == "__main__":
    unittest.main()
