"""
Tests for Prompt Component System - verify prompts are identical and components work
"""

import pytest
from unittest.mock import Mock
from sqlalchemy.orm import Session
import os

# Set required env vars for testing
os.environ.setdefault('OPENAI_API_KEY', 'test-key')
os.environ.setdefault('GOOGLE_GEMINI_API_KEY', 'test-key')
os.environ.setdefault('JWT_SECRET_KEY', 'test-secret-key-minimum-32-characters-long')


class TestPromptComponents:
    """Test prompt component system"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)
    
    def test_base_humanization_import(self):
        """Test that base humanization can be imported"""
        from app.agents.prompts.base_humanization import BASE_HUMANIZATION
        assert BASE_HUMANIZATION is not None
        assert len(BASE_HUMANIZATION) > 0
        assert "Core Communication Principles" in BASE_HUMANIZATION
    
    def test_coordinator_prompt_import(self):
        """Test that coordinator prompt can be imported and generated"""
        from app.agents.prompts.coordinator_prompt import get_coordinator_prompt
        prompt = get_coordinator_prompt()
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Holos Coordinator Agent" in prompt
    
    def test_fitness_prompt_import(self):
        """Test that fitness prompt can be imported and generated"""
        from app.agents.prompts.fitness_prompt import get_fitness_prompt
        prompt = get_fitness_prompt()
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Physical Fitness Coach" in prompt
    
    def test_nutrition_prompt_import(self):
        """Test that nutrition prompt can be imported and generated"""
        from app.agents.prompts.nutrition_prompt import get_nutrition_prompt
        prompt = get_nutrition_prompt()
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Nutrition Coach" in prompt
    
    def test_mental_fitness_prompt_import(self):
        """Test that mental fitness prompt can be imported and generated"""
        from app.agents.prompts.mental_fitness_prompt import get_mental_fitness_prompt
        prompt = get_mental_fitness_prompt()
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Mental Wellness Coach" in prompt
    
    def test_base_agent_uses_prompt_components(self, mock_db):
        """Test that BaseAgent uses prompt components"""
        from app.agents.base_agent import BaseAgent
        
        agent = BaseAgent(user_id=1, db=mock_db)
        prompt = agent._get_system_prompt()
        
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        # Should use BASE_HUMANIZATION
        from app.agents.prompts.base_humanization import BASE_HUMANIZATION
        assert prompt == BASE_HUMANIZATION
    
    def test_coordinator_agent_uses_prompt_components(self, mock_db):
        """Test that CoordinatorAgent uses prompt components"""
        from app.agents.coordinator_agent import CoordinatorAgent
        
        agent = CoordinatorAgent(user_id=1, db=mock_db)
        prompt = agent._get_system_prompt()
        
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Holos Coordinator Agent" in prompt
    
    def test_physical_fitness_agent_uses_prompt_components(self, mock_db):
        """Test that PhysicalFitnessAgent uses prompt components"""
        from app.agents.physical_fitness_agent import PhysicalFitnessAgent
        
        agent = PhysicalFitnessAgent(user_id=1, db=mock_db)
        prompt = agent._get_system_prompt()
        
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Physical Fitness Coach" in prompt
    
    def test_nutrition_agent_uses_prompt_components(self, mock_db):
        """Test that NutritionAgent uses prompt components"""
        from app.agents.nutrition_agent import NutritionAgent
        
        agent = NutritionAgent(user_id=1, db=mock_db)
        prompt = agent._get_system_prompt()
        
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Nutrition Coach" in prompt
    
    def test_mental_fitness_agent_uses_prompt_components(self, mock_db):
        """Test that MentalFitnessAgent uses prompt components"""
        from app.agents.mental_fitness_agent import MentalFitnessAgent
        
        agent = MentalFitnessAgent(user_id=1, db=mock_db)
        prompt = agent._get_system_prompt()
        
        assert prompt is not None
        assert len(prompt) > 0
        assert "Core Communication Principles" in prompt
        assert "Mental Wellness Coach" in prompt
    
    def test_prompts_include_base_humanization(self):
        """Test that all agent prompts include base humanization"""
        from app.agents.prompts.base_humanization import BASE_HUMANIZATION
        from app.agents.prompts.coordinator_prompt import get_coordinator_prompt
        from app.agents.prompts.fitness_prompt import get_fitness_prompt
        from app.agents.prompts.nutrition_prompt import get_nutrition_prompt
        from app.agents.prompts.mental_fitness_prompt import get_mental_fitness_prompt
        
        # All prompts should start with BASE_HUMANIZATION
        assert get_coordinator_prompt().startswith(BASE_HUMANIZATION)
        assert get_fitness_prompt().startswith(BASE_HUMANIZATION)
        assert get_nutrition_prompt().startswith(BASE_HUMANIZATION)
        assert get_mental_fitness_prompt().startswith(BASE_HUMANIZATION)
    
    def test_prompt_component_reusability(self):
        """Test that base humanization is reused (not duplicated)"""
        from app.agents.prompts.base_humanization import BASE_HUMANIZATION
        from app.agents.prompts.coordinator_prompt import get_coordinator_prompt
        from app.agents.prompts.fitness_prompt import get_fitness_prompt
        
        coord_prompt = get_coordinator_prompt()
        fitness_prompt = get_fitness_prompt()
        
        # Both should include the same base humanization
        assert coord_prompt.startswith(BASE_HUMANIZATION)
        assert fitness_prompt.startswith(BASE_HUMANIZATION)
        
        # Base humanization should only appear once at the start
        assert coord_prompt.count(BASE_HUMANIZATION) == 1
        assert fitness_prompt.count(BASE_HUMANIZATION) == 1

