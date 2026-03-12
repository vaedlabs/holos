"""
Business logic services package.

This module contains service classes that implement core business logic,
separated from API routes and database models. Services handle complex
operations, caching, observability, and integrations.

Service Modules:
    - agent_tracer.py: Agent execution tracing and observability
    - prompt_cache.py: In-memory caching for system prompts (token optimization)
    - tool_cache.py: In-memory caching for tool results (reduce redundant calls)
    - llm_retry.py: Retry logic with exponential backoff and model fallback
    - circuit_breaker.py: Circuit breaker pattern for LLM service resilience
    - context_manager.py: User context management with caching
    - medical_service.py: Medical history and exercise conflict detection
    - dietary_service.py: Dietary restriction conflict detection
    - user_service.py: User preferences management

Services are used by routers and agents to perform business operations.
They abstract away complexity and provide reusable functionality.

Usage:
    from app.services import AgentTracer, PromptCache, MedicalService
    
    # Services are instantiated and used by routers/agents
    tracer = AgentTracer(db)
    cache = PromptCache()
"""
