"""LAN lobby: sessions, referee/operator seats and host controls for one arena service.

The simulation stays authoritative on the host. LAN clients never step the engine: an operator
claims one chassis, streams input over the existing WebSocket and receives the same snapshots as a
spectator. The lobby is deliberately small — one host referee, one seat per chassis robot and any
number of read-only viewers — because a single match is already the unit of work of `ArenaService`.
"""
from __future__ import annotations

import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from . import seasons

COOKIE = "arena_lan"
PIN_LENGTH = 6
SESSION_TTL = 900.0
# An operator who drops keeps their seat for a short grace period, so a browser reload or a Wi-Fi
# hiccup does not hand their robot to somebody else.
SEAT_GRACE = 30.0
MAX_SESSIONS = 64
# The cockpit sends at 20 Hz; allow a burst without letting a stuck key flood the engine thread.
MAX_INPUT_PER_SECOND = 45

DEFAULT_STRATEGIES = {
    "2027": ("claude_opus55_xhigh_2027_team", "claude_opus55_xhigh_2027_hold"),
    "2026": ("claude_opus55_xhigh_team", "claude_opus55_xhigh_hold"),
}


def make_pin():
    return f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"


def _interface_addresses():
    """Every non-loopback IPv4 address of this machine.

    `socket.getaddrinfo(hostname)` only returns one address on this Windows setup (and often only
    the primary one elsewhere), which would hide the Ethernet URL when the laptop is also on Wi-Fi.
    The platform listings cover the rest without adding a psutil dependency.
    """
    found = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            found.add(probe.getsockname()[0])
    except OSError:
        pass
    try:
        found.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None,
                                                               socket.AF_INET, socket.SOCK_STREAM))
    except OSError:
        pass
    try:
        if sys.platform == "win32":
            output = subprocess.run(["ipconfig"], capture_output=True, text=True, errors="ignore",
                                     timeout=3).stdout
            found.update(re.findall(r"IPv4[^:]*:\s*([0-9.]+)", output))
        else:
            try:
                output = subprocess.run(["ip", "-4", "addr", "show"], capture_output=True, text=True,
                                         errors="ignore", timeout=3).stdout
                found.update(re.findall(r"inet\s+([0-9.]+)/", output))
            except OSError:
                output = subprocess.run(["hostname", "-I"], capture_output=True, text=True,
                                         errors="ignore", timeout=3).stdout
                found.update(output.split())
    except (OSError, subprocess.SubprocessError):
        pass
    return sorted(address for address in found
                  if address and not address.startswith("127.") and not address.startswith("169.254.")
                  and address != "0.0.0.0")


def local_urls(port):
    """http URLs other machines can use for this process, one per non-loopback IPv4 address."""
    if not port:
        return []
    urls = {f"http://127.0.0.1:{port}"}
    urls.update(f"http://{address}:{port}" for address in _interface_addresses())
    return sorted(urls)


def host_names(urls=()):
    """Host header values a LAN client may legitimately use for this machine."""
    names = {"127.0.0.1", "localhost", "testserver", socket.gethostname(), socket.gethostname().lower()}
    for url in urls:
        name = urlparse(url).hostname
        if name:
            names.add(name)
    names.update(_interface_addresses())
    return sorted(name for name in names if name)


def _clean_name(value, fallback):
    text = " ".join(str(value or "").split())[:24]
    return text or fallback


@dataclass
class LanSession:
    id: str
    token: str
    name: str
    role: str  # host | operator | spectator
    created: float
    seen: float
    seat: tuple[str, int] | None = None
    ready: bool = False
    online: bool = False
    input_window: float = 0.0
    input_count: int = 0

    def public(self):
        return {"id": self.id, "name": self.name, "role": self.role, "ready": self.ready,
                "seat": {"team": self.seat[0], "slot": self.seat[1]} if self.seat else None}


@dataclass
class LanSeat:
    team: str
    slot: int
    role: str
    session: str | None = None

    def public(self, sessions):
        holder = sessions.get(self.session) if self.session else None
        return {"team": self.team, "slot": self.slot, "role": self.role,
                "session": holder.id if holder else None,
                "name": holder.name if holder else None,
                "ready": bool(holder and holder.ready),
                "online": bool(holder and holder.online)}


class LanLobby:
    """Thread-safe lobby state. HTTP endpoints and the WebSocket loop both touch it."""

    def __init__(self, enabled=False, pin=None, urls=(), season=seasons.DEFAULT_SEASON):
        self.enabled = bool(enabled)
        self.pin = pin or make_pin()
        self.urls = list(urls)
        self.lock = threading.RLock()
        self.sessions: dict[str, LanSession] = {}
        self.by_id: dict[str, LanSession] = {}
        self.seats: dict[tuple[str, int], LanSeat] = {}
        self.revision = 0
        self.viewers = 0
        self.phase = "idle"
        self.match_id = None
        self.season = season if season in seasons.seasons() else seasons.DEFAULT_SEASON
        red, blue = DEFAULT_STRATEGIES.get(self.season, DEFAULT_STRATEGIES["2027"])
        self.config = {"season": self.season, "map": seasons.map_of(self.season),
                       "red": red, "blue": blue, "seed": 42, "duration": 420}
        self._rebuild_seats()

    # ---- sessions -------------------------------------------------------------------------
    def _prune(self):
        now = time.monotonic()
        for token, session in list(self.sessions.items()):
            if session.role == "host" or now - session.seen <= SESSION_TTL:
                continue
            self._release(session)
            self.sessions.pop(token, None)
            self.by_id.pop(session.id, None)
            self.revision += 1

    def _create(self, name, role):
        now = time.monotonic()
        token = secrets.token_urlsafe(32)
        session = LanSession(id=secrets.token_hex(4), token=token, name=name, role=role,
                             created=now, seen=now, online=True)
        self.sessions[token] = session
        self.by_id[session.id] = session
        self.revision += 1
        return session

    def session_from_cookie(self, token):
        if not token:
            return None
        with self.lock:
            session = self.sessions.get(token)
            if session:
                session.seen = time.monotonic()
                session.online = True
            return session

    def ensure_host(self, name="主机裁判"):
        """The single host/referee session. Loopback clients share it; no PIN is involved."""
        with self.lock:
            for session in self.sessions.values():
                if session.role == "host":
                    session.name = _clean_name(name, session.name)
                    session.seen = time.monotonic()
                    session.online = True
                    return session
            return self._create(_clean_name(name, "主机裁判"), "host")

    def join(self, name, pin, role, local=False):
        with self.lock:
            if local:
                return self.ensure_host(name or "主机裁判")
            if role == "host":
                raise ValueError("主机裁判只能在本机加入")
            if role == "operator":
                if not secrets.compare_digest(str(pin or ""), str(self.pin)):
                    raise ValueError("联机 PIN 不正确")
            elif role != "spectator":
                raise ValueError("未知的联机身份")
            self._prune()
            if len(self.sessions) >= MAX_SESSIONS:
                raise ValueError("联机人数已满")
            fallback = "操作手" if role == "operator" else "观众"
            return self._create(_clean_name(name, fallback), role)

    def leave(self, session):
        with self.lock:
            if not session or session.role == "host":
                return None
            self._release(session)
            self.sessions.pop(session.token, None)
            self.by_id.pop(session.id, None)
            self.revision += 1
            return session.id

    def _release(self, session):
        if session.seat:
            seat = self.seats.get(session.seat)
            if seat and seat.session == session.id:
                seat.session = None
            session.seat = None

    # ---- seats ----------------------------------------------------------------------------
    def _rebuild_seats(self):
        roles = seasons.roles(self.season)
        wanted = {(team, int(slot)) for team in ("red", "blue") for slot, role in roles.items() if role != "aerial"}
        for seat in self.seats.values():
            if seat.session:
                session = self.by_id.get(seat.session)
                if session:
                    session.seat = None
        self.seats = {key: LanSeat(team=key[0], slot=key[1], role=roles[key[1]]) for key in sorted(wanted)}
        for session in self.sessions.values():
            session.seat = None
            session.ready = False

    def _seat(self, team, slot):
        try:
            key = (str(team), int(slot))
        except (TypeError, ValueError):
            raise ValueError("无效的机体编号") from None
        seat = self.seats.get(key)
        if not seat:
            raise ValueError("该机体不在当前赛季的可驾驶席位中")
        return key, seat

    def claim(self, session, team, slot, force=False):
        with self.lock:
            if not session or session.role not in ("host", "operator"):
                raise ValueError("只有操作手可以选择机体")
            key, seat = self._seat(team, slot)
            if seat.session and seat.session != session.id:
                holder = self.by_id.get(seat.session)
                stale = not holder or (not holder.online and time.monotonic() - holder.seen > SEAT_GRACE)
                if not (force and session.role == "host") and not stale:
                    raise ValueError(f"该机体已由 {holder.name if holder else '其他操作手'} 驾驶")
                if holder:
                    self._release(holder)
            if session.seat and session.seat != key:
                self._release(session)
            seat.session = session.id
            session.seat = key
            session.ready = False
            self.revision += 1
            return seat

    def release(self, session, team=None, slot=None, force=False):
        with self.lock:
            if not session:
                raise ValueError("请先加入联机")
            key = session.seat
            if force and session.role == "host" and team is not None:
                key, _ = self._seat(team, slot)
            if not key:
                return None
            seat = self.seats.get(key)
            if seat and (seat.session == session.id or (force and session.role == "host")):
                seat.session = None
            if session.seat == key:
                session.seat = None
                session.ready = False
            self.revision += 1
            return key

    def set_ready(self, session, ready):
        with self.lock:
            if not session or session.role not in ("host", "operator"):
                raise ValueError("只有操作手可以准备")
            if not session.seat:
                raise ValueError("请先选择机体")
            session.ready = bool(ready)
            self.revision += 1

    # ---- host controls --------------------------------------------------------------------
    def configure(self, session, values):
        with self.lock:
            if session.role != "host":
                raise ValueError("只有主机裁判可以修改比赛设置")
            season = str(values.get("season") or self.season)
            if season not in seasons.seasons():
                raise ValueError("未知赛季")
            red = str(values.get("red") or self.config["red"])[:128]
            blue = str(values.get("blue") or self.config["blue"])[:128]
            try:
                seed = int(values.get("seed", self.config["seed"]))
                duration = int(values.get("duration", self.config["duration"]))
            except (TypeError, ValueError):
                raise ValueError("种子和时长必须是整数") from None
            if not -(2 ** 31) <= seed <= 2 ** 31 - 1:
                raise ValueError("种子超出范围")
            if not 1 <= duration <= 420:
                raise ValueError("时长必须在 1 到 420 秒之间")
            changed = season != self.season
            self.season = season
            self.config = {"season": season, "map": seasons.map_of(season), "red": red, "blue": blue,
                           "seed": seed, "duration": duration}
            if changed:
                self._rebuild_seats()
            self.revision += 1
            return dict(self.config)

    def match_started(self, match_id):
        with self.lock:
            self.phase, self.match_id = "running", match_id
            self.revision += 1

    def match_finished(self, match_id):
        with self.lock:
            if self.match_id == match_id:
                self.phase = "finished"
                self.revision += 1

    # ---- presence / snapshots -------------------------------------------------------------
    def viewer_open(self, session=None):
        with self.lock:
            self.viewers += 1
            if session:
                session.online = True
                session.seen = time.monotonic()
            self.revision += 1

    def viewer_close(self, session=None):
        with self.lock:
            self.viewers = max(0, self.viewers - 1)
            if session:
                session.online = False
                session.seen = time.monotonic()
            self.revision += 1

    def touch(self, session):
        if not session:
            return
        with self.lock:
            session.seen = time.monotonic()
            session.online = True

    def allow_input(self, session):
        """Token bucket for the 20 Hz cockpit; a stuck client cannot flood the engine thread."""
        now = time.monotonic()
        with self.lock:
            if now - session.input_window >= 1.0:
                session.input_window, session.input_count = now, 0
            session.input_count += 1
            return session.input_count <= MAX_INPUT_PER_SECOND

    def player_summary(self):
        with self.lock:
            result = []
            for seat in self.seats.values():
                holder = self.by_id.get(seat.session) if seat.session else None
                if holder:
                    result.append({"team": seat.team, "slot": seat.slot, "id": holder.id, "name": holder.name})
            return result

    def snapshot(self):
        with self.lock:
            operators = sum(1 for session in self.sessions.values() if session.role == "operator")
            return {"enabled": self.enabled, "phase": self.phase, "match_id": self.match_id,
                    "config": dict(self.config),
                    "seats": [seat.public(self.by_id) for seat in self.seats.values()],
                    "viewers": self.viewers,
                    "operators": operators,
                    "spectators": max(0, self.viewers - operators),
                    "pin_required": bool(self.enabled)}

    def status(self, session, local=False):
        with self.lock:
            return {"enabled": self.enabled, "pin_required": bool(self.enabled),
                    "pin": self.pin if local and self.enabled else None,
                    "urls": list(self.urls) if self.enabled else [],
                    "session": session.public() if session else None,
                    "lobby": self.snapshot()}
