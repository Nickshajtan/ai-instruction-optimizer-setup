import json
import sys

request = json.load(sys.stdin)
op = request["operation"]
payload = request["payload"]
usage = {"requests": 1, "input_tokens": 100, "output_tokens": 20, "cost_usd": "0.002", "cost_source": "provider", "cache_hits": 0}

if op == "generate_candidate":
    documents = dict(payload["documents"])
    first = next(iter(documents))
    marker = "\n\nSemantic generation used feedback=" + str(bool(payload.get("feedback"))) + " memory=" + str(bool(payload.get("search_memory")))
    documents[first] += marker
    data = {"proposal": {"operations": [{"type": "rewrite", "target": first, "reason": "semantic provider rewrite", "expected_clarity_effect": "clearer", "expected_finops_effect": "neutral", "risk": "low", "objective": ["clarity"]}]}, "documents": documents}
elif op == "discover_invariants":
    data = {"invariants": [{"id": "semantic-critical-1", "source_path": "AGENTS.md", "source_section": "Rules", "text": "Validate migrations before completion", "importance": "critical", "confidence": 0.91}]}
elif op == "verify_invariant":
    text = "\n".join(payload["documents"].values()).lower()
    data = {"status": "preserved" if "validate migrations" in text or "validation" in text else "removed"}
elif op == "evaluate":
    data = {"cases": [{"id": scenario["id"], "passed": True, "score": 1.0} for scenario in payload["scenarios"]]}
elif op == "optimize_prompt":
    data = {"optimized_text": payload["artifact"]["text"] + "\nGEPA optimized."}
else:
    raise SystemExit(2)

json.dump({"data": data, "usage": usage}, sys.stdout)
