"""LAN lobby: roles, seats, host controls and the WebSocket input path."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from rmuc_arena.lan import COOKIE, host_names, local_urls
from rmuc_arena.server import create_app

PIN = "246810"
SEATS_2027 = {("red", 1), ("red", 3), ("red", 4), ("red", 7),
              ("blue", 1), ("blue", 3), ("blue", 4), ("blue", 7)}


class LanLobbyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.urls = local_urls(8765)
        self.app = create_app("trusted-local", root / "submissions", root / "data", test_mode=True,
                              lan=True, lan_pin=PIN, lan_urls=self.urls)
        self.arena = self.app.state.arena
        self.addCleanup(self.arena.shutdown)
        self.host = TestClient(self.app, client=("testclient", 50000))
        self.remote = TestClient(self.app, client=("192.168.1.20", 50120))
        self.other = TestClient(self.app, client=("192.168.1.21", 50121))

    def tearDown(self):
        try:
            self.host.post("/api/control", json={"command": "stop"})
        except Exception:
            pass

    def join(self, client, name="P1", role="operator"):
        response = client.post("/api/lan/join", json={"name": name, "pin": PIN, "role": role})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def wait_for_battle(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.arena.battle:
                return self.arena.battle
            time.sleep(0.02)
        self.fail("the match never reached the engine")

    def start_match(self, duration=30):
        self.host.get("/api/lan/status")
        configured = self.host.post("/api/lan/config", json={"seed": 42, "duration": duration})
        self.assertEqual(configured.status_code, 200, configured.text)
        started = self.host.post("/api/lan/start")
        self.assertEqual(started.status_code, 200, started.text)
        return self.wait_for_battle()

    # ---- roles and seats -------------------------------------------------------------------
    def test_loopback_is_the_host_referee_and_gets_the_join_pin(self):
        status = self.host.get("/api/lan/status").json()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["pin"], PIN)
        self.assertEqual(status["session"]["role"], "host")
        self.assertEqual(len(status["lobby"]["seats"]), 8)
        self.assertEqual({(seat["team"], seat["slot"]) for seat in status["lobby"]["seats"]}, SEATS_2027)
        self.assertTrue(all(seat["role"] != "aerial" for seat in status["lobby"]["seats"]))
        self.assertTrue(self.urls and self.urls[0].startswith("http://"))

    def test_remote_needs_the_pin_and_never_sees_it(self):
        status = self.remote.get("/api/lan/status").json()
        self.assertIsNone(status["session"])
        self.assertIsNone(status["pin"])
        self.assertEqual(self.remote.post("/api/lan/join", json={"name": "P1", "pin": "000000"}).status_code, 403)
        joined = self.remote.post("/api/lan/join", json={"name": "P1", "pin": PIN, "role": "operator"})
        self.assertEqual(joined.status_code, 200)
        self.assertEqual(joined.json()["session"]["role"], "operator")
        # Operators cannot run the match.
        self.assertEqual(self.remote.post("/api/lan/start").status_code, 409)
        self.assertEqual(self.remote.post("/api/control", json={"command": "pause"}).status_code, 403)
        self.assertEqual(self.remote.post("/api/start", json={"duration": 1}).status_code, 403)
        self.assertEqual(self.remote.post("/api/battle-settings", json={"season": "2027", "values": {}}).status_code, 403)

    def test_a_spectator_can_watch_but_not_take_a_seat(self):
        joined = self.join(self.remote, "Viewer", "spectator")
        self.assertEqual(joined["session"]["role"], "spectator")
        self.assertEqual(self.remote.post("/api/lan/seat", json={"team": "red", "slot": 3}).status_code, 409)
        self.assertEqual(self.remote.post("/api/lan/start").status_code, 409)

    def test_seats_are_exclusive_and_the_host_can_take_one_back(self):
        self.join(self.remote, "P1")
        claimed = self.remote.post("/api/lan/seat", json={"team": "red", "slot": 3})
        self.assertEqual(claimed.status_code, 200, claimed.text)
        occupied = next(seat for seat in claimed.json()["lobby"]["seats"]
                        if seat["team"] == "red" and seat["slot"] == 3)
        self.assertEqual(occupied["name"], "P1")
        self.assertEqual(occupied["session"], claimed.json()["session"]["id"])

        self.join(self.other, "P2")
        self.assertEqual(self.other.post("/api/lan/seat", json={"team": "red", "slot": 3}).status_code, 409)
        # The aerial robot is controlled by its own flight system and is not a seat.
        self.assertEqual(self.other.post("/api/lan/seat", json={"team": "red", "slot": 6}).status_code, 409)
        self.assertEqual(self.other.post("/api/lan/seat", json={"team": "red", "slot": 4}).status_code, 200)

        forced = self.host.post("/api/lan/seat", json={"action": "release", "team": "red", "slot": 3, "force": True})
        self.assertEqual(forced.status_code, 200, forced.text)
        self.assertEqual(self.other.post("/api/lan/seat", json={"team": "red", "slot": 3}).status_code, 200)

    def test_switch_to_2026_grows_the_seat_ring_to_ten(self):
        self.host.get("/api/lan/status")
        response = self.host.post("/api/lan/config", json={"season": "2026"})
        self.assertEqual(response.status_code, 200, response.text)
        lobby = response.json()["lobby"]
        self.assertEqual(lobby["config"]["season"], "2026")
        self.assertEqual(len(lobby["seats"]), 10)
        self.assertTrue(all(seat["role"] != "aerial" for seat in lobby["seats"]))

    def test_configuration_and_referee_are_host_only(self):
        self.join(self.remote, "P1")
        self.assertEqual(self.remote.post("/api/lan/config", json={"red": "x"}).status_code, 403)
        self.assertEqual(self.remote.post("/api/lan/referee", json={"kind": "yellow_both"}).status_code, 409)
        self.assertEqual(self.host.post("/api/lan/config", json={"season": "1999"}).status_code, 422)

    # ---- live input ------------------------------------------------------------------------
    def test_websocket_input_takes_the_claimed_seat_and_players_reach_the_state(self):
        self.join(self.remote, "P1")
        self.assertEqual(self.remote.post("/api/lan/seat", json={"team": "red", "slot": 3}).status_code, 200)
        self.start_match()
        with self.remote.websocket_connect("/api/ws") as socket:
            kinds = []
            for _ in range(30):
                message = socket.receive_json()
                kinds.append(message["type"])
                if message["type"] == "snapshot":
                    socket.send_json({"type": "input", "action": {
                        "move": [1, 0], "aim": None, "pitch": 0.04, "fire": False}})
                    socket.send_json({"type": "ping", "t": 123.4})
                    break
            self.assertIn("lobby", kinds)
            self.assertIn("static", kinds)
            self.assertIn("snapshot", kinds)
            pong = socket.receive_json()
            while pong["type"] != "pong":
                pong = socket.receive_json()
            self.assertEqual(pong["t"], 123.4)
        with self.arena.battle.manual_lock:
            self.assertIn(("red", "3"), self.arena.battle.manual)
        state = self.remote.get("/api/state").json()
        self.assertEqual(state["players"], [{"team": "red", "slot": 3, "id": self.remote.get(
            "/api/lan/status").json()["session"]["id"], "name": "P1"}])

    def test_http_pilot_fallback_is_limited_to_the_claimed_seat(self):
        self.join(self.remote, "P1")
        self.remote.post("/api/lan/seat", json={"team": "red", "slot": 3})
        self.start_match()
        body = {"action": {"move": [0.2, 0], "aim": None, "pitch": 0.04, "fire": False}}
        self.assertEqual(self.remote.post("/api/player", json={"team": "red", "slot": 3, **body}).status_code, 200)
        self.assertEqual(self.remote.post("/api/player", json={"team": "red", "slot": 1, **body}).status_code, 403)

    def test_two_operators_hold_different_robots_at_the_same_time(self):
        self.join(self.remote, "P1")
        self.join(self.other, "P2")
        self.remote.post("/api/lan/seat", json={"team": "red", "slot": 3})
        self.other.post("/api/lan/seat", json={"team": "blue", "slot": 4})
        self.start_match()
        body = {"type": "input", "action": {"move": [0, 0.3], "aim": None, "pitch": 0.04, "fire": False}}
        for client in (self.remote, self.other):
            with client.websocket_connect("/api/ws") as socket:
                for _ in range(30):
                    if socket.receive_json()["type"] == "snapshot":
                        socket.send_json(body)
                        break
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with self.arena.battle.manual_lock:
                keys = set(self.arena.battle.manual)
            if {("red", "3"), ("blue", "4")} <= keys:
                break
            time.sleep(0.05)
        self.assertLessEqual({("red", "3"), ("blue", "4")}, keys)

    def test_lan_matches_are_unranked_and_record_their_operators(self):
        self.join(self.remote, "P1")
        self.remote.post("/api/lan/seat", json={"team": "red", "slot": 3})
        self.start_match(duration=1)
        time.sleep(0.3)
        self.assertTrue(self.arena.metadata["lan"])
        self.assertTrue(self.arena.metadata["test_match"])
        self.assertEqual(self.arena.metadata["operators"], [{
            "team": "red", "slot": 3,
            "id": self.remote.get("/api/lan/status").json()["session"]["id"], "name": "P1"}])
        self.host.post("/api/control", json={"command": "stop"})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and self.arena.busy:
            time.sleep(0.02)
        self.assertEqual(self.host.get("/api/leaderboard").json(), [])

    # ---- network boundary ------------------------------------------------------------------
    def test_lan_hosts_are_allowed_but_dns_rebinding_names_are_not(self):
        names = [name for name in host_names(self.urls) if name not in ("127.0.0.1", "localhost", "testserver")]
        self.assertTrue(names)
        allowed = TestClient(self.app, base_url=f"http://{names[0]}")
        self.assertEqual(allowed.get("/api/health").status_code, 200)
        blocked = TestClient(self.app, base_url="http://evil.example")
        self.assertEqual(blocked.get("/api/health").status_code, 400)


if __name__ == "__main__":
    unittest.main()
