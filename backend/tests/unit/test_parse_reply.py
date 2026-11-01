"""parse_reply: over-long text is trimmed, not failed (Part D: 13 of 378 coach replies)."""

import json

import pytest

from app.agents.schemas import MentalReply, NutritionReply, RouterReply
from app.providers.base import MalformedOutput, parse_reply, trim

pytestmark = pytest.mark.unit


def _mental(**kw):
    data = dict(kind="answer", summary="ok", items=[], notes=[], source_ids=[],
                follow_up=None, risk_flag=False)
    return json.dumps({**data, **kw})


@pytest.mark.parametrize(("text", "limit", "trimmed"), [
    ("Short.", 40, "Short."),
    ("Breathe slowly for five minutes. Then stretch your neck and relax.", 40,
     "Breathe slowly for five minutes."),
    ("Rest. Then stretch your neck gently and relax your shoulders.", 40,
     "Rest. Then stretch your neck gently…"),  # the sentence end would keep < half
    ("Breathe slowly for five minutes and then stretch", 40,
     "Breathe slowly for five minutes and…"),
    ("x" * 50, 40, "x" * 39 + "…"),
    ("आराम से साँस लें। फिर गर्दन को धीरे से घुमाएँ और कंधों को ढीला छोड़ें।", 30,
     "आराम से साँस लें।"),
])
def test_trim(text, limit, trimmed):
    assert trim(text, limit) == trimmed and len(trimmed) <= limit


def test_over_long_notes_and_summary_are_trimmed():
    reply = parse_reply(_mental(summary="Calm down. " * 50, notes=["Do this. " * 40]),
                        MentalReply, "openai")
    assert len(reply.summary) <= 400 and reply.summary.endswith(".")
    assert len(reply.notes[0]) <= 200


def test_an_over_long_field_in_an_item_is_trimmed():
    food = {"day": None, "name": "Dal", "ingredients": ["lentils"], "allergen_tags": [],
            "diet_tags": [], "portion": "1 large bowl of dal with rice, 2 rotis, a side of "
                                        "cucumber salad and a glass of buttermilk",
            "calories": 400, "note": ""}
    data = dict(kind="plan", summary="ok", items=[food], notes=[], source_ids=[],
                follow_up=None, risk_flag=False)
    reply = parse_reply(json.dumps(data), NutritionReply, "openai")
    assert len(reply.items[0].portion) <= 80


def test_the_router_reply_is_trimmed_too():
    data = {"kind": "greeting", "agents": [], "reply": "Hello there, good to see you. " * 20}
    assert len(parse_reply(json.dumps(data), RouterReply, "openai").reply) <= 400


@pytest.mark.parametrize("text", [
    "", "{", _mental(kind="chat"), _mental(summary="x" * 500, risk_flag="maybe"),
    json.dumps({"kind": "coaching", "agents": [], "reply": None}),
])
def test_other_errors_still_fail(text):
    schema = RouterReply if "agents" in text else MentalReply
    with pytest.raises(MalformedOutput):
        parse_reply(text, schema, "openai")
