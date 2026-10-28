"""Personas and labelled conversations (Plan Part E #36).

    personas()          -> {id: Persona}
    conversations()     -> [Conversation], from conversations.jsonl (written by generate.py)

Labels come from conversations.yaml: what each turn is for and who should answer.
"""

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.agents.schemas import HistoryTurn, UserProfile

HERE = Path(__file__).parent
GENERATED = HERE / "conversations.jsonl"


@dataclass(frozen=True)
class Persona:
    id: str
    who: str
    style: str
    goals: str
    profile: UserProfile | None


@dataclass(frozen=True)
class TurnSpec:
    ask: str
    kind: str
    agents: tuple[str, ...] = ()
    accept: tuple = ()  # other right answers: agent tuples, or kinds
    image: bool = False
    app_agents: tuple[str, ...] = ()


@dataclass(frozen=True)
class Turn:
    spec: TurnSpec
    user: str
    assistant: str  # the reply the writer imagined, used as history for later turns


@dataclass
class Conversation:
    persona: Persona
    template: str
    turns: list[Turn] = field(default_factory=list)

    def history_before(self, i: int) -> list[HistoryTurn]:
        """The conversation before turn i, as the router would get it."""
        out = []
        for turn in self.turns[:i]:
            out.append(HistoryTurn(role="user", content=turn.user[:2000],
                                   ts="2026-10-29T09:00:00Z"))
            agents = list(turn.spec.agents) if turn.spec.kind == "coaching" else None
            out.append(HistoryTurn(role="assistant", content=turn.assistant[:2000],
                                   agents=agents, ts="2026-10-29T09:00:05Z"))
        return out

    def right(self, i: int, kind: str, agents: tuple[str, ...]) -> bool:
        spec = self.turns[i].spec
        if kind == spec.kind and (kind != "coaching" or set(agents) == set(spec.agents)):
            return True
        return any(kind == a if isinstance(a, str) else
                   (kind == "coaching" and set(agents) == set(a)) for a in spec.accept)


@lru_cache(maxsize=1)
def personas() -> dict[str, Persona]:
    data = yaml.safe_load((HERE / "personas.yaml").read_text())
    return {p["id"]: Persona(p["id"], p["who"], p["style"], p["goals"],
                             UserProfile(**p["profile"]) if p["profile"] else None)
            for p in data["personas"]}


@lru_cache(maxsize=1)
def templates() -> tuple[dict[str, list[TurnSpec]], dict[str, list[str]]]:
    """Turn specs per template, with `follow` resolved to the previous coaching turn."""
    data = yaml.safe_load((HERE / "conversations.yaml").read_text())
    out = {}
    for name, raw_turns in data["templates"].items():
        specs, last = [], ()
        for raw in raw_turns:
            agents = raw.get("agents") or ()
            agents = last if agents == "follow" else tuple(agents)
            accept = tuple(a if isinstance(a, str) else tuple(a) for a in raw.get("accept", ()))
            specs.append(TurnSpec(raw["ask"], raw["kind"], agents, accept,
                                  raw.get("image", False), tuple(raw.get("app_agents", ()))))
            if raw["kind"] == "coaching":
                last = agents
        out[name] = specs
    return out, data["plays"]


def _overrides(path: Path) -> dict[str, dict]:
    data = yaml.safe_load((HERE / "conversations.yaml").read_text())
    return (data.get("overrides") or {}).get(path.stem) or {}


def conversations(path: Path = GENERATED) -> list[Conversation]:
    specs, _ = templates()
    people = personas()
    overrides = _overrides(path)
    out = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        convo = Conversation(people[row["persona"]], row["template"])
        for i, (spec, turn) in enumerate(zip(specs[row["template"]], row["turns"], strict=True)):
            raw = overrides.get(f"{row['persona']}/{row['template']}/{i}")
            if raw:
                accept = tuple(a if isinstance(a, str) else tuple(a)
                               for a in raw.get("accept", ()))
                spec = TurnSpec(spec.ask, raw["kind"], tuple(raw.get("agents", ())), accept,
                                spec.image, spec.app_agents)
            convo.turns.append(Turn(spec, turn["user"], turn["assistant"]))
        out.append(convo)
    return out
