"""The mention reader (Part E #59): what each sentence recommends, read by a small model
and handed to the gate; a failure leaves the gate its word lists."""

import time

import pytest

from app.agents.schemas import UserProfile
from app.config.speeds import READER
from app.guardrails.gate import read_key
from app.observability.tracer import Trace
from app.orchestration.reader import (
    ITEMS,
    PROMPT,
    ReaderMention,
    ReaderReply,
    ReaderSentence,
    needs_reading,
    read_mentions,
)
from app.orchestration.services import READER_OPTIONS
from app.providers import (
    Breakers,
    CallPlan,
    FakeProvider,
    LLMResult,
    MalformedOutput,
    ProviderUnavailable,
    ResilientProvider,
    Route,
    Usage,
)
from app.providers.fake import Slow

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _answer(*sentences: list[tuple[str, str]]) -> LLMResult:
    reply = ReaderReply(sentences=[
        ReaderSentence(n=n, mentions=[ReaderMention(item=i, stance=s) for i, s in mentions])
        for n, mentions in enumerate(sentences, 1)])
    return LLMResult(provider="openai", model="m", parsed=reply, text=reply.model_dump_json(),
                     usage=Usage(6900, 35))


async def _read(*script, texts=("आज रात 12 स्क्वाट करें। Avoid lunges.",)):
    fake = FakeProvider(list(script), name="openai")
    llm = ResilientProvider(Route(fake, READER_OPTIONS), None, Breakers())
    trace = Trace("t")
    plan = CallPlan(deadline=time.monotonic() + 5, speed=READER, principal="p", kind="reader",
                    trace=trace)
    return await read_mentions(llm, plan, list(texts)), fake, trace


async def test_only_what_a_sentence_recommends_is_handed_on():
    read, fake, trace = await _read(_answer([("bodyweight_squat", "recommends")],
                                            [("forward_lunge", "warns_against")]))
    assert read == {read_key("आज रात 12 स्क्वाट करें।"): ("bodyweight_squat",),
                    read_key("Avoid lunges."): ()}
    assert fake.calls[0].messages[-1].text == "1. आज रात 12 स्क्वाट करें।\n2. Avoid lunges."
    assert fake.calls[0].system == PROMPT
    assert [s.name for s in trace.steps] == ["reader"]


async def test_the_trace_step_spans_the_read():
    _, _, trace = await _read(Slow(0.2, _answer([], [])))
    assert trace.steps[0].duration_ms >= 190


async def test_a_neutral_mention_is_left_to_the_word_lists():
    read, _, _ = await _read(_answer([("peanut", "neutral")]),
                             texts=["Your chikki waits on the card below."])
    assert read == {read_key("Your chikki waits on the card below."): ()}


async def test_the_sentences_are_the_ones_the_gate_judges():
    _, fake, _ = await _read(_answer([], []),
                             texts=["See https://x.com now. Rest well.", "Rest well."])
    assert fake.calls[0].messages[-1].text == "1. See  now.\n2. Rest well."


async def test_a_malformed_answer_is_asked_once_more():
    read, fake, _ = await _read(MalformedOutput("extra data", "openai"),
                                _answer([("bodyweight_squat", "recommends")], []))
    assert read[read_key("आज रात 12 स्क्वाट करें।")] == ("bodyweight_squat",)
    assert len(fake.calls) == 2


async def test_twice_malformed_leaves_the_word_lists():
    read, fake, trace = await _read(MalformedOutput("a", "openai"), MalformedOutput("b", "openai"))
    assert read is None and len(fake.calls) == 2
    assert [(s.name, s.outcome) for s in trace.steps] == [("reader", "malformed")]


async def test_a_failed_read_leaves_the_word_lists():
    down = ProviderUnavailable("down", "openai")
    read, _, trace = await _read(down, down, down, down)
    assert read is None and trace.steps[-1].name == "reader"


async def test_nothing_to_read_costs_nothing():
    read, fake, _ = await _read(texts=["", "   "])
    assert read == {} and fake.calls == []


@pytest.mark.parametrize("profile, reads", [
    (None, False),
    (UserProfile(condition_ids=[], allergen_tags=[], diet_tags=[], notes=""), False),
    (UserProfile(condition_ids=["asthma"], allergen_tags=[], diet_tags=[], notes=""), True),
    (UserProfile(condition_ids=[], allergen_tags=["peanut"], diet_tags=[], notes=""), True),
    (UserProfile(condition_ids=[], allergen_tags=[], diet_tags=["vegan"], notes=""), True),
])
def test_only_a_profile_with_something_to_protect_is_read(profile, reads):
    assert needs_reading(profile) is reads


def test_the_prompt_lists_every_item_the_answer_may_name():
    catalogue = PROMPT[PROMPT.index("CATALOGUE (id"):]
    assert all(item in catalogue for item in ITEMS)
