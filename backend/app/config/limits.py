"""Every limit from Plan C.12, in one place. Change a value here only with the owner."""

from datetime import timedelta
from decimal import Decimal

# Request intake
REQUEST_BODY_BYTES = 7 * 1024 * 1024
MESSAGE_CHARS = 2000
IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
IMAGE_MAX_SIDE_PX = 1024
GUEST_PROFILE_BYTES = 4 * 1024
GUEST_HISTORY_TURNS = 6
HISTORY_TURN_CHARS = 2000

# Agents (reply caps per agent live with the schemas: agents.schemas.REPLY_TOKEN_CAP)
REASONING_ALLOWANCE_LOW = 1000
TOOL_ROUNDS = 3
# Entries one message may log, all coaches together (owner, 11 Nov 2026, Part E #59:
# a model told to log 40 entries saved 40)
ENTRIES_PER_TURN = 10
# The mention reader (Part E #59): off, the gate checks with its word lists alone
MENTION_READER = False

# Deadlines (owner, 29 Oct 2026, Part E #35)
ROUTING_DEADLINE_S = 5
AGENT_DEADLINE_S = 60
REQUEST_DEADLINE_S = 90
# Input tokens each call reserves for (C.13): the largest measured per kind, rounded up
# (2 Nov 2026, 1,894 calls in P4.5's runs: physical 7,133, nutrition 5,710, meal photo
# 5,401, mental 3,152, router 1,454; the summary, not yet measured, from its prompt)
RESERVE_TOKENS_IN = {"router": 1600, "physical": 8000, "nutrition": 6500,
                     "meal_photo": 6000, "mental": 3500, "summary": 3000, "logged_note": 1000,
                     # Part E #59: 6,894 measured for 1–4 sentences; a long reply adds more
                     "reader": 9000}

# Concurrency
INFLIGHT_PER_PRINCIPAL = 1
INFLIGHT_PER_GUEST_IP = 3
INFLIGHT_GLOBAL = 32
LEASE_TTL = timedelta(seconds=60)
LLM_SLOTS_PER_PRINCIPAL = 3
LLM_SLOTS_GLOBAL = 24
PROVIDER_SLOTS = {"openai": 24, "gemini": 4, "tavily": 4}

# Request and spend caps
REQUESTS_PER_MINUTE = 6
GUEST_SESSION_REQUESTS = 30
GUEST_SESSION_USD = Decimal("0.05")
ACCOUNT_DAY_REQUESTS = 30
ACCOUNT_DAY_USD = Decimal("0.05")
GUEST_IP_WINDOW = timedelta(minutes=240)
GUEST_IP_REQUESTS = 60
GUEST_IP_USD = Decimal("0.10")
GUEST_IP_HARD_STOP_FACTOR = 3
NEW_GUEST_SESSIONS_PER_IP_HOUR = 10
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_ATTEMPTS_PER_IP = 10
LOGIN_FAILURES_PER_ACCOUNT = 5
GLOBAL_DAY_USD = Decimal("0.75")
GLOBAL_MONTH_USD = Decimal("10")

# Web search credits
SEARCHES_PER_REQUEST = 2
SEARCHES_PER_GUEST_SESSION = 5
SEARCHES_PER_GUEST_IP_WINDOW = 10
SEARCHES_PER_ACCOUNT_DAY = 10
SEARCHES_GLOBAL_DAY = 40
SEARCHES_GLOBAL_MONTH = 800

# Lifetimes
GUEST_SESSION_TTL = timedelta(minutes=240)
ACCOUNT_SESSION_IDLE = timedelta(days=7)
ACCOUNT_SESSION_MAX = timedelta(days=30)
INVITE_TTL = timedelta(days=7)
CRISIS_FLAG_TTL = timedelta(minutes=30)
DECIDED_WRITE_KEPT = timedelta(days=1)  # a repeat tap gets the same answer
# A held log entry has no time limit (Part E #50); its confirmed date and time
LOG_DATE_BACK = timedelta(days=30)
LOG_DATE_AHEAD = timedelta(minutes=5)  # the phone's clock may run a little ahead

# Output and import
TRACE_TO_BROWSER_BYTES = 32 * 1024
IMPORT_TURNS = 50
IMPORT_LOG_ENTRIES = 500
IMPORT_BYTES = 1024 * 1024

# Middleware
FLOOD_REQUESTS_PER_MINUTE = 100
FLOOD_WINDOW = timedelta(minutes=1)
