"""A minimal valid showcase.json, which final submissions and web uploads now require."""
import json
from pathlib import Path

SHOWCASE = {"format": "rmuc-showcase-v1", "title": "测试策略", "tagline": "测试用打法", "summary": "用于测试的策略展示。",
            "style": {"aggression": 50, "defense": 50, "economy": 50, "objective": 50, "teamwork": 50, "adaptability": 50},
            "phases": [{"from": 0, "to": 420, "title": "全场", "goal": "按程序执行", "focus": "attack"}]}
SHOWCASE_TEXT = json.dumps(SHOWCASE, ensure_ascii=False)


def write_showcase(workspace, **changes):
    (Path(workspace) / "showcase.json").write_text(json.dumps({**SHOWCASE, **changes}, ensure_ascii=False), encoding="utf-8")
