from __future__ import annotations

import json
import sys


request = json.load(sys.stdin)
scenario = request["scenario"]
print(
    json.dumps(
        {
            "target": "fake-target",
            "model": "fixture-model",
            "model_version": "1",
            "applicable_rules": scenario.get("expected_required", []),
            "planned_actions": scenario.get("expected_required", []),
            "forbidden_actions_avoided": scenario.get("expected_forbidden", []),
            "uncertainties": [],
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cost_usd": "0",
                "latency_ms": 1,
            },
            "raw_summary": {"fixture": True},
        }
    )
)
