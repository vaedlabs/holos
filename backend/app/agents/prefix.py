"""The static prompt prefix of each coach (Plan C.9): instructions, output rules, the
domain's safety rules and its catalogue. Built once from rules.yaml and catalogue.yaml,
so the prompt and the gate read the same rules, and identical for every user, so the
provider can cache it (at least 1,024 tokens).
"""

from functools import cache

from app.guardrails.loader import Rule, get_guardrails
from app.guardrails.types import EXERCISE_TAGS, PRACTICE_TAGS

VOICE = """\
You are Holos's {role}, part of a personal assistant for growth in exercise, food and \
mental wellbeing. Talk to the person like a coach who knows them: warm, direct and \
specific to their profile, goals and what they said earlier in the conversation. Reply in \
their language and tone: English, Hindi (Devanagari) or Hinglish, as they write. You are \
not a doctor and never diagnose; for pain, worrying symptoms or medication questions, \
suggest they check with a doctor or physiotherapist, once and briefly."""

OUTPUT = """\
How to reply: only in the JSON schema.
- kind: plan when you give concrete items to do; answer for information; log_ack after \
logging; clarify only when nothing useful is possible without one answer. Otherwise help \
now: choose sensible defaults, say in a few words what you assumed, and let them adjust. \
Ask only about your own area.
- Other coaches may answer the same message at the same time (exercise, food, mental \
wellbeing). Answer only the part that is yours; never cover theirs.
- summary: the heart of the reply, at most 400 characters, plain text.
- items: only catalogue IDs from the list below for exercises and practices. Each note \
says how to do it safely for this person, at most 120 characters.
- notes: up to 3 short tips or cautions.
- source_ids: only ids of web search results from this turn; else empty.
- follow_up: only with kind clarify.
- risk_flag: true if the person may be at risk of self-harm or in a medical emergency.
- Never write links, and never say you logged or saved something unless the log tool \
returned "staged".
Tools: call {log_tool} when the person asks you to log something they did or ate, then \
confirm with kind log_ack. Call get_recent_logs when they refer to what they did before. \
Call web_search only for facts you can't know (recent research, a product); most \
questions need no search.
Safety: every item and every sentence is checked against the person's profile after you \
reply, and anything unsafe is removed. Follow the rules below so nothing has to be \
removed. When you leave something out for their safety, say why in one short note."""

DOMAIN = {
    "physical": ("exercise coach", "log_workout", "exercise"),
    "nutrition": ("food coach", "log_meal", "dietary"),
    "mental": ("mental wellbeing coach", "log_practice", "mental"),
}


def _when(rule: Rule) -> str:
    when = rule.when
    if when.always:
        return "Always"
    if when.condition:
        return f"If the profile has {' or '.join(c.replace('_', ' ') for c in when.condition)}"
    if when.diet:
        return f"If the diet is {' or '.join(str(d) for d in when.diet)}"
    return "If the profile lists allergies"


def _block(rule: Rule) -> str:
    if "text" in rule.block:
        return "never write anything that does this"
    if rule.block.get("allergen") == "same":
        return "no food containing those allergens"
    parts = []
    for key, value in rule.block.items():
        values = value if isinstance(value, list) else [value]
        name = key.replace("_", " ")
        parts.append(name if values == [True] else f"{name} {'/'.join(map(str, values))}")
    verb = "no" if rule.severity == "block" else "warn about"
    return f"{verb} items with {', '.join(parts)}"


def rules_text(section: str) -> str:
    rules = getattr(get_guardrails().rules, section)
    return "\n".join(f"- {_when(r)}: {_block(r)} ({r.reason})." for r in rules)


def _tags(tags: dict, vocab: dict) -> str:
    shown = []
    for key, value in tags.items():
        default = "low" if vocab.get(key) and "low" in vocab[key] else False
        if value not in (default, None, False):
            shown.append(key.replace("_", " ") if value is True else
                         f"{key.replace('_', ' ')} {value}")
    return f" ({', '.join(shown)})" if shown else ""


def catalogue_text(domain: str) -> str:
    catalogue = get_guardrails().catalogue
    if domain == "physical":
        return "Exercises you may use (id: name (tags)):\n" + "\n".join(
            f"- {i.id}: {i.name}{_tags(i.tags, EXERCISE_TAGS)}" for i in catalogue.exercises)
    if domain == "mental":
        return "Practices you may use (id: name (tags)):\n" + "\n".join(
            f"- {i.id}: {i.name}{_tags(i.tags, PRACTICE_TAGS)}" for i in catalogue.practices)
    lines = []
    for food in catalogue.ingredients:
        tags = [*food.allergens, *food.diet_conflicts]
        lines.append(f"- {food.name}{': ' + ', '.join(tags) if tags else ''}")
    return ("Known ingredients and what they contain (allergens, then diet conflicts). Tag "
            "every food's allergens from its ingredients:\n" + "\n".join(lines))


@cache
def prefix(domain: str, extra: str = "") -> str:
    role, log_tool, section = DOMAIN[domain]
    parts = [VOICE.format(role=role), OUTPUT.format(log_tool=log_tool)]
    if extra:
        parts.append(extra)
    parts += [f"Safety rules:\n{rules_text(section)}", catalogue_text(domain)]
    return "\n\n".join(parts)
