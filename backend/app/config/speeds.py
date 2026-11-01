"""Measured provider speeds (Plan C.9). Every slowness rule reads this table.

Measured on the real API, gpt-6-luna (Part D): 27 Oct 2026, small-model free text 306
calls, physical 301, nutrition text 111, meal photo 66; 29 Oct 2026, the router call
1,009 and, streamed, the time to first output of 1,665 calls in four persona runs (the
p90 of a typical run: one run hit an hour when OpenAI was slower, food p90 10.5 s, and
the live p90 is what follows such days) and mental totals of 14 calls. Change a value
only from a new measurement.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Speed:
    p50: float
    p90: float  # a non-streaming call still running here gets a backup call
    p95: float  # a retry needs this much time left (plus the timeout overshoot)
    p99: float  # a non-streaming call still running here counts as bad for the breaker
    # A streaming call with no output yet at this time gets a backup call (Part E #35);
    # None: the p90 stands in
    first_p90: float | None = None


# The router's one call: profile, 6 history turns, a RouterReply of ~25 tokens
ROUTER = Speed(1.4, 2.0, 2.2, 2.9, first_p90=1.9)
# The small model writing free text (up to 200 tokens): the closest to the summary
SMALL_FREE_TEXT = Speed(1.6, 3.0, 3.4, 8.7)
PHYSICAL = Speed(3.3, 6.5, 8.7, 12.9, first_p90=3.0)
NUTRITION = Speed(3.6, 4.4, 4.6, 5.1, first_p90=2.1)
# p99 is the worst of 65 calls: the 66th took 46.9 s, which is what backups are for
MEAL_PHOTO = Speed(3.2, 4.2, 4.7, 5.4, first_p90=2.4)
MENTAL = Speed(5.3, 7.5, 7.8, 8.2, first_p90=2.5)
# A coach reply that may hold a week plan (Part E #38), measured 29 Oct 2026 on 22 week-plan
# requests run twice at the 24/21/14 item limits: physical 16 calls, nutrition 18, mental
# 12, so p95 and p99 are the slowest call. A long reply takes longer to write, not to
# start: the time to first output is the coach's own.
PHYSICAL_PLAN = Speed(7.5, 11.7, 12.7, 12.7, first_p90=PHYSICAL.first_p90)
NUTRITION_PLAN = Speed(11.9, 14.1, 16.7, 16.7, first_p90=NUTRITION.first_p90)
MENTAL_PLAN = Speed(5.4, 6.8, 8.1, 8.1, first_p90=MENTAL.first_p90)
SUMMARY = SMALL_FREE_TEXT

# The SDK's own timeout ends up to this much late (Part D); our bound doesn't rely on it
TIMEOUT_OVERSHOOT_S = 0.5
