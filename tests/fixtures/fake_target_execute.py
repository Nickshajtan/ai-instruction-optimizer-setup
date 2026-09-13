from __future__ import annotations

import json
import sys
from pathlib import Path

request = json.load(sys.stdin)
scenario = request["scenario"]
Path("execution-probe.txt").write_text("changed by fake target\n", encoding="utf-8")
print(
    json.dumps(
        {
            "target": "fake-target",
            "model": "fixture-model",
            "model_version": "1",
            "status": "succeeded",
            "performed_actions": scenario.get("behavior_required", []),
            "forbidden_actions_avoided": scenario.get("behavior_forbidden", []),
            "reported_checks": ["fixture-check"],
            "usage": {"input_tokens": 20, "output_tokens": 10, "cost_usd": "0", "latency_ms": 1},
        }
    )
)
