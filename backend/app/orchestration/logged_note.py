"""The coach's sentence about what was just saved (owner, 8 Nov 2026, Part E #54 B).

    text = await logged_note(llm, plan, message, saved, at, tz, profile)  # or None

After the save the `committed` record goes out at once; then the small model writes one or
two sentences in the person's language from the save result alone: what, when, a few
warm words, and any warning (then no praise). It is checked like any prose, except that
it may say the entries were logged, because the save already happened. It has its own
time limit (LOGGED_NOTE_S, from measured calls). A failure or a late answer sends
nothing, since the record said it, and so does a bug here (logged with its stack): a
save must not end in an error.
Held entries get no sentence: the coach's reply already explained them.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.schemas import StagedWrite, UserProfile
from app.agents.style import STYLE_NOTE, writing_style
from app.agents.tools.write import summarise
from app.orchestration.clock import when_text
from app.orchestration.composer import gated
from app.orchestration.staging import NO_PROFILE, warning_text
from app.providers import CallPlan, ProviderError, ResilientProvider, Turn

log = logging.getLogger(__name__)

NOTE_CHARS = 300
PROMPT = """\
You are Holos, a personal coach for exercise, food and mental wellbeing, talking to \
someone you know. What they asked you to log has just been saved. Reply with one or two \
short sentences, at most 200 characters in all, in their language and tone (English, \
Hindi in Devanagari, or Hinglish, as they write): say in your own words what was logged \
and when, and add a few warm, specific words as their coach would. If a warning is \
listed, mention it plainly once and add no praise. No advice, no questions, no links, \
no emojis."""


def note_prompt(message: str, saved: list[StagedWrite], at: datetime, tz: ZoneInfo) -> str:
    lines = []
    for write in saved:
        lines.append(f"- {summarise(write.kind, write.args)} ({when_text(at, tz)})")
        lines += [f"  warning: {warning_text(w)}" for w in write.conflicts]
    style = STYLE_NOTE[writing_style(message)]
    return f"The person wrote: {message}\n\nSaved:\n" + "\n".join(lines) + f"\n\n({style})"


async def logged_note(llm: ResilientProvider, plan: CallPlan, message: str,
                      saved: list[StagedWrite], at: datetime, tz: ZoneInfo,
                      profile: UserProfile | None) -> str | None:
    try:
        reply = await llm.generate([Turn("user", note_prompt(message, saved, at, tz))],
                                   plan=plan, system=PROMPT)
    except ProviderError:
        return None  # on the trace already
    except Exception:
        log.exception("logged note failed")
        return None
    if not reply.text or reply.truncated:
        return None
    text = gated(reply.text.strip()[:NOTE_CHARS], profile or NO_PROFILE, after_save=True).text
    return text or None
