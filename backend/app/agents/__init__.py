"""
AI agent modules package.

This module contains LangChain-based AI agents that provide specialized
fitness, nutrition, and mental wellness guidance. Agents use LLMs (OpenAI,
Google Gemini) with tool calling capabilities.

Agent Modules:
    - base_agent.py: Base agent class with common tools and execution logic
    - physical_fitness_agent.py: Workout planning and exercise recommendations
    - nutrition_agent.py: Meal planning and food analysis (includes Gemini Vision)
    - mental_fitness_agent.py: Mental wellness and stress management guidance
    - coordinator_agent.py: Query routing and holistic plan creation
    - reasoning_patterns.py: Structured reasoning patterns for safety and validation

Agent Features:
    - Tool calling (medical history, user preferences, web search)
    - Safety checks (exercise conflicts, dietary restrictions)
    - Retry logic with exponential backoff
    - Observability (execution tracing)
    - Caching (prompts, tool results, user context)
    - Streaming support (SSE for coordinator agent)

Usage:
    from app.agents import PhysicalFitnessAgent, NutritionAgent
    
    # Agents are instantiated with database session and configuration
    agent = PhysicalFitnessAgent(db=db, user_id=user_id)
    response = agent.run("Create a workout plan")
"""
