"""Write the repo-root contracts/ folder from the Pydantic models and rules.yaml (Plan C.4).

    python -m app.contracts.generate           # write the files
    python -m app.contracts.generate --check   # exit 1 if the committed files differ

Only contracts/schema/, contracts/crisis.json and contracts/catalogue.json are generated. The sample
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
        "schema/history_page.json": _schema(schemas.HistoryPage),
        "schema/import_payload.json": _schema(schemas.ImportPayload),
    }
    # The exact schemas sent to the providers
    for name, model in schemas.REPLY_MODELS.items():
        files[f"schema/llm/{name}_reply.json"] = schemas.llm_json_schema(model)
    files["schema/llm/router_reply.json"] = schemas.llm_json_schema(schemas.RouterReply)
    for name, model in schemas.TOOL_ARG_MODELS.items():
        files[f"schema/llm/tool_{name}.json"] = schemas.llm_json_schema(model)

    files["catalogue.json"] = catalogue_contract()

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


def catalogue_contract() -> dict:
    """The profile pickers (P5.3, Part E #42): each condition, allergy and diet the gate
    knows, its name, and the words an account saves for it (`save`), which the profile
    resolution reads back as the same ID (C.8; the import writes the same words)."""
    catalogue = get_guardrails().catalogue
    terms = catalogue.profile_terms

    def named(words: list[str]) -> str:
        return words[0][:1].upper() + words[0][1:]

    return {
        "version": catalogue.version,
        "conditions": [{"id": c.id, "name": c.name, "save": c.name}
                       for c in catalogue.conditions],
        "allergens": [{"id": str(a), "name": named(w), "save": f"{w[0]} allergy"}
                      for a, w in terms.allergens.items()],
        "diets": [{"id": str(d), "name": named(w), "save": w[0]} for d, w in terms.diets.items()],
    }


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
