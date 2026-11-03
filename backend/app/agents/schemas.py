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

from app.config.limits import IMPORT_LOG_ENTRIES, IMPORT_TURNS
from app.guardrails.loader import get_guardrails
from app.guardrails.types import Allergen, Diet

CONTRACT_VERSION = 1

_catalogue = get_guardrails().catalogue

# Enums built from catalogue.yaml, so the model can only return known IDs
ExerciseId = StrEnum("ExerciseId", {i: i for i in _catalogue.exercise_ids})
PracticeId = StrEnum("PracticeId", {i: i for i in _catalogue.practice_ids})

ReplyKind = Literal["plan", "answer", "log_ack", "clarify"]
AgentName = Literal["physical", "nutrition", "mental"]
# What a turn was (C.15). coaching: the coaches in `agents` answer; every other kind is
# answered by the router's own reply, no coach (Part E #36)
TurnKind = Literal["coaching", "greeting", "meta", "off_topic", "unclear", "other_language"]
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

# A plan over several days labels each item with its day (owner, Part E #38): relative
# days, not dates. Grouped by it in the app; the gate checks every item as before
DAY = Field(max_length=16, description=(
    "Only in a plan over several days: the day or meal this item belongs to, for example "
    "'Mon', 'Day 2', 'Daily' or 'Tue lunch'; null otherwise."))


# Owner, 2 Nov 2026 (Part E #38): a marathon long run, a long ride or an Ironman day runs
# for hours; any other exercise at most 90 minutes. The ceiling only stops impossible
# numbers.
ENDURANCE_IDS = frozenset({"walking", "brisk_walking", "hiking", "jogging", "running",
                           "long_distance_running", "cycling", "stationary_cycling",
                           "rowing_machine", "elliptical", "swimming"})
DURATION_MAX_S = 5400
ENDURANCE_MAX_S = 86400
DURATION_RULE = ("Seconds. At most 5400 (90 minutes), except walking, hiking, jogging, "
                 "running, cycling, rowing, elliptical and swimming, which may be longer.")


class ExerciseItem(_LLMModel):
    day: str | None = DAY
    catalogue_id: ExerciseId
    sets: int | None = Field(ge=1, le=10)
    reps: int | None = Field(ge=1, le=100)
    duration_s: int | None = Field(ge=1, le=ENDURANCE_MAX_S, description=DURATION_RULE)
    intensity: Intensity
    note: str = Field(max_length=120, description="At most 120 characters.")

    @model_validator(mode="after")
    def _duration_fits_the_exercise(self):
        _check_duration(self.catalogue_id, self.duration_s)
        return self


def _check_duration(catalogue_id: str, duration_s: int | None) -> None:
    if (duration_s or 0) > DURATION_MAX_S and catalogue_id not in ENDURANCE_IDS:
        raise ValueError(f"{catalogue_id} lasts at most {DURATION_MAX_S} s")


class PracticeItem(_LLMModel):
    day: str | None = DAY
    catalogue_id: PracticeId
    duration_min: int = Field(ge=1, le=60)
    note: str = Field(max_length=120, description="At most 120 characters.")


class FoodItem(_LLMModel):
    day: str | None = DAY  # null in a meal log
    name: str = Field(max_length=60, description="The dish, at most 60 characters.")
    # Gemini doesn't enforce item counts and OpenAI doesn't enforce string lengths
    # (Part D): the descriptions are how the model learns these limits
    ingredients: list[Annotated[str, Field(max_length=30)]] = Field(
        min_length=1, max_length=8,
        description="1 to 8 main ingredients, in English, each at most 30 characters.")
    allergen_tags: list[Allergen] = Field(max_length=len(Allergen))
    diet_tags: list[Diet] = Field(max_length=len(Diet))
    portion: str = Field(max_length=80, description=(
        "At most 80 characters, for example '1 bowl (250 g)' or '2 rotis, 1 cup dal'."))
    calories: float | None = Field(ge=0, le=5000)
    note: str = Field(max_length=120, description="At most 120 characters.")


MACRO_MAX_G = 500  # per food: stops impossible numbers only
# 4P + 4C + 9F may pass the stated calories by this much (rounding, fibre counted as
# carbs); the worst of 32 live foods was +10% (Part D, P4.8)
ENERGY_SLACK = 1.25
ENERGY_FLOOR_KCAL = 30
_MACRO = ("Grams of {} in this portion, your best estimate; null only if you can't "
          "estimate it.")


class LoggedFood(FoodItem):
    """A food in a meal log, with its protein, carbs and fat, so the person can track
    them (owner, 3 Nov 2026, Part E #44). Plans and photo replies keep FoodItem."""

    protein_g: float | None = Field(ge=0, le=MACRO_MAX_G, description=_MACRO.format("protein"))
    carbs_g: float | None = Field(ge=0, le=MACRO_MAX_G,
                                  description=_MACRO.format("carbohydrate"))
    fat_g: float | None = Field(ge=0, le=MACRO_MAX_G, description=_MACRO.format("fat"))

    @model_validator(mode="after")
    def _macros_fit_the_calories(self):
        """Protein, carbs and fat can't hold more energy than the food. Less is fine:
        alcohol has energy of its own (live, two pints of lager: 430 kcal stated, 160
        from the macros); 30 of 32 live foods were within 10% (Part D, P4.8)."""
        amounts = (self.calories, self.protein_g, self.carbs_g, self.fat_g)
        if any(a is None for a in amounts):
            return self
        energy = 4 * self.protein_g + 4 * self.carbs_g + 9 * self.fat_g
        if energy > self.calories * ENERGY_SLACK + ENERGY_FLOOR_KCAL:
            raise ValueError(
                f"{self.name}: protein, carbs and fat give about {round(energy)} kcal, more "
                f"than the {round(self.calories)} kcal stated; correct the numbers")
        return self


# --- Replies (C.3) ---

# A week plan fits (Part E #38: 30 of 44 live week plans complete, 16 of 44 at 8/5/5;
# 30 exercises for a 6-day split, owner, 2 Nov 2026)
PLAN_MAX_ITEMS = {"PhysicalReply": 30, "NutritionReply": 21, "MentalReply": 14}

# Output tokens for the reply itself, per agent (Plan C.9), sized to the week-plan item
# limits (Part E #38): the largest valid reply must fit in the cap minus
# SIZE_RULE_MARGIN, so a reply is never cut off.
REPLY_TOKEN_CAP = {"physical": 2400, "nutrition": 5000, "mental": 1200}
SIZE_RULE_MARGIN = 100


class _ReplyBase(_LLMModel):
    # Descriptions reach the model through the JSON Schema; they state the rules the
    # validator below enforces, so fewer replies fail and need a retry.
    kind: ReplyKind = Field(description=(
        "plan: concrete items to do; answer: an information reply; log_ack: confirms a log; "
        "clarify: ask one question first."))
    summary: str = Field(max_length=400, description=(
        "Short plain-text reply to the user, at most 400 characters."))
    notes: list[Annotated[str, Field(max_length=200)]] = Field(
        max_length=3, description="Up to 3 short tips or cautions, each at most 200 characters.")
    source_ids: list[Annotated[str, Field(max_length=20)]] = Field(
        max_length=5, description="Only ids of this turn's web search results; else empty.")
    follow_up: str | None = Field(
        max_length=200, description=(
            "The question to ask, at most 200 characters. Null unless kind is clarify."))
    risk_flag: bool = Field(
        description="True if the user may be at risk of self-harm or in a medical emergency.")

    @model_validator(mode="after")
    def _kind_matches_content(self):
        # The content decides, so a reply isn't failed and retried over its label (live,
        # 3 in 378 coach replies, Part D): items make it a plan, a plan without items is
        # an answer, and only a clarify asks a follow-up question
        if self.items and self.kind != "plan":  # type: ignore[attr-defined]
            self.kind = "plan"
        elif not self.items and self.kind == "plan":  # type: ignore[attr-defined]
            self.kind = "answer"
        if self.kind != "clarify":
            self.follow_up = None
        return self


class PhysicalReply(_ReplyBase):
    items: list[ExerciseItem] = Field(
        max_length=30, description="1 to 30 items when kind is plan; empty otherwise.")


class NutritionReply(_ReplyBase):
    # A meal photo's foods are items (kind plan): live, 12 of 12 replies listed them with
    # these descriptions, 0 of 12 without (Part D, Part E #29)
    kind: ReplyKind = Field(description=(
        "plan: concrete food items, either a plan to follow or the foods seen in a meal photo; "
        "answer: an information reply; log_ack: confirms a log; clarify: ask one question "
        "first."))
    items: list[FoodItem] = Field(max_length=21, description=(
        "1 to 21 items when kind is plan, including each food seen in a photo; empty "
        "otherwise."))


class MentalReply(_ReplyBase):
    items: list[PracticeItem] = Field(
        max_length=14, description="1 to 14 items when kind is plan; empty otherwise.")


AgentReply = PhysicalReply | NutritionReply | MentalReply  # backend only, never sent to an LLM
# --- Router reply (C.15) ---

ROUTER_REPLY_CHARS = 400


class RouterReply(_LLMModel):
    """The router's one call: the coaches to call, or Holos's own short reply."""

    kind: TurnKind = Field(description=(
        "coaching: the user wants advice, a plan, an answer or to log something about "
        "exercise, food or mental wellbeing. greeting: a hello, thanks or goodbye. meta: a "
        "question about Holos itself. off_topic: anything outside exercise, food and mental "
        "wellbeing. unclear: you can't tell what they want. other_language: the message is "
        "not in English, Hindi or Hinglish."))
    agents: list[AgentName] = Field(max_length=3, description=(
        "Every coach the request needs and only those: physical (exercise, training, "
        "movement, sport, pain during exercise), nutrition (food, meals, diet, drinks, "
        "supplements), mental (stress, mood, anxiety, sleep, motivation, focus, emotions). "
        "Empty unless kind is coaching."))
    reply: str | None = Field(max_length=ROUTER_REPLY_CHARS, description=(
        "Your own short reply, at most 400 characters. Null when kind is coaching."))

    @model_validator(mode="after")
    def _agents_or_reply(self):
        # The kind decides; a stray reply or stray agents are dropped, not a failure
        # (live: "coaching" with agents and a reply, 1 in 215)
        _unique(self.agents)
        if self.kind == "coaching":
            if not self.agents:
                raise ValueError("coaching needs agents")
            self.reply = None
        else:
            if not (self.reply or "").strip():
                raise ValueError(f"kind '{self.kind}' needs a reply")
            self.agents = []
        return self


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
    # As a plan's item: a logged long run may last hours (Part E #38)
    duration_s: int | None = Field(ge=1, le=ENDURANCE_MAX_S, description=DURATION_RULE)
    note: str = Field(max_length=120)

    @model_validator(mode="after")
    def _duration_fits_the_exercise(self):
        _check_duration(self.catalogue_id, self.duration_s)
        return self


class LogMealArgs(_LLMModel):
    meal: Literal["breakfast", "lunch", "dinner", "snack"]
    foods: list[LoggedFood] = Field(min_length=1, max_length=5)

    def totals(self) -> dict[str, float | bool | None]:
        """The meal's calories and macros: each the sum over the foods that give it
        (None if none does); `complete` only when every food gives all four."""
        out: dict[str, float | bool | None] = {}
        for name in ("calories", "protein_g", "carbs_g", "fat_g"):
            known = [getattr(f, name) for f in self.foods if getattr(f, name) is not None]
            out[name] = round(sum(known), 1) if known else None
        out["complete"] = all(getattr(f, n) is not None for f in self.foods
                              for n in ("calories", "protein_g", "carbs_g", "fat_g"))
        return out


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


def _unique(agents: list[str] | None) -> None:
    if agents is not None and len(set(agents)) != len(agents):
        raise ValueError("agents must not repeat")


class HistoryTurn(_Model):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)
    agents: list[AgentName] | None = Field(default=None, max_length=3)  # who answered
    ts: datetime

    @model_validator(mode="after")
    def _agents_on_assistant_only(self):
        if self.role == "user" and self.agents is not None:
            raise ValueError("agents are only set on assistant turns")
        _unique(self.agents)
        return self


class ChatPayload(_Model):
    # min_length rejects a blank message before any paid call (red-team finding, Part E #9)
    message: str = Field(min_length=1, max_length=2000)
    # Coaches chosen in the app: routing is skipped, not the crisis check
    agents: list[AgentName] | None = Field(default=None, min_length=1, max_length=3)
    guest_profile: UserProfile | None = None
    guest_history: list[HistoryTurn] | None = Field(default=None, max_length=6)
    client_request_id: UUID
    contract_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _not_blank(self):
        if not self.message.strip():
            raise ValueError("message is blank")
        _unique(self.agents)
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


class WriteWarning(_Model):
    """What in a logged entry conflicts with the profile, kept with the log row (owner,
    3 Nov 2026, Part E #45). `conflict`: a rule fired, so the entry waits for the
    person's confirmation; `unchecked`: ingredients the gate couldn't check, recorded
    only. `left_out`: the person said at confirm that they didn't have it (the peanuts
    picked out of the poha)."""

    kind: Literal["conflict", "unchecked"]
    item: str = Field(max_length=60)  # the food or exercise
    rule_id: str = Field(max_length=40)
    attributes: list[Annotated[str, Field(max_length=40)]] = Field(max_length=10)
    reason: str = Field(max_length=200)
    left_out: bool = False


class StagedWrite(_Model):
    kind: WriteKind
    args: LogWorkoutArgs | LogMealArgs | LogPracticeArgs
    warnings: list[WriteWarning] = Field(default=[], max_length=20)

    @property
    def conflicts(self) -> list[WriteWarning]:
        return [w for w in self.warnings if w.kind == "conflict"]

    @model_validator(mode="after")
    def _args_match_kind(self):
        if not isinstance(self.args, WRITE_ARGS[self.kind]):
            raise ValueError(f"args don't match kind '{self.kind}'")
        return self


AgentError = Literal["busy", "cap_reached", "unavailable", "malformed"]


class AgentResult(_Model):
    reply: AgentReply | None  # None: the coach failed (`error`); the app offers Retry
    warnings: list[str] = []
    removed_count: int = Field(default=0, ge=0)  # items the gate removed (C.5 section_end)
    item_caveats: list[list[str]] = []  # per item of reply.items (C.5 `item` caveats)
    decisions: list[Decision] = []
    sources: list[Source] = []
    staged_writes: list[StagedWrite] = []
    # Set when there is no reply: the stream's notice or error (C.5)
    error: AgentError | None = None


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
    status: Literal["ok", "error", "refused", "staged", "held", "unavailable"]


class TraceView(_Model):
    trace_id: str = Field(max_length=64)
    route: TurnKind | Literal["crisis"]
    agents: list[AgentName] = Field(default=[], max_length=3)
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
        "admitted", "routed", "agent_started", "tool_call", "gate", "retry", "composing",
        "still_working",
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
    """One coach's text, the multi-coach summary, or neither: Holos's own reply."""

    agent: AgentName | None = None
    summary: bool = False
    chunk: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _agent_or_summary(self):
        if self.agent is not None and self.summary:
            raise ValueError("text is for one agent or the summary, not both")
        return self


class SourcesData(_EventData):
    agent: AgentName
    sources: list[Source] = Field(min_length=1, max_length=5)


class SectionEndData(_EventData):
    agent: AgentName
    removed_count: int = Field(ge=0)
    decisions: list[Decision] = []
    warnings: list[Annotated[str, Field(max_length=400)]] = []
    error: AgentError | None = None  # the coach failed: no section_start came before


class ConfirmWrite(_Model):
    """POST /agents/writes/{id}/confirm, body optional: the attributes from the
    `pending_write` event the person didn't have (Part E #45)."""

    left_out: list[Annotated[str, Field(max_length=40)]] = Field(default=[], max_length=10)


class ImportLog(_Model):
    """A guest's stored log entry (C.17 `committed` or a confirmed `pending_write`) and
    when it happened. Parsed one by one at import, so a bad entry is skipped, not fatal."""

    entry: StagedWrite
    at: datetime


class ImportPayload(_Model):
    """POST /account/import (C.18). Logs are read one by one (ImportLog)."""

    import_id: UUID
    profile: UserProfile | None = None
    history: list[HistoryTurn] = Field(default=[], max_length=IMPORT_TURNS)
    logs: list[dict[str, Any]] = Field(default=[], max_length=IMPORT_LOG_ENTRIES)


class ProfileNotes(_Model):
    """POST /profile/check: a guest's notes, checked and not stored (Part E #42)."""

    notes: str = Field(max_length=1000)


class PendingWriteData(_EventData):
    summary: str = Field(max_length=300)
    # What to confirm: each conflict as text, and the attributes the person may say they
    # left out (Part E #45); empty when only a web search holds the write
    warnings: list[Annotated[str, Field(max_length=300)]] = []
    attributes: list[Annotated[str, Field(max_length=40)]] = []
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
    warnings: list[Annotated[str, Field(max_length=300)]] = []  # as logged, left-outs too


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
