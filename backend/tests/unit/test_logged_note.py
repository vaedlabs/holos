"""The coach's sentence about what was just saved (Part E #54 B): sent only when it comes
in time, whole and safe; any failure sends nothing, since the record said it."""

import asyncio
import logging
import time
from datetime import UTC, datetime

import pytest

from app.agents.clock import zone
from app.agents.schemas import (
    LoggedFood,
    LogMealArgs,
    LogWorkoutArgs,
    StagedWrite,
    UserProfile,
    WriteWarning,
)
from app.config.speeds import LOGGED_NOTE
from app.orchestration.logged_note import logged_note, note_prompt
from app.orchestration.services import SUMMARY_OPTIONS
from app.providers import (
    Breakers,
    CallPlan,
    FakeProvider,
    LLMResult,
    ProviderUnavailable,
    ResilientProvider,
    Route,
)
from app.providers.fake import Slow

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

AT = datetime(2026, 11, 9, 4, 0, tzinfo=UTC)
INDIA = zone("Asia/Kolkata")
WALK = StagedWrite(kind="workout", args=LogWorkoutArgs(
    catalogue_id="brisk_walking", sets=None, reps=None, duration_s=1800, note=""))
POHA = StagedWrite(kind="meal", args=LogMealArgs(meal="breakfast", foods=[LoggedFood(
    day=None, name="Poha with peanuts", ingredients=["flattened rice", "peanut"],
    allergen_tags=["peanut"], diet_tags=[], portion="1 plate", calories=380, note="",
    protein_g=9, carbs_g=55, fat_g=13)]),
    warnings=[WriteWarning(kind="conflict", item="Poha with peanuts", rule_id="DI-ALG-01",
                           attributes=["peanut"], reason="contains peanut")])
PEANUT = UserProfile(condition_ids=[], allergen_tags=["peanut"], diet_tags=[], notes="")


def _text(text, truncated=False):
    return LLMResult(provider="openai", model="m", text=text, truncated=truncated)


async def _note(*script, within=5.0, saved=(WALK,), profile=None, message="log my walk"):
    fake = FakeProvider(list(script), name="openai")
    llm = ResilientProvider(Route(fake, SUMMARY_OPTIONS), None, Breakers())
    plan = CallPlan(deadline=time.monotonic() + within, speed=LOGGED_NOTE, principal="p",
                    kind="logged_note")
    return await logged_note(llm, plan, message, list(saved), AT, INDIA, profile), fake


async def test_the_sentence_may_say_logged():
    text, fake = await _note(_text("Logged your 30-minute walk at 9:30 am. Nice work."))
    assert text == "Logged your 30-minute walk at 9:30 am. Nice work."
    prompt = fake.calls[0].messages[-1].text
    assert "Brisk walking: 30 min (9:30 am)" in prompt


async def test_the_prompt_lists_each_warning_and_the_persons_language():
    prompt = note_prompt("aaj nashte mein poha khaya", [POHA], AT, INDIA)
    assert "  warning: " in prompt and "peanut" in prompt
    assert "Hinglish" in prompt
    assert "Devanagari" in note_prompt("आज नाश्ते में पोहा खाया", [POHA], AT, INDIA)


async def test_the_message_itself_is_never_in_the_prompt():
    # Live, 10 Nov 2026: shown "...and suggest a light dinner", it suggested one
    message = "log my 20 minute walk and suggest a light dinner"
    _, fake = await _note(_text("Logged your walk."), message=message)
    call = fake.calls[0]
    sent = call.messages[-1].text + (call.system or "")
    assert "dinner" not in sent and "suggest" not in sent


async def test_the_sentence_is_gated_like_any_prose():
    text, _ = await _note(_text("Logged your poha. Peanuts are a great snack for you. "
                                "See https://x.example for more."),
                          saved=(POHA,), profile=PEANUT)
    assert "https" not in text and "Logged your poha." in text


@pytest.mark.parametrize("step", [_text(""), _text("Logged your walk and", truncated=True),
                                  ProviderUnavailable("down")])
async def test_an_empty_cut_off_or_failed_reply_sends_nothing(step):
    text, _ = await _note(step, step)
    assert text is None


async def test_a_late_sentence_is_dropped_at_its_time_limit():
    started = time.monotonic()
    text, _ = await _note(Slow(5.0, _text("Logged.")), within=0.3)
    assert text is None and time.monotonic() - started < 1.5


async def test_a_bug_is_logged_and_sends_nothing(caplog):
    with caplog.at_level(logging.ERROR):
        text, _ = await _note()  # nothing scripted: the fake raises
    assert text is None and "logged note failed" in caplog.text


async def test_a_long_sentence_is_cut_to_the_events_limit():
    text, _ = await _note(_text("Logged your walk. " * 40))
    assert text is not None and len(text) <= 300


async def test_cancelling_the_request_cancels_the_sentence():
    task = asyncio.ensure_future(_note(Slow(5.0, _text("Logged."))))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
