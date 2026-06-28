from __future__ import annotations

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from legal_lm.config import AppConfig
from legal_lm.model_router import ModelRouter


def main() -> int:
    config = AppConfig.from_env()
    router = ModelRouter(config)
    checks = [
        (
            "extraction",
            'Return exactly this JSON object and no other keys: {"ok": true, "role": "extraction"}',
            "Acknowledge extraction smoke test.",
        ),
        (
            "reasoning",
            'Return exactly this JSON object and no other keys: {"ok": true, "role": "reasoning"}',
            "Acknowledge reasoning smoke test.",
        ),
        (
            "verifier",
            'Return exactly this JSON object and no other keys: {"ok": true, "role": "verifier"}',
            "Acknowledge verifier smoke test.",
        ),
    ]

    results = []
    for role, system_prompt, prompt in checks:
        result = router.generate_json(role, system_prompt, prompt)
        if result.get("ok") is not True or result.get("role") != role:
            raise RuntimeError(f"{role} smoke test returned unexpected JSON: {result}")
        results.append(result)

    print(json.dumps({"results": results, "usage": router.usage_limiter.snapshot()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
