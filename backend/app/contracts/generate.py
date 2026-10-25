"""Write the repo-root contracts/ folder from the Pydantic models and rules.yaml (Plan C.4).

    python -m app.contracts.generate           # write the files
    python -m app.contracts.generate --check   # exit 1 if the committed files differ

Only contracts/schema/ and contracts/crisis.json are generated. The sample
streams and crisis cases next to them are written by hand.
"""

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.agents import schemas
from app.guardrails.loader import get_guardrails

CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts"


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _schema(model: type[BaseModel]) -> dict:
    return model.model_json_schema()


def build() -> dict[str, str]:
    """Every generated file, as {path relative to contracts/: content}."""
    files = {
        "schema/chat_payload.json": _schema(schemas.ChatPayload),
        "schema/user_profile.json": _schema(schemas.UserProfile),
        "schema/history_turn.json": _schema(schemas.HistoryTurn),
        "schema/trace_view.json": _schema(schemas.TraceView),
        "schema/stream_event.json": schemas.STREAM_EVENT.json_schema(),
    }
    # The exact schemas sent to the providers
    for name, model in schemas.REPLY_MODELS.items():
        files[f"schema/llm/{name}_reply.json"] = schemas.llm_json_schema(model)
    for name, model in schemas.TOOL_ARG_MODELS.items():
        files[f"schema/llm/tool_{name}.json"] = schemas.llm_json_schema(model)

    rules = get_guardrails().rules
    crisis = rules.crisis
    files["crisis.json"] = {
        "contract_version": schemas.CONTRACT_VERSION,
        "rules_version": rules.version,
        "phrases": crisis.phrases,
        "exceptions": crisis.exceptions,
        "normalise": crisis.normalise.model_dump(),
        "message": crisis.message,
        "reminder": crisis.reminder,
        "helplines": [h.model_dump() for h in crisis.helplines],
    }
    return {path: _dump(data) for path, data in files.items()}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    drift = []
    for rel, content in build().items():
        path = CONTRACTS_DIR / rel
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if check:
            drift.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote contracts/{rel}")
    if drift:
        print("contracts/ is out of date; run: python -m app.contracts.generate")
        for rel in drift:
            print(f"  contracts/{rel}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
