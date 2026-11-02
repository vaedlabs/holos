"""The process-wide services a chat request uses (Plan C.9): one OpenAI client, one
breaker per provider, one scheduler, one backup budget, the router, the three coaches,
the summary call and web search. Built once per process; tests pass their own.

    services = get_services()
    services.coaches["physical"].run(...)
"""

import os
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.agents.base import MODEL, BaseAgent
from app.agents.mental import MentalAgent
from app.agents.nutrition import NutritionAgent
from app.agents.physical import PhysicalAgent
from app.agents.schemas import AgentName
from app.agents.tools.web_search import WebSearch, get_web_search
from app.orchestration.router import Router
from app.providers import Backups, Breakers, GenerateOptions, ResilientProvider, Route
from app.providers.base import LLMProvider
from app.providers.resilient import CircuitBreaker
from app.providers.scheduler import FairScheduler

# The router answers in ~25 tokens; Holos's own reply is up to 400 characters (C.15)
ROUTER_OPTIONS = GenerateOptions(model=MODEL, max_output_tokens=300)
# The multi-coach summary: free text, at most 600 characters (C.3)
SUMMARY_OPTIONS = GenerateOptions(model=MODEL, max_output_tokens=300)
COACHES: dict[AgentName, type[BaseAgent]] = {
    "physical": PhysicalAgent, "nutrition": NutritionAgent, "mental": MentalAgent}


@dataclass
class Services:
    router: Router
    coaches: dict[AgentName, BaseAgent]
    summary: ResilientProvider
    search: WebSearch | None
    breaker: CircuitBreaker  # the chat provider's: admission refuses while it is open


def build_services(provider: LLMProvider, *, search: WebSearch | None = None,
                   breakers: Breakers | None = None, scheduler: FairScheduler | None = None,
                   backups: Backups | None = None) -> Services:
    breakers = breakers or Breakers()
    scheduler = scheduler or FairScheduler()
    backups = backups or Backups()

    def llm(options: GenerateOptions) -> ResilientProvider:
        return ResilientProvider(Route(provider, options), None, breakers, scheduler, backups)

    return Services(
        router=Router(llm(ROUTER_OPTIONS)),
        coaches={name: cls(llm(cls.options())) for name, cls in COACHES.items()},
        summary=llm(SUMMARY_OPTIONS),
        search=search,
        breaker=breakers[provider.name],
    )


@lru_cache(maxsize=1)
def get_services() -> Services:
    from app.dependencies import get_state_store
    from app.providers.openai import OpenAIProvider

    provider = OpenAIProvider(os.environ["OPENAI_API_KEY"],
                              http_client=httpx.AsyncClient(timeout=120))
    search = get_web_search(get_state_store()) if os.environ.get("TAVILY_API_KEY") else None
    return build_services(provider, search=search)
