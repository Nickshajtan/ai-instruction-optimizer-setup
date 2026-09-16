from __future__ import annotations

import json
import sys

PROTOCOL = "ai-doc.extension/v1"


def main() -> int:
    request = json.loads(sys.stdin.read())
    response = {"protocol": PROTOCOL, "request_id": request.get("request_id")}
    if request.get("protocol") != PROTOCOL:
        response.update({"status": "error", "error": "unsupported protocol"})
    elif request.get("operation") != "evaluate":
        response.update({"status": "error", "error": "unsupported operation"})
    else:
        scenarios = request["payload"]["suite"].get("scenarios", [])
        response.update(
            {
                "status": "ok",
                "result": {
                    "engine": "simple-process-evaluator",
                    "passed": True,
                    "cases": [{"id": item["id"], "passed": True, "score": 1.0} for item in scenarios],
                    "raw_summary": {"semantic": False},
                },
            }
        )
    print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
