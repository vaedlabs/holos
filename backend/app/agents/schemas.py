"""Pydantic models shared by the backend, the LLM providers and the frontend (Plan C.3, C.5, C.10).

Two kinds of model live here:

* LLM models (reply models, items, tool arguments) are sent to a provider as a
  JSON Schema. They follow the provider rules: every field required (null for
  missing), no unions other than nullable, no recursion, nesting depth at most 3,
  and every string has a max length.
* Backend and stream models (ChatPayload, stream events, TraceView, ...) are never
  sent to an LLM, so they may use unions and defaults.

Neither provider enforces string lengths in structured output (Plan Part D), so
`llm_json_schema()` moves each maxLength into the field description and Pydantic
enforces it when the reply is parsed.
"""

import copy
import operator
from datetime import datetime
from enum import StrEnum
from functools import reduce
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from app.guardrails.loader import get_guardrails
from app.guardrails.types import Allergen, Diet

CONTRACT_VERSION = 1

_catalogue = get_guardrails().catalogue

# Enums built from catalogue.yaml, so the model can only return known IDs
ExerciseId = StrEnum("ExerciseId", {i: i for i in _catalogue.exercise_ids})
PracticeId = StrEnum("PracticeId", {i: i for i in _catalogue.practice_ids})

ReplyKind = Literal["plan", "answer", "log_ack", "clarify"]
Route = Literal["physical", "nutrition", "mental", "holistic", "greeting", "meta", "off_topic"]
AgentName = Literal["physical", "nutrition", "mental"]
WriteKind = Literal["workout", "meal", "practice"]
Intensity = Literal["low", "moderate", "high"]

# A short text: catalogue-style IDs and tags
_ID_PATTERN = r"^[a-z0-9_]+$"


class _LLMModel(BaseModel):
    """Base for models sent to an LLM: no extra fields, every field required."""

    model_config = ConfigDict(extra="forbid")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Items (C.3) ---


class ExerciseItem(_LLMModel):
    catalogue_id: ExerciseId
    sets: int | None = Field(ge=1, le=10)
    reps: int | None = Field(ge=1, le=100)
    duration_s: int | None = Field(ge=1, le=3600)
    intensity: Intensity
    note: str = Field(max_length=120)


class PracticeItem(_LLMModel):
    catalogue_id: PracticeId
    duration_min: int = Field(ge=1, le=60)
    note: str = Field(max_length=120)


class FoodItem(_LLMModel):
    name: str = Field(max_length=60)
    ingredients: list[Annotated[str, Field(max_length=30)]] = Field(min_length=1, max_length=8)
    allergen_tags: list[Allergen] = Field(max_length=len(Allergen))
    diet_tags: list[Diet] = Field(max_length=len(Diet))
    portion: str = Field(max_length=40)
    calories: float | None = Field(ge=0, le=5000)
    note: str = Field(max_length=120)


# --- Replies (C.3) ---

PLAN_MAX_ITEMS = {"PhysicalReply": 8, "NutritionReply": 5, "MentalReply": 5}

# Output tokens for the reply itself, per agent (Plan C.9). Nutrition is higher
# because a full 5-food plan needs it (Part E #10). The largest valid reply must
# fit in the cap minus SIZE_RULE_MARGIN, so a reply is never cut off.
REPLY_TOKEN_CAP = {"physical": 1200, "nutrition": 1400, "mental": 1200}
SIZE_RULE_MARGIN = 100


class _ReplyBase(_LLMModel):
    kind: ReplyKind
    summary: str = Field(max_length=400)
    notes: list[Annotated[str, Field(max_length=200)]] = Field(max_length=3)
    source_ids: list[Annotated[str, Field(max_length=20)]] = Field(max_length=5)
    follow_up: str | None = Field(max_length=200)
    risk_flag: bool

    @model_validator(mode="after")
    def _items_match_kind(self):
        count = len(self.items)  # type: ignore[attr-defined]
        if self.kind == "plan" and count == 0:
            raise ValueError("a plan needs at least one item")
        if self.kind != "plan" and count:
            raise ValueError(f"kind '{self.kind}' must have no items")
        if self.kind != "clarify" and self.follow_up is not None:
            raise ValueError("follow_up is only for kind 'clarify'")
        return self


class PhysicalReply(_ReplyBase):
    items: list[ExerciseItem] = Field(max_length=8)


class NutritionReply(_ReplyBase):
    items: list[FoodItem] = Field(max_length=5)


class MentalReply(_ReplyBase):
    items: list[PracticeItem] = Field(max_length=5)


AgentReply = PhysicalReply | NutritionReply | MentalReply  # backend only, never sent to an LLM
REPLY_MODELS: dict[AgentName, type[_ReplyBase]] = {
    "physical": PhysicalReply,
    "nutrition": NutritionReply,
    "mental": MentalReply,
}


# --- Tool arguments (C.10) ---


class GetRecentLogsArgs(_LLMModel):
    kind: WriteKind
    days: int = Field(ge=1, le=14)


class WebSearchArgs(_LLMModel):
    query: str = Field(max_length=200)


class LogWorkoutArgs(_LLMModel):
    catalogue_id: ExerciseId
    sets: int | None = Field(ge=1, le=10)
    reps: int | None = Field(ge=1, le=100)
    duration_s: int | None = Field(ge=1, le=3600)
    note: str = Field(max_length=120)


class LogMealArgs(_LLMModel):
    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    foods: list[FoodItem] = Field(min_length=1, max_length=5)


class LogPracticeArgs(_LLMModel):
    catalogue_id: PracticeId
    duration_min: int = Field(ge=1, le=60)
    mood_before: int | None = Field(ge=1, le=5)
    mood_after: int | None = Field(ge=1, le=5)
    note: str = Field(max_length=120)


TOOL_ARG_MODELS: dict[str, type[_LLMModel]] = {
    "get_recent_logs": GetRecentLogsArgs,
    "web_search": WebSearchArgs,
    "log_workout": LogWorkoutArgs,
    "log_meal": LogMealArgs,
    "log_practice": LogPracticeArgs,
}
WRITE_ARGS: dict[WriteKind, type[_LLMModel]] = {
    "workout": LogWorkoutArgs,
    "meal": LogMealArgs,
    "practice": LogPracticeArgs,
}

LLM_MODELS: list[type[_LLMModel]] = [*REPLY_MODELS.values(), *TOOL_ARG_MODELS.values()]


# --- Profile, history, request (C.3) ---


class UserProfile(_Model):
    condition_ids: list[Annotated[str, Field(max_length=40, pattern=_ID_PATTERN)]] = Field(
        max_length=30
    )
    allergen_tags: list[Allergen] = Field(max_length=len(Allergen))
    diet_tags: list[Diet] = Field(max_length=len(Diet))
    notes: str = Field(max_length=1000)


class HistoryTurn(_Model):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)
    route: Route | None = None
    ts: datetime

    @model_validator(mode="after")
    def _route_on_assistant_only(self):
        if self.role == "user" and self.route is not None:
            raise ValueError("route is only set on assistant turns")
        return self


class ChatPayload(_Model):
    # min_length rejects a blank message before any paid call (red-team finding, Part E #9)
    message: str = Field(min_length=1, max_length=2000)
    agent: Route | None = None
    guest_profile: UserProfile | None = None
    guest_history: list[HistoryTurn] | None = Field(default=None, max_length=6)
    client_request_id: UUID
    contract_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _not_blank(self):
        if not self.message.strip():
            raise ValueError("message is blank")
        return self


# --- Results and decisions (C.3) ---


class Decision(_Model):
    action: Literal["allow", "warn", "block"]
    rule_id: str = Field(max_length=40)
    rules_version: int = Field(ge=1)
    reason: str = Field(max_length=200)
    offending_items: list[str] = []


class Source(_Model):
    id: str = Field(max_length=20)
    title: str = Field(max_length=200)
    url: str = Field(max_length=2000, pattern=r"^https?://")


class StagedWrite(_Model):
    kind: WriteKind
    args: LogWorkoutArgs | LogMealArgs | LogPracticeArgs

    @model_validator(mode="after")
    def _args_match_kind(self):
        if not isinstance(self.args, WRITE_ARGS[self.kind]):
            raise ValueError(f"args don't match kind '{self.kind}'")
        return self


class AgentResult(_Model):
    reply: AgentReply
    warnings: list[str] = []
    decisions: list[Decision] = []
    sources: list[Source] = []
    staged_writes: list[StagedWrite] = []


class HolisticResult(_Model):
    results: list[AgentResult] = Field(min_length=1, max_length=3)
    summary: str = Field(max_length=600)


# --- Trace (C.5) ---


class Usage(_Model):
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0)


class TraceStep(_Model):
    name: str = Field(max_length=40)
    agent: AgentName | None = None
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    queue_ms: int = Field(ge=0)


class TraceTool(_Model):
    name: str = Field(max_length=40)
    args: str = Field(max_length=120)
    duration_ms: int = Field(ge=0)
    status: Literal["ok", "error", "refused", "staged", "unavailable"]


class TraceView(_Model):
    trace_id: str = Field(max_length=64)
    route: Route | Literal["crisis"]
    steps: list[TraceStep] = []
    tools: list[TraceTool] = []
    decisions: list[Decision] = []
    retries: int = Field(default=0, ge=0)
    sources: list[Source] = []
    usage: Usage


# --- Stream events (C.5) ---


class _EventData(_Model):
    seq: int = Field(ge=0)
    trace_id: str = Field(max_length=64)


class AcceptedData(_EventData):
    contract_version: int = Field(ge=1)
    mode: Literal["guest", "account"]


class StepData(_EventData):
    name: Literal[
        "admitted", "routed", "agent_started", "tool_call", "gate", "retry", "composing"
    ]
    agent: AgentName | None = None
    detail: str | None = Field(default=None, max_length=200)


class SectionStartData(_EventData):
    agent: AgentName
    kind: ReplyKind


class ItemData(_EventData):
    agent: AgentName
    item: ExerciseItem | FoodItem | PracticeItem
    display: str = Field(max_length=300)
    caveats: list[str] = []


class TextData(_EventData):
    agent: AgentName | None = None
    summary: bool = False
    chunk: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _agent_or_summary(self):
        if (self.agent is None) == (not self.summary):
            raise ValueError("text is either for one agent or the holistic summary")
        return self


class SourcesData(_EventData):
    agent: AgentName
    sources: list[Source] = Field(min_length=1, max_length=5)


class SectionEndData(_EventData):
    agent: AgentName
    removed_count: int = Field(ge=0)
    decisions: list[Decision] = []


class PendingWriteData(_EventData):
    summary: str = Field(max_length=300)
    # Account mode
    write_id: str | None = None
    expires_at: datetime | None = None
    # Guest mode
    entry: StagedWrite | None = None
    profile_hash: str | None = None

    @model_validator(mode="after")
    def _one_mode(self):
        account = self.write_id is not None and self.expires_at is not None
        guest = self.entry is not None and self.profile_hash is not None
        if account == guest:
            raise ValueError(
                "needs write_id + expires_at (account) or entry + profile_hash (guest)"
            )
        return self


class CommittedWrite(_Model):
    kind: WriteKind
    summary: str = Field(max_length=300)
    write_id: str | None = None  # account
    entry: StagedWrite | None = None  # guest: for the browser to store


class CommittedData(_EventData):
    writes: list[CommittedWrite] = Field(min_length=1)


class Helpline(_Model):
    name: str
    region: str
    contact: str


class CrisisData(_EventData):
    text: str
    helplines: list[Helpline] = Field(min_length=1)


class NoticeData(_EventData):
    code: Literal["cap_reached", "search_off", "partial_result", "month_budget_used"]
    message: str = Field(max_length=300)


class ErrorData(_EventData):
    code: str = Field(max_length=40, pattern=_ID_PATTERN)
    message: str = Field(max_length=300)
    retry_after: int | None = Field(default=None, ge=0)


class DoneData(_EventData):
    trace: TraceView
    usage: Usage
    turn: HistoryTurn | None = None  # guest mode


def _event(name: str, data: type[_EventData]) -> type[_Model]:
    return type(
        f"{data.__name__.removesuffix('Data')}Event",
        (_Model,),
        {"__annotations__": {"event": Literal[name], "data": data}},
    )


EVENT_DATA: dict[str, type[_EventData]] = {
    "accepted": AcceptedData,
    "step": StepData,
    "section_start": SectionStartData,
    "item": ItemData,
    "text": TextData,
    "sources": SourcesData,
    "section_end": SectionEndData,
    "pending_write": PendingWriteData,
    "committed": CommittedData,
    "crisis": CrisisData,
    "notice": NoticeData,
    "error": ErrorData,
    "done": DoneData,
}
TERMINAL_EVENTS = frozenset({"done", "error"})
EVENT_MODELS = {name: _event(name, data) for name, data in EVENT_DATA.items()}


# One line of a stream: {"event": name, "data": {...}}
StreamEvent = Annotated[
    reduce(operator.or_, EVENT_MODELS.values()), Field(discriminator="event")
]
STREAM_EVENT = TypeAdapter(StreamEvent)


# --- Provider schema ---

# Keywords neither provider enforces in structured output (Plan Part D)
_UNENFORCED = ("maxLength", "minLength")


def llm_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The JSON Schema to send to a provider for an LLM model.

    $defs are inlined (Gemini documents only root references), nullable fields
    become {"type": [X, "null"]}, every object gets additionalProperties: false,
    and string lengths move into the description because neither provider
    enforces them. Pydantic still checks the lengths when the reply is parsed.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
            rest = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**target, **rest})
        # Nullable X: Gemini documents {"type": [X, "null"]}, not anyOf
        options = node.get("anyOf")
        if options and len(options) == 2 and {"type": "null"} in options:
            other = next(o for o in options if o != {"type": "null"})
            if isinstance(other.get("type"), str) and "$ref" not in other:
                rest = {k: v for k, v in node.items() if k != "anyOf"}
                return walk({**other, **rest, "type": [other["type"], "null"]})
        out = {k: walk(v) for k, v in node.items() if k not in _UNENFORCED}
        if node.get("type") in ("string", ["string", "null"]) and "maxLength" in node:
            limit = f"At most {node['maxLength']} characters."
            described = node.get("description")
            out["description"] = f"{described} {limit}" if described else limit
        if node.get("type") == "object":
            out["additionalProperties"] = False
        return out

    result = walk(schema)
    result.pop("title", None)
    return result
