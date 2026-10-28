"""Write conversations.jsonl: each persona plays its templates, in its own words.

    cd backend && python -m tests.scenarios.generate [OUT]  # real OpenAI calls, about $0.01

The writer model sees the persona and what each turn is for, never the labels.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from app.providers import GenerateOptions, MalformedOutput, Turn
from app.providers.openai import OpenAIProvider

from .scenarios import GENERATED, personas, templates

WRITER_MODEL = "gpt-6-luna"


class _Exchange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user: str = Field(description="The user's message, exactly as they would type it.")
    assistant: str = Field(description=(
        "A short plausible reply from the app, at most 300 characters, so later turns "
        "have something to follow up on."))


class _Script(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turns: list[_Exchange]


def _prompt(persona, specs) -> str:
    asks = "\n".join(f"{i + 1}. {s.ask}" + (" (they attach a photo)" if s.image else "")
                     for i, s in enumerate(specs))
    profile = persona.profile.model_dump() if persona.profile else "none (new guest)"
    return (
        "Write a realistic chat between this person and Holos, an app that coaches "
        "exercise, food and mental wellbeing.\n\n"
        f"Person: {persona.who}\nHow they write: {persona.style}\nGoals: {persona.goals}\n"
        f"Their profile in the app: {profile}\n\n"
        f"Write exactly {len(specs)} user turns, one per step, each followed by a short app "
        f"reply:\n{asks}\n\n"
        "Write the user's messages the way this person really types (language, length, "
        "typos, tone). Never name the app's coaches or categories ('physical', "
        "'nutrition', 'mental', 'holistic'). Make each message specific to this person's "
        "life and goals.")


async def main() -> None:
    load_dotenv(".env")
    specs, plays = templates()
    people = personas()
    provider = OpenAIProvider(os.environ["OPENAI_API_KEY"],
                              http_client=httpx.AsyncClient(timeout=90))
    options = GenerateOptions(model=WRITER_MODEL, max_output_tokens=3000, timeout_s=90)
    jobs = [(pid, name) for pid, names in plays.items() for name in names]

    async def write(pid: str, name: str) -> dict:
        for _ in range(3):  # a broken script, or one with the wrong turn count, is redone
            try:
                result = await provider.generate(
                    [Turn("user", _prompt(people[pid], specs[name]))], options=options,
                    schema=_Script)
            except MalformedOutput:
                continue
            turns = result.parsed.turns
            if len(turns) == len(specs[name]):
                return {"persona": pid, "template": name,
                        "turns": [t.model_dump() for t in turns],
                        "tokens": [result.usage.tokens_in, result.usage.tokens_out]}
        raise RuntimeError(f"{pid}/{name}: no usable script in three tries")

    rows = await asyncio.gather(*(write(pid, name) for pid, name in jobs))
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else GENERATED
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} conversations to {out}")


if __name__ == "__main__":
    asyncio.run(main())
