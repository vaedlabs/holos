"""
Prompt components for Holos agents.
This module provides reusable prompt components to reduce token costs and enable prompt versioning.
"""

from .base_humanization import BASE_HUMANIZATION
from .coordinator_prompt import get_coordinator_prompt
from .fitness_prompt import get_fitness_prompt
from .nutrition_prompt import get_nutrition_prompt
from .mental_fitness_prompt import get_mental_fitness_prompt

__all__ = [
    "BASE_HUMANIZATION",
    "get_coordinator_prompt",
    "get_fitness_prompt",
    "get_nutrition_prompt",
    "get_mental_fitness_prompt",
]

