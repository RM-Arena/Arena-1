"""Pinned provenance works from a clean checkout without private manual PDFs."""
import copy
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def source_metadata(kind):
    rules = json.loads((ROOT / "config/rules.json").read_text(encoding="utf-8"))
    source = rules["official"]["source"] if kind == "rules" else rules["official"]["construction"]["source"]
    variable = "RMUC_RULES_PDF" if kind == "rules" else "RMUC_CONSTRUCTION_PDF"
    if os.environ.get(variable):
        provided = Path(os.environ[variable])
        if hashlib.sha256(provided.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"{variable} differs from the project's pinned 2026 V1.0.0 manual")
    return copy.deepcopy(source)
