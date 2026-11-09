"""Contracts: LLM schemas meet provider rules, replies fit the size rule, and the
sample streams, crisis cases and generated files are valid and up to date (Plan P1.2).
"""

import json
from pathlib import Path

import pytest
import tiktoken
from pydantic import BaseModel, ValidationError

from app.agents import schemas
from app.contracts import generate
from app.guardrails.types import Allergen, Diet

pytestmark = pytest.mark.contract

CONTRACTS = generate.CONTRACTS_DIR
STREAMS = CONTRACTS / "streams"
REQUIRED_STREAMS = {
    "plan_single", "holistic", "blocked_and_retried", "pending_write",
    "crisis", "cap_reached", "search_off", "error_mid_stream", "coach_failed", "own_reply",
    "risk_flag",
}
LLM_IDS = [m.__name__ for m in schemas.LLM_MODELS]

# Keywords both providers document for structured output (Part D, 25 Oct 2026)
PROVIDER_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items", "enum",
    "description", "title", "minimum", "maximum", "minItems", "maxItems",
}


# --- Helpers ---


def _resolve(schema: dict) -> tuple[dict, dict]:
    return schema, schema.get("$defs", {})


def _walk_objects(node, defs, depth=0, seen=()):
    """Yield (object_schema, depth) for every object, following $refs once."""
    if isinstance(node, list):
        for n in node:
            yield from _walk_objects(n, defs, depth, seen)
        return
    if not isinstance(node, dict):
        return
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        assert name not in seen, f"recursive reference to {name}"
        yield from _walk_objects(defs[name], defs, depth, (*seen, name))
        return
    if node.get("type") == "object":
        depth += 1
        yield node, depth
    for key, value in node.items():
        if key != "$defs":
            yield from _walk_objects(value, defs, depth, seen)


def _walk(node):
    """Every dict in a schema."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _is_nullable_pair(options: list) -> bool:
    return len(options) == 2 and {"type": "null"} in options


# --- LLM models meet the provider rules (C.3) ---


@pytest.mark.parametrize("model", schemas.LLM_MODELS, ids=LLM_IDS)
def test_llm_model_rules(model: type[BaseModel]):
    schema, defs = _resolve(model.model_json_schema())
    depths = []
    for obj, depth in _walk_objects(schema, defs):
        depths.append(depth)
        props = set(obj.get("properties", {}))
        assert set(obj.get("required", [])) == props, f"{model.__name__}: every field required"
    assert max(depths) <= 3, f"{model.__name__}: depth {max(depths)} > 3"

    for node in _walk(schema):
        assert "oneOf" not in node and "allOf" not in node
        if "anyOf" in node:
            assert _is_nullable_pair(node["anyOf"]), f"{model.__name__}: only nullable unions"
        if node.get("type") == "string" and "enum" not in node:
            assert "maxLength" in node, f"{model.__name__}: string without maxLength: {node}"
        assert "default" not in node, f"{model.__name__}: LLM fields have no defaults"


def _schema_nodes(node: dict):
    """Every schema node: the root, property values, array items and anyOf options."""
    yield node
    for child in (node.get("properties") or {}).values():
        yield from _schema_nodes(child)
    if isinstance(node.get("items"), dict):
        yield from _schema_nodes(node["items"])
    for option in node.get("anyOf", []):
        yield from _schema_nodes(option)


@pytest.mark.parametrize("model", schemas.LLM_MODELS, ids=LLM_IDS)
def test_provider_schema_uses_supported_keywords_only(model):
    schema = schemas.llm_json_schema(model)
    assert "$defs" not in schema
    for node in _schema_nodes(schema):
        unsupported = set(node) - PROVIDER_KEYWORDS
        assert not unsupported, f"{model.__name__}: unsupported keywords {unsupported}"
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False


@pytest.mark.parametrize("model", schemas.LLM_MODELS, ids=LLM_IDS)
def test_provider_limits(model):
    """OpenAI: 5000 properties, 10 levels, 1000 enum values, 120,000 characters (Part D)."""
    schema = schemas.llm_json_schema(model)
    nodes = list(_schema_nodes(schema))
    enum_values = [v for n in nodes for v in n.get("enum", [])]
    props = [p for n in nodes for p in (n.get("properties") or {})]
    assert len(props) <= 5000
    assert len(enum_values) <= 1000
    for n in nodes:
        if len(n.get("enum", [])) > 250:
            assert sum(len(str(v)) for v in n["enum"]) <= 15000
    assert sum(len(str(v)) for v in enum_values) + sum(len(p) for p in props) <= 120_000


def test_lengths_still_enforced_after_parse():
    """The provider schema drops maxLength, so Pydantic must reject long text."""
    with pytest.raises(ValidationError, match="at most 400 characters"):
        schemas.MentalReply(kind="answer", summary="x" * 401, items=[], notes=[],
                            source_ids=[], follow_up=None, risk_flag=False)


def test_unknown_catalogue_id_is_malformed():
    with pytest.raises(ValidationError):
        schemas.ExerciseItem(day=None, catalogue_id="bulgarian_death_squat", sets=3, reps=10,
                             duration_s=None, intensity="high", note="")


@pytest.mark.parametrize(("exercise", "seconds", "ok"), [
    ("long_distance_running", 3 * 3600, True),  # a marathon long run (owner, 2 Nov 2026)
    ("cycling", 86400, True), ("cycling", 86401, False),
    ("plank", 5400, True), ("plank", 5401, False), ("circuit_training", 4 * 3600, False),
])
def test_only_endurance_exercises_last_over_90_minutes(exercise, seconds, ok):
    def item():
        return schemas.ExerciseItem(day=None, catalogue_id=exercise, sets=None, reps=None,
                                    duration_s=seconds, intensity="low", note="")

    def log():  # the same rule when the person logs it
        return schemas.LogWorkoutArgs(catalogue_id=exercise, sets=None, reps=None,
                                      duration_s=seconds, note="")
    for make in (item, log):
        if ok:
            assert make().duration_s == seconds
        else:
            with pytest.raises(ValidationError):
                make()


@pytest.mark.parametrize(
    ("kind", "items", "follow_up", "kind_after", "follow_up_after"),
    [("plan", 0, None, "answer", None), ("plan", 1, None, "plan", None),
     ("answer", 1, None, "plan", None), ("answer", 0, None, "answer", None),
     ("clarify", 0, "Which knee?", "clarify", "Which knee?"), ("answer", 0, "?", "answer", None),
     ("clarify", 1, "?", "plan", None), ("log_ack", 0, None, "log_ack", None)],
)
def test_the_content_decides_the_reply_kind(kind, items, follow_up, kind_after,
                                             follow_up_after):
    # Repaired, not failed (live, 3 in 378 coach replies, Part D)
    item = {"day": None, "catalogue_id": "box_breathing", "duration_min": 5, "note": ""}
    reply = schemas.MentalReply(kind=kind, summary="s", items=[item] * items, notes=[],
                                source_ids=[], follow_up=follow_up, risk_flag=False)
    assert (reply.kind, reply.follow_up) == (kind_after, follow_up_after)


# --- Size rule (C.3): largest valid reply fits the agent's cap minus the margin ---

_WORDS = "the quick brown fox jumps over a lazy dog with steady breathing and good form".split()


def _text(n: int) -> str:
    out, i = "", 0
    while len(out) < n:
        out += _WORDS[i % len(_WORDS)] + " "
        i += 1
    return out[:n]


def _largest(model: type[schemas._ReplyBase]) -> BaseModel:
    longest = lambda e: max(e, key=lambda m: len(m.value))  # noqa: E731
    items = {
        "PhysicalReply": dict(day=_text(16), catalogue_id=longest(schemas.ExerciseId),
                              # The longest ID beats an endurance one with 86400 s (measured)
                              sets=10, reps=100, duration_s=schemas.DURATION_MAX_S,
                              intensity="moderate",
                              note=_text(120)),
        "NutritionReply": dict(day=_text(16), name=_text(60), ingredients=[_text(30)] * 8,
                               allergen_tags=list(Allergen), diet_tags=list(Diet),
                               portion=_text(80), calories=4999.5, note=_text(120)),
        "MentalReply": dict(day=_text(16), catalogue_id=longest(schemas.PracticeId),
                            duration_min=60, note=_text(120)),
    }[model.__name__]
    return model(kind="plan", summary=_text(400), notes=[_text(200)] * 3,
                 source_ids=[_text(20)] * 5, follow_up=None, risk_flag=True,
                 items=[items] * schemas.PLAN_MAX_ITEMS[model.__name__])


@pytest.mark.parametrize("agent", list(schemas.REPLY_MODELS))
def test_largest_reply_fits_size_rule(agent):
    # o200k_base is the OpenAI tokenizer; Gemini has none offline (Part E #10)
    model = schemas.REPLY_MODELS[agent]
    tokens = len(tiktoken.get_encoding("o200k_base").encode(_largest(model).model_dump_json()))
    limit = schemas.REPLY_TOKEN_CAP[agent] - schemas.SIZE_RULE_MARGIN
    assert tokens <= limit, f"{agent}: {tokens} tokens > {limit}"


@pytest.mark.parametrize("agent", list(schemas.REPLY_MODELS))
def test_gemini_gets_no_item_limit_on_lists_of_items(agent):
    # Live, 2 Nov 2026: "too many states for serving" with maxItems 21 foods or 24
    # exercises; the description still states the limit and Pydantic enforces it
    from app.providers.gemini import gemini_schema
    props = gemini_schema(schemas.REPLY_MODELS[agent])["properties"]
    assert "maxItems" not in props["items"] and "to " in props["items"]["description"]
    assert "maxItems" not in json.dumps(props["items"]["items"])
    assert (props["notes"]["maxItems"], props["source_ids"]["maxItems"]) == (3, 5)


@pytest.mark.parametrize("model", schemas.LLM_MODELS, ids=LLM_IDS)
def test_a_nullable_choice_can_be_null(model):
    """Live, 9 Nov 2026: `when.part` was sent as [string, null] with an enum without
    null, so the coach had to pick a part of the day for "log my walk" (Part E #51).
    Both providers accepted null in the enum live (9 Nov 2026)."""
    for node in _schema_nodes(schemas.llm_json_schema(model)):
        if "enum" in node and isinstance(node.get("type"), list):
            assert None in node["enum"], f"{model.__name__}: {node}"


# --- Sample streams (C.4, C.5) ---


def _stream(name: str) -> list[dict]:
    return [json.loads(line) for line in (STREAMS / f"{name}.jsonl").read_text().splitlines()]


def test_required_streams_exist():
    assert {p.stem for p in STREAMS.glob("*.jsonl")} >= REQUIRED_STREAMS


@pytest.mark.parametrize("name", sorted(REQUIRED_STREAMS))
def test_every_line_validates(name):
    for i, line in enumerate(_stream(name)):
        try:
            schemas.STREAM_EVENT.validate_python(line)
        except ValidationError as exc:
            pytest.fail(f"{name}.jsonl line {i + 1}: {exc}")


@pytest.mark.parametrize("name", sorted(REQUIRED_STREAMS))
def test_one_terminal_event_and_seq_increases(name):
    events = _stream(name)
    terminal = [e for e in events if e["event"] in schemas.TERMINAL_EVENTS]
    assert len(terminal) == 1 and events[-1] is terminal[0], "exactly one terminal event, last"
    seqs = [e["data"]["seq"] for e in events]
    assert seqs == sorted(set(seqs)), "seq strictly increases"
    assert len({e["data"]["trace_id"] for e in events}) == 1
    assert events[0]["event"] == "accepted"


def test_crisis_stream_shape():
    assert [e["event"] for e in _stream("crisis")] == ["accepted", "crisis", "done"]


def test_samples_cover_every_event():
    seen = {e["event"] for name in REQUIRED_STREAMS for e in _stream(name)}
    assert seen == set(schemas.EVENT_DATA)


def test_bad_event_rejected():
    with pytest.raises(ValidationError):
        schemas.STREAM_EVENT.validate_python(
            {"event": "text", "data": {"seq": 0, "trace_id": "t", "agent": "physical",
                                       "summary": True, "chunk": "x"}}
        )


# --- Crisis cases and generated files (C.4) ---


def test_crisis_cases_shape():
    lines = (CONTRACTS / "crisis_cases.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines]
    assert len(cases) >= 30
    for case in cases:
        assert set(case) == {"text", "expect", "note"}
        assert isinstance(case["expect"], bool) and case["text"].strip()
    assert any(c["expect"] for c in cases) and any(not c["expect"] for c in cases)


def test_generated_contracts_match_committed():
    """Drift check: run `python -m app.contracts.generate` and commit the result."""
    for rel, content in generate.build().items():
        path = CONTRACTS / rel
        assert path.exists(), f"missing contracts/{rel}"
        assert path.read_text(encoding="utf-8") == content, f"contracts/{rel} is out of date"
    expected = set(generate.build())
    on_disk = {str(p.relative_to(CONTRACTS)) for p in (CONTRACTS / "schema").rglob("*.json")}
    assert on_disk == {r for r in expected if r.startswith("schema/")}, "stale schema files"


def test_contracts_dir_is_repo_root():
    assert (Path(generate.CONTRACTS_DIR).parent / "backend").is_dir()
