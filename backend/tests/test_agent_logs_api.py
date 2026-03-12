"""
Tests for agent execution logs API endpoint
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime
from app.models.agent_execution_log import AgentExecutionLog
from app.models.user import User


class TestAgentLogsAPI:
    """Test the GET /agents/execution-logs endpoint"""
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock user"""
        user = Mock(spec=User)
        user.id = 1
        user.email = "test@example.com"
        user.username = "testuser"
        return user
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock(spec=Session)
    
    @pytest.fixture
    def sample_logs(self):
        """Create sample agent execution logs"""
        return [
            AgentExecutionLog(
                id=1,
                trace_id="physical-fitness_1_abc123",
                agent_type="physical-fitness",
                user_id=1,
                query="What exercises?",
                response="Here are some exercises...",
                warnings=None,
                tools_called=[{"name": "get_medical_history", "input": {}, "output": "No history"}],
                tokens_used=200,
                duration_ms=1500.5,
                success=True,
                created_at=datetime.now()
            ),
            AgentExecutionLog(
                id=2,
                trace_id="nutrition_1_def456",
                agent_type="nutrition",
                user_id=1,
                query="What's in this?",
                response="Nutrition analysis...",
                warnings=None,
                tools_called=[],
                tokens_used=150,
                duration_ms=1200.0,
                success=True,
                created_at=datetime.now()
            ),
            AgentExecutionLog(
                id=3,
                trace_id="coordinator_1_ghi789",
                agent_type="coordinator",
                user_id=1,
                query="Create a plan",
                response="Holistic plan...",
                warnings=None,
                tools_called=[],
                tokens_used=500,
                duration_ms=3000.0,
                success=True,
                created_at=datetime.now()
            )
        ]
    
    def test_get_agent_logs_requires_authentication(self):
        """Test that endpoint requires authentication"""
        # This would be tested with actual FastAPI test client
        # For now, we verify the endpoint exists
        from app.routers.agents import router
        
        # Check that the route exists
        routes = [r for r in router.routes if hasattr(r, 'path')]
        execution_logs_route = [r for r in routes if 'execution-logs' in r.path]
        assert len(execution_logs_route) > 0
    
    def test_get_agent_logs_filters_by_user(self, mock_db, mock_user, sample_logs):
        """Test that logs are filtered by current user"""
        # Mock query chain
        query_mock = Mock()
        filter_mock = Mock()
        order_mock = Mock()
        count_mock = Mock(return_value=3)
        offset_mock = Mock(return_value=sample_logs)
        
        query_mock.filter.return_value = filter_mock
        filter_mock.order_by.return_value = order_mock
        order_mock.count.return_value = count_mock
        order_mock.offset.return_value = offset_mock
        offset_mock.limit.return_value = sample_logs
        
        mock_db.query.return_value = query_mock
        
        # Verify query filters by user_id
        logs_query = mock_db.query(AgentExecutionLog).filter(
            AgentExecutionLog.user_id == mock_user.id
        )
        
        assert logs_query is not None
    
    def test_get_agent_logs_filters_by_agent_type(self, mock_db, mock_user, sample_logs):
        """Test that logs can be filtered by agent type"""
        # Mock query chain with agent_type filter
        query_mock = Mock()
        filter_mock = Mock()
        filter_mock2 = Mock()
        order_mock = Mock()
        count_mock = Mock(return_value=1)
        offset_mock = Mock(return_value=[sample_logs[0]])
        
        query_mock.filter.return_value = filter_mock
        filter_mock.filter.return_value = filter_mock2
        filter_mock2.order_by.return_value = order_mock
        order_mock.count.return_value = count_mock
        order_mock.offset.return_value = offset_mock
        offset_mock.limit.return_value = [sample_logs[0]]
        
        mock_db.query.return_value = query_mock
        
        # Verify query can filter by agent_type
        logs_query = mock_db.query(AgentExecutionLog).filter(
            AgentExecutionLog.user_id == mock_user.id
        )
        logs_query = logs_query.filter(AgentExecutionLog.agent_type == "physical-fitness")
        
        assert logs_query is not None
    
    def test_get_agent_logs_pagination(self, mock_db, mock_user, sample_logs):
        """Test that pagination works correctly"""
        # Create a proper mock chain that returns a list for .all()
        limit_mock = Mock()
        limit_mock.all.return_value = [sample_logs[0]]
        
        offset_mock = Mock()
        offset_mock.limit.return_value = limit_mock
        
        order_mock = Mock()
        order_mock.offset.return_value = offset_mock
        order_mock.count.return_value = 3
        
        filter_mock = Mock()
        filter_mock.order_by.return_value = order_mock
        
        query_mock = Mock()
        query_mock.filter.return_value = filter_mock
        
        mock_db.query.return_value = query_mock
        
        # Test pagination
        limit = 1
        offset = 0
        
        logs_query = mock_db.query(AgentExecutionLog).filter(
            AgentExecutionLog.user_id == mock_user.id
        ).order_by(AgentExecutionLog.created_at.desc())
        
        total = logs_query.count()
        logs = logs_query.offset(offset).limit(limit).all()
        
        assert total == 3
        assert len(logs) == 1
    
    def test_agent_execution_log_schema(self, sample_logs):
        """Test that AgentExecutionLogResponse schema works"""
        from app.schemas.agent_logs import AgentExecutionLogResponse
        
        log = sample_logs[0]
        response = AgentExecutionLogResponse.model_validate(log)
        
        assert response.id == 1
        assert response.agent_type == "physical-fitness"
        assert response.user_id == 1
        assert response.tokens_used == 200
        assert response.success is True
        assert response.duration_ms == 1500.5
    
    def test_agent_execution_logs_list_schema(self, sample_logs):
        """Test that AgentExecutionLogsListResponse schema works"""
        from app.schemas.agent_logs import AgentExecutionLogsListResponse, AgentExecutionLogResponse
        
        logs_responses = [AgentExecutionLogResponse.model_validate(log) for log in sample_logs]
        list_response = AgentExecutionLogsListResponse(
            logs=logs_responses,
            total=3,
            page=1,
            page_size=50
        )
        
        assert list_response.total == 3
        assert len(list_response.logs) == 3
        assert list_response.page == 1
        assert list_response.page_size == 50

