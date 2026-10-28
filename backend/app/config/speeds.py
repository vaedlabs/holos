"""Measured provider speeds (Plan C.9). Every slowness rule reads this table.

Measured on the real API, gpt-6-luna (Part D): 27 Oct 2026, small-model free text 306
calls, physical 301, nutrition text 111, meal photo 66; 29 Oct 2026, the router call
1,009. Change a value only from a new measurement.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Speed:
    p50: float
    p90: float  # a call still running here gets a backup call
    p95: float  # a retry needs this much time left (plus the timeout overshoot)
    p99: float  # a call still running here counts as bad for the breaker


# The router's one call: profile, 6 history turns, a RouterReply of ~25 tokens
ROUTER = Speed(1.4, 2.0, 2.2, 2.9)
# The small model writing free text (up to 200 tokens): the closest to the summary
SMALL_FREE_TEXT = Speed(1.6, 3.0, 3.4, 8.7)
PHYSICAL = Speed(3.3, 6.5, 8.7, 12.9)
NUTRITION = Speed(3.6, 4.4, 4.6, 5.1)
# p99 is the worst of 65 calls: the 66th took 46.9 s, which is what backups are for
MEAL_PHOTO = Speed(3.2, 4.2, 4.7, 5.4)
# Not measured yet (P4.5, P4.6): the closest measured call stands in
MENTAL = PHYSICAL
SUMMARY = SMALL_FREE_TEXT

# The SDK's own timeout ends up to this much late (Part D); our bound doesn't rely on it
TIMEOUT_OVERSHOOT_S = 0.5
