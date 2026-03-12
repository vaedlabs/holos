"""
Basic tests for agent initialization and structure
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session


class TestAgentInitialization:
    """Test that agents can be initialized correctly"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def mock_env_vars(self, monkeypatch):
        """Set up mock environment variables"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long")
    
    def test_base_agent_initialization(self, mock_db, mock_env_vars):
        """Test that BaseAgent can be initialized"""
        from app.agents.base_agent import BaseAgent
        
        agent = BaseAgent(user_id=1, db=mock_db)
        
        assert agent.user_id == 1
        assert agent.db == mock_db
        assert agent.llm is not None
        assert agent.tools is not None
        assert len(agent.tools) > 0
        assert agent.system_message is not None
    
    def test_physical_fitness_agent_initialization(self, mock_db, mock_env_vars):
        """Test that PhysicalFitnessAgent can be initialized"""
        from app.agents.physical_fitness_agent import PhysicalFitnessAgent
        
        agent = PhysicalFitnessAgent(user_id=1, db=mock_db)
        
        assert agent.user_id == 1
        assert agent.db == mock_db
        assert agent.llm is not None
        assert agent.system_message is not None
        # Check that system message contains fitness-specific content
        assert "fitness" in agent.system_message.lower() or "exercise" in agent.system_message.lower()
    
    def test_nutrition_agent_initialization(self, mock_db, mock_env_vars):
        """Test that NutritionAgent can be initialized"""
        from app.agents.nutrition_agent import NutritionAgent
        
        agent = NutritionAgent(user_id=1, db=mock_db)
        
        assert agent.user_id == 1
        assert agent.db == mock_db
        assert agent.model is not None
        assert agent.system_message is not None
        # Check that system message contains nutrition-specific content
        assert "nutrition" in agent.system_message.lower() or "meal" in agent.system_message.lower()
    
    def test_mental_fitness_agent_initialization(self, mock_db, mock_env_vars):
        """Test that MentalFitnessAgent can be initialized"""
        from app.agents.mental_fitness_agent import MentalFitnessAgent
        
        agent = MentalFitnessAgent(user_id=1, db=mock_db)
        
        assert agent.user_id == 1
        assert agent.db == mock_db
        assert agent.llm is not None
        assert agent.system_message is not None
        # Check that system message contains mental fitness-specific content
        assert "mental" in agent.system_message.lower() or "mindfulness" in agent.system_message.lower()
    
    def test_coordinator_agent_initialization(self, mock_db, mock_env_vars):
        """Test that CoordinatorAgent can be initialized"""
        from app.agents.coordinator_agent import CoordinatorAgent
        
        agent = CoordinatorAgent(user_id=1, db=mock_db)
        
        assert agent.user_id == 1
        assert agent.db == mock_db
        assert agent.llm is not None
        # Coordinator should have sub-agents
        assert agent.physical_agent is not None
        assert agent.nutrition_agent is not None
        assert agent.mental_agent is not None
    
    def test_agent_shared_context(self, mock_db, mock_env_vars):
        """Test that agents can accept shared context"""
        from app.agents.coordinator_agent import CoordinatorAgent
        from app.services.context_manager import context_manager
        
        # Mock context
        shared_context = {
            "medical_history": {
                "conditions": "knee injury",
                "limitations": None,
                "medications": None,
                "notes": None
            },
            "preferences": {
                "goals": "build strength",
                "activity_level": "moderate",
                "dietary_restrictions": None,
                "location": None,
                "exercise_types": None,
                "age": None,
                "gender": None,
                "lifestyle": None
            }
        }
        
        # Coordinator should fetch context and pass to sub-agents
        with patch.object(context_manager, 'get_user_context', return_value=shared_context):
            agent = CoordinatorAgent(user_id=1, db=mock_db)
            
            # Verify coordinator has context
            assert agent._shared_context == shared_context
            
            # Verify sub-agents have context
            assert agent.physical_agent._shared_context == shared_context
            assert agent.nutrition_agent._shared_context == shared_context
            assert agent.mental_agent._shared_context == shared_context
    
    def test_agent_missing_api_key(self, mock_db, monkeypatch):
        """Test that agents raise error when API key is missing"""
        # Remove OPENAI_API_KEY if it exists
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        
        # Need to patch os.getenv at the module level
        import app.agents.base_agent
        original_getenv = app.agents.base_agent.os.getenv
        
        def mock_getenv(key, default=None):
            if key == "OPENAI_API_KEY":
                return None
            return original_getenv(key, default)
        
        app.agents.base_agent.os.getenv = mock_getenv
        
        try:
            from app.agents.base_agent import BaseAgent
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                BaseAgent(user_id=1, db=mock_db)
        finally:
            # Restore original
            app.agents.base_agent.os.getenv = original_getenv
    
    def test_nutrition_agent_missing_gemini_key(self, mock_db):
        """Test that NutritionAgent raises error when Gemini key is missing"""
        from app.agents.nutrition_agent import NutritionAgent
        import os
        
        # Set OpenAI key but not Gemini key
        os.environ["OPENAI_API_KEY"] = "test-key"
        if "GOOGLE_GEMINI_API_KEY" in os.environ:
            del os.environ["GOOGLE_GEMINI_API_KEY"]
        
        with pytest.raises(ValueError, match="GOOGLE_GEMINI_API_KEY"):
            NutritionAgent(user_id=1, db=mock_db)

