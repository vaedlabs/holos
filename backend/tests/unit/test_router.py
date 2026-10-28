"""Router (Plan C.15, Part E #36): deterministic paths, the one model call, languages."""

import time

import pytest
from pydantic import ValidationError

from app.agents.schemas import HistoryTurn, RouterReply, UserProfile
from app.config.speeds import ROUTER
from app.orchestration.router import (
    OTHER_LANGUAGE_FALLBACK,
    OTHER_LANGUAGE_NOTE,
    OUR_LANGUAGE_NOTE,
    Router,
    language,
    other_language,
    profile_text,
)
from app.providers import (
    Breakers,
    CallPlan,
    FakeProvider,
    GenerateOptions,
    LLMResult,
    MalformedOutput,
    ProviderTimeout,
    ResilientProvider,
    Route,
    Usage,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

KNEE = UserProfile(condition_ids=["knee_ligament_injury"], allergen_tags=["peanut"],
                   diet_tags=["vegetarian"], notes="plays football")


def _router(*script):
    fake = FakeProvider(list(script), name="openai")
    llm = ResilientProvider(Route(fake, GenerateOptions(model="m", max_output_tokens=300)),
                            None, Breakers())
    return Router(llm), fake


def _plan():
    return CallPlan(deadline=time.monotonic() + 5, speed=ROUTER, principal="p", kind="router")


def _says(kind, agents=(), reply=None, usage=None, truncated=False):
    return LLMResult(provider="openai", model="m", truncated=truncated,
                     parsed=RouterReply(kind=kind, agents=list(agents), reply=reply),
                     usage=usage or Usage(tokens_in=900, tokens_out=25))


def _turn(role, content, agents=None):
    return HistoryTurn(role=role, content=content, agents=agents, ts="2026-10-29T09:00:00Z")


# --- Deterministic paths: no model call ---


@pytest.mark.parametrize("agents", [None, ["physical"], ["mental", "physical"]])
async def test_a_photo_goes_to_nutrition(agents):
    # Only nutrition reads photos, so a photo beats coaches picked in the app
    router, fake = _router()
    decision = await router.route("is this ok?", plan=_plan(), has_image=True, agents=agents)
    assert (decision.kind, decision.agents, decision.by) == ("coaching", ("nutrition",), "image")
    assert fake.calls == []


async def test_coaches_picked_in_the_app_skip_routing_in_a_fixed_order():
    router, fake = _router()
    decision = await router.route("hi", plan=_plan(), agents=["mental", "physical"])
    assert (decision.kind, decision.agents, decision.by) == (
        "coaching", ("physical", "mental"), "app")
    assert decision.reply is None and fake.calls == []


# --- The model call ---


@pytest.mark.parametrize(("said", "agents"), [
    (["physical"], ("physical",)),
    (["nutrition", "physical"], ("physical", "nutrition")),
    (["mental", "nutrition"], ("nutrition", "mental")),
    (["mental", "nutrition", "physical"], ("physical", "nutrition", "mental")),
])
async def test_the_model_names_every_coach_needed(said, agents):
    usage = Usage(tokens_in=910, tokens_out=24)
    router, fake = _router(_says("coaching", said, usage=usage))
    decision = await router.route("workouts and snacks for my hike", plan=_plan())
    assert (decision.kind, decision.agents, decision.reply, decision.by) == (
        "coaching", agents, None, "model")
    assert decision.usage == usage
    assert fake.calls[0].schema is RouterReply


@pytest.mark.parametrize("kind", ["greeting", "meta", "off_topic", "unclear", "other_language"])
async def test_no_coach_means_holos_replies_itself(kind):
    router, _ = _router(_says(kind, reply="Morning Arjun! How's the knee?"))
    decision = await router.route("good morning", plan=_plan())
    assert (decision.kind, decision.agents, decision.reply) == (
        kind, (), "Morning Arjun! How's the knee?")


async def test_the_model_sees_the_profile_and_the_conversation():
    router, fake = _router(_says("coaching", ["physical"]))
    history = [_turn("user", "a knee-friendly leg day please"),
               _turn("assistant", "Here is a plan: glute bridges...", ["physical"]),
               _turn("user", "thanks!"),
               _turn("assistant", "Anytime, Arjun.")]
    await router.route("make it easier", plan=_plan(), profile=KNEE, history=history)
    call = fake.calls[0]
    assert "knee_ligament_injury" in call.system and "peanut" in call.system
    assert "vegetarian" in call.system and "plays football" in call.system
    assert [(m.role, m.text) for m in call.messages] == [
        ("user", "a knee-friendly leg day please"),
        ("assistant", "[physical] Here is a plan: glute bridges..."),
        ("user", "thanks!"),
        ("assistant", "[Holos] Anytime, Arjun."),
        ("user", "make it easier"),
    ]


async def test_only_the_last_six_turns_are_sent_and_long_ones_are_cut():
    router, fake = _router(_says("greeting", reply="Hi!"))
    history = [_turn("user", f"message {i} " + "x" * 600) for i in range(9)]
    await router.route("hi", plan=_plan(), history=history)
    sent = fake.calls[0].messages[:-1]
    assert [m.text.split()[1] for m in sent] == ["3", "4", "5", "6", "7", "8"]
    assert all(len(m.text) <= 500 for m in sent)


async def test_a_guest_with_no_profile():
    assert profile_text(None) == "Profile: none yet."
    router, fake = _router(_says("greeting", reply="Welcome!"))
    await router.route("hi", plan=_plan())
    assert "Profile: none yet." in fake.calls[0].system


@pytest.mark.parametrize("step", [
    MalformedOutput("not json"),
    LLMResult(provider="openai", model="m", parsed=None),
    LLMResult(provider="openai", model="m", text='{"kind": "coaching"}', parsed=None,
              truncated=True),
])
async def test_an_unusable_model_reply_is_an_error_not_a_made_up_answer(step):
    router, _ = _router(step)
    with pytest.raises(MalformedOutput):
        await router.route("write me Python code", plan=_plan())


async def test_a_truncated_reply_is_an_error_even_when_it_parsed():
    router, _ = _router(_says("coaching", ["physical"], truncated=True))
    with pytest.raises(MalformedOutput):
        await router.route("leg day", plan=_plan())


async def test_a_provider_failure_is_raised_for_the_caller_to_report():
    router, _ = _router(*[ProviderTimeout("slow")] * 3)
    with pytest.raises(ProviderTimeout):
        await router.route("leg day", plan=_plan())


# --- Languages Holos doesn't support (Part E #37) ---


@pytest.mark.parametrize("text", [
    "ঘুমটা হচ্ছে না ঠিকমতো। সহজ ব্যায়াম বলবেন?",  # Bengali
    "நான் சரியாக தூங்கவில்லை",  # Tamil
    "નમસ્તે, હું થાકી ગઈ છું",  # Gujarati
    "مرحبا، أشعر بالتعب",  # Arabic
    "Kannst du mir ein kurzes Training für heute machen?",
    "Últimamente llego a casa agotada y con la cabeza a mil.",
    "Je suis très fatiguée aujourd'hui, comment dormir mieux?",
    "Ik ben moe en heb geen zin om te sporten",
    "Ich bin so müde",
])
async def test_other_languages_are_found_without_the_model(text):
    assert other_language(text)


@pytest.mark.parametrize("text", [
    "मुझे तनाव है, नींद नहीं आती",  # Hindi
    "aaj bahut stress hai kya karu",  # Hinglish
    "Danke! I'll try the squats tomorrow. Bye!",
    "Gracias Holos, this feels much more doable",
    "Lunch: tortilla española and a café con leche with oat milk.",
    "Que sera sera, my mom used to say. How do I sleep better?",
    "café con leche please",  # one foreign small word, no English ones
    "la vida es una fiesta, my friend says, and I want to feel that way again",
    "ok ঘুম",  # mostly Latin: the model decides
    "👍",
    "",
])
async def test_english_hindi_and_a_few_foreign_words_are_not(text):
    assert not other_language(text)


async def test_another_language_is_told_to_the_model():
    router, fake = _router(_says("other_language", reply="Holos funktioniert auf Englisch."))
    decision = await router.route("Kannst du mir ein Training machen?", plan=_plan())
    assert decision.kind == "other_language"
    assert fake.calls[0].system.endswith(OTHER_LANGUAGE_NOTE)


async def test_another_language_never_reaches_a_coach():
    # Neither the crisis check nor the gate can read it
    router, _ = _router(_says("coaching", ["mental"]))
    decision = await router.route("Últimamente llego a casa agotada y con la cabeza a mil.",
                                  plan=_plan())
    assert (decision.kind, decision.agents, decision.reply) == (
        "other_language", (), OTHER_LANGUAGE_FALLBACK)


@pytest.mark.parametrize(("has_image", "agents"), [(True, None), (False, ["mental"])])
async def test_another_language_is_caught_before_a_photo_or_app_coaches(has_image, agents):
    router, fake = _router(_says("other_language", reply="Holos funktioniert auf Englisch."))
    decision = await router.route("Kannst du mir kurz helfen, den Kopf ruhig zu kriegen?",
                                  plan=_plan(), has_image=has_image, agents=agents)
    assert (decision.kind, decision.agents) == ("other_language", ())
    assert len(fake.calls) == 1


@pytest.mark.parametrize(("text", "lang"), [
    ("मुझे तनाव है, नींद नहीं आती", "hindi"),
    ("अभी 2 रोटी और दाल खाई, ok?", "hindi"),
    ("aaj bahut stress hai kya karu", "ours"),
    ("Danke, klingt gut. I'll try it tomorrow after my ride. Bye!", "ours"),
    ("Can I have café con leche with oat milk or is that bad?", "ours"),
    ("Muchas gracias por ayudarme sin hacerme sentir mal cuando no me sale", "other"),
    ("abs", "unsure"),
    ("Ich habe das mit the doctor and it was ok", "unsure"),  # half German, half English
    ("Lunch: tortilla de patatas and a side salad", "unsure"),
    ("👍", "unsure"),
])
async def test_language(text, lang):
    assert language(text) == lang


async def test_english_is_told_it_is_supported():
    router, fake = _router(_says("coaching", ["physical"]))
    await router.route("Danke! Can I do squats tomorrow and what about my knee?", plan=_plan())
    assert fake.calls[0].system.endswith(OUR_LANGUAGE_NOTE)
    assert OTHER_LANGUAGE_NOTE not in fake.calls[0].system


async def test_an_unsure_message_gets_no_language_note():
    router, fake = _router(_says("unclear", reply="What would you like to work on?"))
    await router.route("abs", plan=_plan())
    system = fake.calls[0].system
    assert OUR_LANGUAGE_NOTE not in system and OTHER_LANGUAGE_NOTE not in system


async def test_hindi_called_another_language_is_asked_again():
    # Live: once in 645 calls
    router, fake = _router(_says("other_language", reply="Holos works in English.",
                                 usage=Usage(tokens_in=900, tokens_out=30)),
                           _says("coaching", ["nutrition"],
                                 usage=Usage(tokens_in=900, tokens_out=20)))
    decision = await router.route("अभी दो रोटी और दाल खाई", plan=_plan())
    assert (decision.kind, decision.agents) == ("coaching", ("nutrition",))
    assert decision.usage == Usage(tokens_in=1800, tokens_out=50)
    assert len(fake.calls) == 2


async def test_hindi_is_told_it_is_supported():
    router, fake = _router(_says("coaching", ["nutrition"]))
    await router.route("अभी दो रोटी और दाल खाई", plan=_plan())
    assert fake.calls[0].system.endswith(OUR_LANGUAGE_NOTE)


async def test_hindi_called_another_language_twice_is_an_error():
    router, _ = _router(_says("other_language", reply="No."), _says("other_language", reply="No."))
    with pytest.raises(MalformedOutput):
        await router.route("अभी दो रोटी और दाल खाई", plan=_plan())


async def test_mixed_english_called_another_language_twice_is_the_models_call():
    router, fake = _router(_says("other_language", reply="Holos works in English."),
                           _says("other_language", reply="Holos funktioniert auf Englisch."))
    decision = await router.route("Danke, klingt gut. I'll try it tomorrow after my ride.",
                                  plan=_plan())
    assert (decision.kind, decision.reply) == ("other_language", "Holos funktioniert auf Englisch.")
    assert len(fake.calls) == 2


async def test_an_unsure_message_may_be_another_language():
    router, fake = _router(_says("other_language", reply="Holos funziona in inglese."))
    decision = await router.route("ciao bella", plan=_plan())
    assert decision.kind == "other_language" and len(fake.calls) == 1


# --- RouterReply ---


async def test_the_kind_decides_and_strays_are_dropped():
    # Live: "coaching" with agents and a reply, 1 in 215
    coaching = RouterReply(kind="coaching", agents=["physical"], reply="Sure!")
    assert coaching.reply is None
    greeting = RouterReply(kind="greeting", agents=["mental"], reply="Hi!")
    assert greeting.agents == []


@pytest.mark.parametrize("data", [
    {"kind": "coaching", "agents": [], "reply": None},
    {"kind": "greeting", "agents": [], "reply": None},
    {"kind": "meta", "agents": [], "reply": "   "},
    {"kind": "coaching", "agents": ["physical", "physical"], "reply": None},
    {"kind": "coaching", "agents": ["physical"], "reply": "x" * 401},
    {"kind": "chat", "agents": [], "reply": "hi"},
])
async def test_router_reply_rejects(data):
    with pytest.raises(ValidationError):
        RouterReply(**data)
