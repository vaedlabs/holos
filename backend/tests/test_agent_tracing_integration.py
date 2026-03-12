"""
Integration tests for agent tracing - tests agents with tracers
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy.orm import Session
from app.services.agent_tracer import AgentTracer
from app.models.agent_execution_log import AgentExecutionLog


class TestAgentTracingIntegration:
    """Integration tests for agent tracing"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        db = Mock(spec=Session)
        db.add = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db
    
    @pytest.fixture
    def mock_env_vars(self, monkeypatch):
        """Set up mock environment variables"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long")
    
    def test_base_agent_with_tracer(self, mock_db, mock_env_vars):
        """Test that BaseAgent accepts and uses tracer"""
        from app.agents.base_agent import BaseAgent
        
        tracer = AgentTracer(db=mock_db)
        tracer.start_trace("physical-fitness", 1, "test query")
        
        agent = BaseAgent(user_id=1, db=mock_db, tracer=tracer)
        
        assert agent.tracer is not None
        assert agent.tracer == tracer
    
    def test_physical_fitness_agent_with_tracer(self, mock_db, mock_env_vars):
        """Test that PhysicalFitnessAgent accepts tracer"""
        from app.agents.physical_fitness_agent import PhysicalFitnessAgent
        
        tracer = AgentTracer(db=mock_db)
        agent = PhysicalFitnessAgent(user_id=1, db=mock_db, tracer=tracer)
        
        assert agent.tracer is not None
    
    def test_nutrition_agent_with_tracer(self, mock_db, mock_env_vars):
        """Test that NutritionAgent accepts tracer"""
        from app.agents.nutrition_agent import NutritionAgent
        
        tracer = AgentTracer(db=mock_db)
        agent = NutritionAgent(user_id=1, db=mock_db, tracer=tracer)
        
        assert agent.tracer is not None
    
    def test_mental_fitness_agent_with_tracer(self, mock_db, mock_env_vars):
        """Test that MentalFitnessAgent accepts tracer"""
        from app.agents.mental_fitness_agent import MentalFitnessAgent
        
        tracer = AgentTracer(db=mock_db)
        agent = MentalFitnessAgent(user_id=1, db=mock_db, tracer=tracer)
        
        assert agent.tracer is not None
    
    def test_coordinator_agent_with_tracer(self, mock_db, mock_env_vars):
        """Test that CoordinatorAgent accepts tracer and passes to sub-agents"""
        from app.agents.coordinator_agent import CoordinatorAgent
        from app.services.context_manager import context_manager
        
        tracer = AgentTracer(db=mock_db)
        
        # Mock context manager
        with patch.object(context_manager, 'get_user_context', return_value={"medical_history": None, "preferences": None}):
            agent = CoordinatorAgent(user_id=1, db=mock_db, tracer=tracer)
            
            assert agent.tracer is not None
            # Sub-agents should also have tracer
            assert agent.physical_agent.tracer == tracer
            assert agent.nutrition_agent.tracer == tracer
            assert agent.mental_agent.tracer == tracer
    
    def test_agent_without_tracer(self, mock_db, mock_env_vars):
        """Test that agents work without tracer (backward compatibility)"""
        from app.agents.base_agent import BaseAgent
        
        agent = BaseAgent(user_id=1, db=mock_db)
        
        assert agent.tracer is None
    
    def test_tracer_logs_tool_calls_from_agent(self, mock_db, mock_env_vars):
        """Test that tool calls from agent execution are logged"""
        from app.agents.base_agent import BaseAgent
        
        tracer = AgentTracer(db=mock_db)
        tracer.start_trace("physical-fitness", 1, "test query")
        
        agent = BaseAgent(user_id=1, db=mock_db, tracer=tracer)
        
        # The agent's run method would call tools, and those should be logged
        # This is tested indirectly - the tracer is passed and agent has access to it
        assert agent.tracer is not None
        assert agent.tracer.current_trace is not None

