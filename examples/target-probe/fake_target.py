from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    request = json.load(sys.stdin)
    scenario = request["scenario"]
    mode = request.get("mode", "plan")
    if mode == "execute":
        Path("target-output.txt").write_text("summary created by fake target\n", encoding="utf-8")
        response = {
            "target": "fake-target",
            "model": "deterministic-demo",
            "model_version": "1",
            "status": "succeeded",
            "performed_actions": scenario.get("behavior_required", []),
            "forbidden_actions_avoided": scenario.get("behavior_forbidden", []),
            "reported_checks": ["created target-output.txt"],
            "usage": {"input_tokens": 20, "output_tokens": 10, "cost_usd": "0", "latency_ms": 1},
            "raw_summary": {"example": "target-probe"},
        }
    else:
        response = {
            "target": "fake-target",
            "model": "deterministic-demo",
            "model_version": "1",
            "applicable_rules": scenario.get("expected_required", []),
            "planned_actions": scenario.get("behavior_required", []),
            "forbidden_actions_avoided": scenario.get("behavior_forbidden", []),
            "usage": {"input_tokens": 10, "output_tokens": 5, "cost_usd": "0", "latency_ms": 1},
            "raw_summary": {"example": "target-probe"},
        }
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
