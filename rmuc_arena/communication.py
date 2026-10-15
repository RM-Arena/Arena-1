"""Bounded per-robot messages for all control modes, delivered next round."""
import json

from .submissions import SLOT_IDS

SLOTS = tuple(str(slot) for slot in SLOT_IDS)


def validate_messages(messages, sender, dynamic=False):
    if not isinstance(messages, list) or len(messages) > 4:
        raise ValueError("messages must be a list of at most four messages")
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"to", "data"}:
            raise ValueError("Each message must contain only to and data")
        recipient = message["to"]
        valid = isinstance(recipient, str) and ((recipient.isascii() and recipient.isdigit() and 0 < int(recipient) <= 2**32-1) if dynamic else recipient in SLOTS)
        if recipient != "all" and (not valid or recipient == sender):
            raise ValueError("Message recipient must be all or another own robot slot")
        if len(json.dumps(message["data"], ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()) > 512:
            raise ValueError("Message data must be <=512 bytes")


class TeamCommunication:
    def __init__(self, rosters=None):
        self.rosters = rosters or {team: SLOTS for team in ("red", "blue")}
        self.inboxes = self.empty_inboxes()

    def empty_inboxes(self):
        return {team: {str(slot): [] for slot in slots} for team, slots in self.rosters.items()}

    def route(self, outgoing, tick, delivery_tick):
        """Replace consumed inboxes atomically, in fixed team/slot/message order."""
        next_inboxes, records = self.empty_inboxes(), []
        for team, sender, messages in sorted(outgoing,key=lambda entry:(0 if entry[0]=="red" else 1,int(entry[1]))):
            for message in messages:
                recipients = [str(slot) for slot in self.rosters[team] if str(slot) != sender] if message["to"] == "all" else [message["to"]] if message["to"] in next_inboxes[team] else []
                common = {"from": f"{team}-{sender}", "tick": tick,
                          "delivery_tick": delivery_tick, "data": message["data"]}
                for recipient in recipients:
                    next_inboxes[team][recipient].append({**common, "to": f"{team}-{recipient}"})
                records.append({**common, "to": [f"{team}-{recipient}" for recipient in recipients]})
        self.inboxes = next_inboxes
        return records
