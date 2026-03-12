"""
Prompt components for Holos agents.

This module provides reusable prompt components to reduce token costs and enable
prompt versioning. Prompts are cached in-memory to avoid regenerating identical
system prompts for each agent invocation.

Exported Components:
    - BASE_HUMANIZATION: Universal communication guidelines for all agents
    - get_coordinator_prompt(): Coordinator agent prompt (routing, holistic plans)
    - get_fitness_prompt(): Physical fitness agent prompt (workouts, exercises)
    - get_nutrition_prompt(): Nutrition agent prompt (meals, food analysis)
    - get_mental_fitness_prompt(): Mental fitness agent prompt (wellness, stress)

Prompt Structure:
    Each agent prompt combines:
    1. BASE_HUMANIZATION (universal guidelines)
    2. Agent-specific role and responsibilities
    3. Safety protocols (medical conflicts, dietary restrictions)
    4. Response format guidelines

Caching:
    Prompts are cached by PromptCache service to reduce token usage.
    Cache keys include prompt type and user context version.

Usage:
    from app.agents.prompts import get_fitness_prompt, BASE_HUMANIZATION
    
    # Prompts are used by agents to build system prompts
    system_prompt = get_fitness_prompt(user_context)
"""

from .base_humanization import BASE_HUMANIZATION
from .coordinator_prompt import get_coordinator_prompt
from .fitness_prompt import get_fitness_prompt
from .nutrition_prompt import get_nutrition_prompt
from .mental_fitness_prompt import get_mental_fitness_prompt

# Export all prompt components for convenient importing
# Makes prompts available via: from app.agents.prompts import get_fitness_prompt
__all__ = [
    "BASE_HUMANIZATION",  # Universal communication guidelines
    "get_coordinator_prompt",  # Coordinator agent prompt builder
    "get_fitness_prompt",  # Physical fitness agent prompt builder
    "get_nutrition_prompt",  # Nutrition agent prompt builder
    "get_mental_fitness_prompt",  # Mental fitness agent prompt builder
]

