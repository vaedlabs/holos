"""The gate: checks a reply or a write against the user's profile (Plan C.14).

    gate(domain, reply_or_write, profile) -> GateResult
    gate(domain, reply, profile, purpose="photo")  # a meal photo (C.14 step 7)
    gate_text(text, profile) -> GateResult      # the multi-coach summary

Input is plain data (`model.model_dump(mode="json")`), because guardrails/ can't
import the app's schemas. A reply is told from a write by its `summary` field.

1. Items: tags come from the catalogue ID, or for a food from its declared
   allergens plus the ingredients its name and ingredient list name. An unknown
   catalogue ID is malformed. For a user with allergies, an ingredient the
   catalogue doesn't know gets a "not checked" caveat.
2. Prose: each sentence that recommends a blocked item is removed. Negated
   mentions ("avoid squats") don't count. Self-harm phrases are removed too.
3. Links and "logged"/"saved" claims are removed from all prose. While an entry waits
   for the person's confirmation, so are claims it couldn't be saved; when the turn's
   entries were all logged, so is sending the person to a confirm card (Part E #52).

Items are judged, not removed: BaseAgent retries first, then drops blocked items
(Plan C.10). Every decision carries a rule ID and the rules version.

A meal photo shows food the user already has (owner, Part E #31): an item conflict is
a warning naming it ("Likely contains gluten, which is in your allergies"), never a
block, so it is neither retried nor removed. Prose is gated as for a plan, except that
naming a food that is one of the photo's own items describes the plate, not a
recommendation ("This looks like a chicken sandwich"); any other conflicting food
in the prose is removed as usual. A user with allergies or a diet also gets
PHOTO_CAVEAT on the reply.
"""

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from .loader import Guardrails, Rule, get_guardrails
from .matcher import Entry, Matcher, get_matcher
from .normalise import fold_for_matching
from .types import (
    ACTION_ORDER,
    Action,
    Allergen,
    Decision,
    DietConflict,
    Domain,
    GateResult,
    ItemVerdict,
    ProfileLike,
    Purpose,
    Scrub,
)

# Built-in rules: the gate's own checks, not profile rules from rules.yaml
MALFORMED_RULE = "GT-MALFORMED-01"
UNCHECKED_RULE = "GT-UNCHECKED-01"
MALFORMED_REASON = "Not a known catalogue item"
UNCHECKED_REASON = "Not checked against your allergies"
PHOTO_CAVEAT = ("A photo can't show every ingredient (oils, sauces, spice mixes). "
                "Check with whoever made it.")
REASON_MAX = 200

# A declared allergen says something about the diet too
ALLERGEN_CONFLICTS = {
    Allergen.MILK: {DietConflict.ANIMAL_PRODUCT},
    Allergen.EGG: {DietConflict.ANIMAL_PRODUCT, DietConflict.EGG},
    Allergen.FISH: {DietConflict.ANIMAL_PRODUCT, DietConflict.FISH},
    Allergen.CRUSTACEAN: {DietConflict.ANIMAL_PRODUCT, DietConflict.SHELLFISH},
    Allergen.MOLLUSC: {DietConflict.ANIMAL_PRODUCT, DietConflict.SHELLFISH},
}

# The danda (।) ends a Hindi sentence: without it one blocked mention took the paragraph
SENTENCE_SPLIT = re.compile(r"((?<=[.!?…।])\s+|\n+)")
SPACES = re.compile(r"[ \t]{2,}")
SPACE_BEFORE_PUNCT = re.compile(r" +([.,;:!?])")

MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
AUTOLINK = re.compile(r"<(?:https?://|mailto:)[^>]*>", re.IGNORECASE)
# A link never ends in sentence punctuation, so "see x.com." keeps its full stop
_LINK_TAIL = r"""(?:[^\s<>]*[^\s<>.,;:!?)\]'"])?"""
URL = re.compile(r"(?:https?://|www\.)" + _LINK_TAIL, re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
BARE_DOMAIN = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|in|co|info|biz|xyz|app|ly|me|gov|edu|ai|dev"
    r"|link|site|online|top|club|shop|uk|us)\b(?:/" + _LINK_TAIL + ")?",
    re.IGNORECASE,
)
# "ho gaye" is left out: "log" is also "people" ("kai log ho gaye"). Devanagari has no
# closing \b: a word ending in a vowel sign has no boundary there in `re`
WRITE_CLAIM = re.compile(
    r"\b(?:logged|saved|(?:log|save) (?:kar (?:diya|di|dia)|ho (?:gaya|gya|gayi|gai))"
    r"|(?:added|recorded) (?:it |this |that )?(?:to|in) your (?:log|logs|diary|journal|history))\b"
    r"|(?<!\w)(?:लॉग|सेव) (?:कर (?:दिया|दी)|हो (?:गया|गयी|गई))"
)
# "Couldn't save it": false while the entry waits for confirmation (Part E #52)
REFUSAL_CLAIM = re.compile(
    r"\b(?:(?:couldn't|could not|can't|cannot|can not|wasn't able to|was not able to"
    r"|unable to|didn't|did not|won't|will not|not able to) (?:\w+ ){0,2}"
    r"(?:save|log|record|add)\b"
    r"|not (?:been )?(?:saved|logged|recorded|added)\b"
    r"|(?:log|save) (?:nahi|nahin|nhi) (?:kar|ho))"
    r"|(?<!\w)(?:लॉग|सेव) नहीं (?:कर|हो)"
)
# "Confirm it on the card below": false when nothing waits (Part E #52)
CARD_CLAIM = re.compile(
    r"^(?=.*(?:\bconfirm|कन्फर्म|पुष्टि))(?=.*(?:\bcards?\b|\bwait|कार्ड|इंतज़ार|इंतजार))")


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else [value]


def _active(rule: Rule, profile: ProfileLike) -> bool:
    when = rule.when
    if when.always:
        return True
    if when.condition:
        return any(c in profile.condition_ids for c in when.condition)
    if when.diet:
        return any(d in profile.diet_tags for d in when.diet)
    if when.allergen == "any":
        return bool(profile.allergen_tags)
    return False


class _Check:
    """One gate call: the active rules, and everything the gate decides."""

    def __init__(self, guardrails: Guardrails, matcher: Matcher, profile: ProfileLike,
                 purpose: Purpose = "plan"):
        rules = guardrails.rules
        self.purpose = purpose
        self.held = False  # an entry this turn waits for confirmation
        self.logged = False  # the turn logged entries, and none of them waits
        self.after_save = False  # written after the save: "logged" is true
        self.version = rules.version
        self.matcher = matcher
        self.profile = profile
        self.allergies = set(profile.allergen_tags)
        every = [*rules.exercise, *rules.dietary, *rules.mental]
        active = [r for r in every if _active(r, profile)]
        self.tag_rules = {
            "exercise": [r for r in active if r.id.startswith("EX-")],
            "practice": [r for r in active if r.id.startswith("MN-") and "text" not in r.block],
            "ingredient": [r for r in active if r.id.startswith("DI-")],
        }
        self.tag_rules["food"] = self.tag_rules["ingredient"]
        self.text_rules = [
            (r, re.compile(r"(?<![\w'])(?:"
                           + "|".join(re.escape(fold_for_matching(p)) for p in r.block["text"])
                           + r")(?![\w'])"))
            for r in active if "text" in r.block
        ]
        self.allowed_domains = {
            h.contact.lower() for h in rules.crisis.helplines if "." in h.contact
        }
        self.on_plate: set[Entry] = set()  # photo mode: the ingredients of the photo's items
        self.decisions: list[Decision] = []
        self.scrubbed: list[Scrub] = []
        self.malformed = False

    def decision(self, action: Action, rule_id: str, reason: str, items: list[str]) -> Decision:
        decision = Decision(action, rule_id, self.version, reason[:REASON_MAX], tuple(items))
        if decision not in self.decisions:
            self.decisions.append(decision)
        return decision

    # --- Rules on tags ---

    def _tag_hits(self, entry: Entry, allergens: set[str], conflicts: set[str]) -> list[Rule]:
        hits = []
        for rule in self.tag_rules[entry.kind]:
            if entry.kind in ("ingredient", "food"):
                matched = all(
                    bool(allergens & self.allergies) if key == "allergen"
                    else bool(conflicts & set(_as_list(value)))
                    for key, value in rule.block.items()
                )
            else:
                matched = all(entry.tags.get(key) in _as_list(value)
                              for key, value in rule.block.items())
            if matched:
                hits.append(rule)
        return hits

    def entry_hits(self, entry: Entry) -> list[Rule]:
        return self._tag_hits(entry, set(entry.allergens), set(entry.diet_conflicts))

    def _attributes(self, hits: list[Rule], allergens: set[str] = frozenset(),
                    conflicts: set[str] = frozenset()) -> tuple[tuple[str, tuple[str, ...]], ...]:
        out = []
        for rule in hits:
            found: list[str] = []
            for key, value in rule.block.items():
                if key == "allergen":
                    found += sorted(str(a) for a in allergens & self.allergies)
                elif key == "diet_conflict":
                    found += sorted(str(c) for c in conflicts & set(_as_list(value)))
                else:
                    found.append(key)
            out.append((rule.id, tuple(found)))
        return tuple(out)

    # --- Items ---

    def catalogue_item(self, index: int, item: Any, kind: str) -> ItemVerdict:
        table = self.matcher.exercises if kind == "exercise" else self.matcher.practices
        entry = table.get(item.get("catalogue_id")) if isinstance(item, Mapping) else None
        if entry is None:
            self.malformed = True
            label = str(item.get("catalogue_id")) if isinstance(item, Mapping) else "?"
            d = self.decision("block", MALFORMED_RULE, MALFORMED_REASON, [label[:60]])
            return ItemVerdict(index, "block", decisions=(d,))
        hits = self.entry_hits(entry)
        return replace(self._verdict(index, hits, entry.name), attributes=self._attributes(hits))

    def food_item(self, index: int, food: Any) -> ItemVerdict:
        if not isinstance(food, Mapping) or not isinstance(food.get("name"), str):
            self.malformed = True
            d = self.decision("block", MALFORMED_RULE, "Not a valid food item", ["?"])
            return ItemVerdict(index, "block", decisions=(d,))
        name = food["name"]
        allergens = set(food.get("allergen_tags") or [])
        conflicts: set[str] = set()
        for allergen in allergens:
            conflicts |= ALLERGEN_CONFLICTS.get(allergen, set())
        unknown = []
        for n, text in enumerate([name, *(food.get("ingredients") or [])]):
            found = self.matcher.ingredients(text) if isinstance(text, str) else []
            if not found and n > 0:
                unknown.append(text)
            for entry in found:
                allergens |= entry.allergens
                conflicts |= entry.diet_conflicts
        food_entry = Entry("food", name, name)
        hits = self._tag_hits(food_entry, allergens, conflicts)
        if self.purpose == "photo":
            verdict = self._photo_verdict(index, hits, name, allergens)
        else:
            verdict = self._verdict(index, hits, name)
        verdict = replace(verdict, attributes=self._attributes(hits, allergens, conflicts))
        if unknown and self.allergies:
            d = self.decision("warn", UNCHECKED_RULE, UNCHECKED_REASON, unknown)
            caveat = f"{UNCHECKED_REASON}: {', '.join(unknown)}"
            verdict = ItemVerdict(index, max(verdict.action, "warn", key=ACTION_ORDER.get),
                                  (*verdict.caveats, caveat), (*verdict.decisions, d),
                                  (*verdict.attributes, (UNCHECKED_RULE, tuple(unknown))))
        return verdict

    def _photo_verdict(self, index: int, hits: list[Rule], name: str,
                       allergens: set[str]) -> ItemVerdict:
        """Food the user already has: every conflict is a warning that names it."""
        decisions, caveats = [], []
        for rule in hits:
            if rule.severity == "block" and "allergen" in rule.block:
                found = sorted(a.replace("_", " ") for a in allergens & self.allergies)
                named = " and ".join([", ".join(found[:-1]), found[-1]] if len(found) > 1
                                     else found)
                verb = "are" if len(found) > 1 else "is"
                caveat = f"Likely contains {named}, which {verb} in your allergies"
            elif rule.severity == "block":
                caveat = f"Likely {rule.reason[0].lower()}{rule.reason[1:]}"
            else:
                caveat = rule.reason
            decisions.append(self.decision("warn", rule.id, caveat, [name]))
            caveats.append(caveat)
        return ItemVerdict(index, "warn" if hits else "allow", tuple(caveats), tuple(decisions))

    def _verdict(self, index: int, hits: list[Rule], name: str) -> ItemVerdict:
        decisions = tuple(self.decision(r.severity.value, r.id, r.reason, [name]) for r in hits)
        action = max((d.action for d in decisions), key=ACTION_ORDER.get, default="allow")
        caveats = tuple(d.reason for d in decisions if d.action == "warn")
        return ItemVerdict(index, action, caveats, decisions)

    # --- Prose ---

    def prose(self, text: Any, where: str) -> Any:
        if not isinstance(text, str) or not text:
            return text
        text = self._remove_links(text, where)
        parts = SENTENCE_SPLIT.split(text)
        kept = []
        for i in range(0, len(parts), 2):
            sentence, sep = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
            if sentence.strip() and not self._sentence_ok(sentence, where):
                continue
            kept.append(sentence + sep)
        cleaned = SPACE_BEFORE_PUNCT.sub(r"\1", SPACES.sub(" ", "".join(kept)))
        return cleaned.strip()

    def _remove_links(self, text: str, where: str) -> str:
        def drop(match: re.Match) -> str:
            found = match.group(0)
            if found.lower().rstrip(".,;:!?") in self.allowed_domains:
                return found
            self.scrubbed.append(Scrub("link", where, found[:200]))
            return ""

        def label(match: re.Match) -> str:
            self.scrubbed.append(Scrub("link", where, match.group(0)[:200]))
            return match.group(1)

        text = MARKDOWN_LINK.sub(label, text)
        for pattern in (AUTOLINK, URL, EMAIL, BARE_DOMAIN):
            text = pattern.sub(drop, text)
        return text

    def _sentence_ok(self, sentence: str, where: str) -> bool:
        folded = fold_for_matching(sentence)
        if ((WRITE_CLAIM.search(folded) and not self.after_save)
                or (self.held and REFUSAL_CLAIM.search(folded))
                or (self.logged and CARD_CLAIM.search(folded))):
            self.scrubbed.append(Scrub("write_claim", where, sentence.strip()[:200]))
            return False
        ok = True
        for rule, pattern in self.text_rules:
            if match := pattern.search(folded):
                self.decision(rule.severity.value, rule.id, rule.reason, [match.group(0)])
                ok = ok and rule.severity != "block"
        for mention in self.matcher.find(sentence):
            if mention.negated or mention.entry in self.on_plate:
                continue
            for rule in self.entry_hits(mention.entry):
                self.decision(rule.severity.value, rule.id, rule.reason, [mention.entry.name])
                ok = ok and rule.severity != "block"
        return ok

    def result(self, content: Any, items: list[ItemVerdict]) -> GateResult:
        action = max((d.action for d in self.decisions), key=ACTION_ORDER.get, default="allow")
        caveats = ()
        if self.purpose == "photo" and (self.allergies or self.profile.diet_tags):
            caveats = (PHOTO_CAVEAT,)
        return GateResult(action, tuple(self.decisions), content, tuple(items),
                          tuple(self.scrubbed), self.malformed, caveats)


def _new_check(guardrails: Guardrails | None, profile: ProfileLike,
               purpose: Purpose = "plan") -> _Check:
    """Tests may pass their own rules; the packaged ones use the shared matcher."""
    if guardrails is None or guardrails is get_guardrails():
        return _Check(get_guardrails(), get_matcher(), profile, purpose)
    return _Check(guardrails, Matcher(guardrails.catalogue), profile, purpose)


ITEM_KIND = {"physical": "exercise", "mental": "practice", "nutrition": "food"}


def _items(check: _Check, domain: Domain, items: Any, prefix: str) -> list[ItemVerdict]:
    if not isinstance(items, list):
        check.malformed = True
        check.decision("block", MALFORMED_RULE, "Items are not a list", [prefix])
        return []
    verdicts = []
    for i, item in enumerate(items):
        if ITEM_KIND[domain] == "food":
            verdicts.append(check.food_item(i, item))
        else:
            verdicts.append(check.catalogue_item(i, item, ITEM_KIND[domain]))
        if isinstance(item, Mapping) and "note" in item:
            item["note"] = check.prose(item["note"], f"{prefix}[{i}].note")
    return verdicts


def _plate(check: _Check, items: Any) -> set[Entry]:
    """Every catalogue ingredient named by the photo's items."""
    plate: set[Entry] = set()
    for food in items if isinstance(items, list) else []:
        if isinstance(food, Mapping):
            for text in [food.get("name"), *(food.get("ingredients") or [])]:
                if isinstance(text, str):
                    plate.update(check.matcher.ingredients(text))
    return plate


def _already_had(check: _Check, logged: Sequence[Mapping[str, Any]]) -> set[Entry]:
    had: set[Entry] = set()
    for entry in logged:
        if "foods" in entry:
            had |= _plate(check, entry["foods"])
        cid = entry.get("catalogue_id")
        for table in (check.matcher.exercises, check.matcher.practices):
            if cid in table:
                had.add(table[cid])
    return had


def gate(
    domain: Domain,
    reply_or_write: Mapping[str, Any],
    profile: ProfileLike,
    guardrails: Guardrails | None = None,
    purpose: Purpose = "plan",
    logged: Sequence[Mapping[str, Any]] = (),
    held: bool = False,
) -> GateResult:
    """Check an agent reply or a write (log_workout, log_meal, log_practice arguments).
    purpose="photo": a nutrition reply about a meal photo (C.14 step 7).
    logged: the entries the person logged this turn (write arguments). Like a photo's
    foods, they are what the person already had, so a sentence naming them stays: live,
    a vegan's paneer log lost its whole acknowledgement (Part E #45).
    held: one of them waits for the person's confirmation (Part E #52)."""
    if domain not in ITEM_KIND:
        raise ValueError(f"unknown domain '{domain}'")
    if purpose == "photo" and (domain != "nutrition" or "summary" not in reply_or_write):
        raise ValueError("photo mode is for nutrition replies")
    check = _new_check(guardrails, profile, purpose)
    check.held, check.logged = held, bool(logged) and not held
    content = copy.deepcopy(dict(reply_or_write))

    if "summary" in content:  # a reply
        if purpose == "photo":
            check.on_plate = _plate(check, content.get("items"))
        check.on_plate |= _already_had(check, logged)
        items = _items(check, domain, content.get("items", []), "items")
        content["summary"] = check.prose(content["summary"], "summary")
        notes = [check.prose(n, f"notes[{i}]") for i, n in enumerate(content.get("notes") or [])]
        content["notes"] = [n for n in notes if n]
        if content.get("follow_up"):
            content["follow_up"] = check.prose(content["follow_up"], "follow_up") or None
    elif domain == "nutrition":  # a meal: its foods are the items
        items = _items(check, domain, content.get("foods"), "foods")
    else:  # a workout or practice: the entry itself is the one item
        items = [check.catalogue_item(0, content, ITEM_KIND[domain])]
        content["note"] = check.prose(content.get("note", ""), "note")
    return check.result(content, items)


def gate_text(
    text: str, profile: ProfileLike, guardrails: Guardrails | None = None,
    after_save: bool = False,
) -> GateResult:
    """Check free prose that belongs to no one domain, such as the holistic summary.
    after_save: the sentence written once entries were saved (Part E #54 B): it may say
    they were logged, since the save already happened; every other check applies."""
    check = _new_check(guardrails, profile)
    check.after_save = after_save
    return check.result(check.prose(text, "summary"), [])
