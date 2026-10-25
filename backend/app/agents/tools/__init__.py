"""Agent tools (Plan C.10). The old LangChain tools live in tools/legacy until P4.12."""

from app.agents.schemas import AgentName

from .base import GateHook, GateResult, Tool, ToolContext, allow_all
from .read import GET_RECENT_LOGS
from .web_search import WEB_SEARCH, WebSearch, get_web_search
from .write import LOG_MEAL, LOG_PRACTICE, LOG_WORKOUT

# Which tools each agent gets (Plan C.10 table)
AGENT_TOOLS: dict[AgentName, tuple[Tool, ...]] = {
    "physical": (GET_RECENT_LOGS, WEB_SEARCH, LOG_WORKOUT),
    "nutrition": (GET_RECENT_LOGS, WEB_SEARCH, LOG_MEAL),
    "mental": (GET_RECENT_LOGS, WEB_SEARCH, LOG_PRACTICE),
}

__all__ = [
    "AGENT_TOOLS",
    "GateHook",
    "GateResult",
    "Tool",
    "ToolContext",
    "WebSearch",
    "allow_all",
    "get_web_search",
]
