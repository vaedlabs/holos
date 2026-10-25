"""Record the provider fixtures with one live run (Plan P2.3). Makes paid calls.

    cd backend && python -m tests.contract.record_providers [openai|gemini] [scenario ...]

Uses OPENAI_API_KEY and GOOGLE_GEMINI_API_KEY from .env. Owner approval needed.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from app.providers import ProviderError

from .http_fixtures import RecordingTransport, save
from .provider_scenarios import PROVIDERS, SCENARIOS, make_provider

KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GOOGLE_GEMINI_API_KEY"}


async def main(selected: list[str]) -> int:
    load_dotenv(".env")
    providers = [s for s in selected if s in PROVIDERS] or list(PROVIDERS)
    selected = [s for s in selected if s not in PROVIDERS]
    tokens_in = tokens_out = 0
    for provider_name in providers:
        for scenario in SCENARIOS:
            if selected and scenario.name not in selected:
                continue
            transport = RecordingTransport()
            provider = make_provider(provider_name, os.environ[KEYS[provider_name]], transport)
            try:
                results = await scenario.run(provider, provider_name)
            except ProviderError as exc:  # recorded too: a real error-mapping fixture
                results = []
                print(f"{provider_name:7} {scenario.name:21} -> {type(exc).__name__}")
            path = save(provider_name, scenario.name, transport.exchanges)
            used = [(r.usage.tokens_in, r.usage.tokens_out) for r in results]
            tokens_in += sum(u[0] for u in used)
            tokens_out += sum(u[1] for u in used)
            print(f"{provider_name:7} {scenario.name:21} {len(transport.exchanges)} exchange(s), "
                  f"tokens {used} -> {path.name}")
    print(f"total tokens: in={tokens_in} out={tokens_out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
