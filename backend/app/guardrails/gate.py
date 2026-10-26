"""The gate: checks a reply or a write against the user's profile (Plan C.14).

    gate(domain, reply_or_write, profile) -> GateResult
    gate_text(text, profile) -> GateResult      # the holistic summary

Input is plain data (`model.model_dump(mode="json")`), because guardrails/ can't
import the app's schemas. A reply is told from a write by its `summary` field.

1. Items: tags come from the catalogue ID, or for a food from its declared
   allergens plus the ingredients its name and ingredient list name. An unknown
   catalogue ID is malformed. For a user with allergies, an ingredient the
   catalogue doesn't know gets a "not checked" caveat.
2. Prose: each sentence that recommends a blocked item is removed. Negated
   mentions ("avoid squats") don't count. Self-harm phrases are removed too.
3. Links and "logged"/"saved" claims are removed from all prose.

Items are judged, not removed: BaseAgent retries first, then drops blocked items
(Plan C.10). Every decision carries a rule ID and the rules version.
"""

import copy
import re
from collections.abc import Mapping
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
    Scrub,
)

# Built-in rules: the gate's own checks, not profile rules from rules.yaml
MALFORMED_RULE = "GT-MALFORMED-01"
UNCHECKED_RULE = "GT-UNCHECKED-01"
MALFORMED_REASON = "Not a known catalogue item"
UNCHECKED_REASON = "Not checked against your allergies"
REASON_MAX = 200

# A declared allergen says something about the diet too
ALLERGEN_CONFLICTS = {
    Allergen.MILK: {DietConflict.ANIMAL_PRODUCT},
    Allergen.EGG: {DietConflict.ANIMAL_PRODUCT, DietConflict.EGG},
    Allergen.FISH: {DietConflict.ANIMAL_PRODUCT, DietConflict.FISH},
    Allergen.CRUSTACEAN: {DietConflict.ANIMAL_PRODUCT, DietConflict.SHELLFISH},
    Allergen.MOLLUSC: {DietConflict.ANIMAL_PRODUCT, DietConflict.SHELLFISH},
}

SENTENCE_SPLIT = re.compile(r"((?<=[.!?…])\s+|\n+)")
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
WRITE_CLAIM = re.compile(
    r"\b(?:logged|saved|(?:log|save) kar (?:diya|di|dia)"
    r"|(?:added|recorded) (?:it |this |that )?(?:to|in) your (?:log|logs|diary|journal|history))\b"
)


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

    def __init__(self, guardrails: Guardrails, matcher: Matcher, profile: ProfileLike):
        rules = guardrails.rules
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

    # --- Items ---

    def catalogue_item(self, index: int, item: Any, kind: str) -> ItemVerdict:
        table = self.matcher.exercises if kind == "exercise" else self.matcher.practices
        entry = table.get(item.get("catalogue_id")) if isinstance(item, Mapping) else None
        if entry is None:
            self.malformed = True
            label = str(item.get("catalogue_id")) if isinstance(item, Mapping) else "?"
            d = self.decision("block", MALFORMED_RULE, MALFORMED_REASON, [label[:60]])
            return ItemVerdict(index, "block", decisions=(d,))
        return self._verdict(index, self.entry_hits(entry), entry.name)

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
        verdict = self._verdict(index, self._tag_hits(food_entry, allergens, conflicts), name)
        if unknown and self.allergies:
            d = self.decision("warn", UNCHECKED_RULE, UNCHECKED_REASON, unknown)
            caveat = f"{UNCHECKED_REASON}: {', '.join(unknown)}"
            verdict = ItemVerdict(index, max(verdict.action, "warn", key=ACTION_ORDER.get),
                                  (*verdict.caveats, caveat), (*verdict.decisions, d))
        return verdict

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
        if WRITE_CLAIM.search(folded):
            self.scrubbed.append(Scrub("write_claim", where, sentence.strip()[:200]))
            return False
        ok = True
        for rule, pattern in self.text_rules:
            if match := pattern.search(folded):
                self.decision(rule.severity.value, rule.id, rule.reason, [match.group(0)])
                ok = ok and rule.severity != "block"
        for mention in self.matcher.find(sentence):
            if mention.negated:
                continue
            for rule in self.entry_hits(mention.entry):
                self.decision(rule.severity.value, rule.id, rule.reason, [mention.entry.name])
                ok = ok and rule.severity != "block"
        return ok

    def result(self, content: Any, items: list[ItemVerdict]) -> GateResult:
        action = max((d.action for d in self.decisions), key=ACTION_ORDER.get, default="allow")
        return GateResult(action, tuple(self.decisions), content, tuple(items),
                          tuple(self.scrubbed), self.malformed)


def _new_check(guardrails: Guardrails | None, profile: ProfileLike) -> _Check:
    """Tests may pass their own rules; the packaged ones use the shared matcher."""
    if guardrails is None or guardrails is get_guardrails():
        return _Check(get_guardrails(), get_matcher(), profile)
    return _Check(guardrails, Matcher(guardrails.catalogue), profile)


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


def gate(
    domain: Domain,
    reply_or_write: Mapping[str, Any],
    profile: ProfileLike,
    guardrails: Guardrails | None = None,
) -> GateResult:
    """Check an agent reply or a write (log_workout, log_meal, log_practice arguments)."""
    if domain not in ITEM_KIND:
        raise ValueError(f"unknown domain '{domain}'")
    check = _new_check(guardrails, profile)
    content = copy.deepcopy(dict(reply_or_write))

    if "summary" in content:  # a reply
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
    text: str, profile: ProfileLike, guardrails: Guardrails | None = None
) -> GateResult:
    """Check free prose that belongs to no one domain, such as the holistic summary."""
    check = _new_check(guardrails, profile)
    return check.result(check.prose(text, "summary"), [])
