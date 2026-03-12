"""
Tests for Agent Tracer - agent observability and tracing
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from sqlalchemy.orm import Session
from app.services.agent_tracer import AgentTracer
from app.models.agent_execution_log import AgentExecutionLog


class TestAgentTracer:
    """Test AgentTracer functionality"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        db = Mock(spec=Session)
        db.add = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        return db
    
    @pytest.fixture
    def tracer(self, mock_db):
        """Create an AgentTracer instance"""
        return AgentTracer(db=mock_db)
    
    def test_start_trace(self, tracer):
        """Test that starting a trace creates a trace with correct data"""
        trace_id = tracer.start_trace(
            agent_type="physical-fitness",
            user_id=1,
            query="What exercises should I do?",
            image_base64=None
        )
        
        assert trace_id is not None
        assert tracer.current_trace is not None
        assert tracer.current_trace["agent_type"] == "physical-fitness"
        assert tracer.current_trace["user_id"] == 1
        assert tracer.current_trace["query"] == "What exercises should I do?"
        assert tracer.current_trace["image_base64"] is False
        assert tracer.current_trace["tools_called"] == []
        assert tracer.current_trace["tokens_used"] == 0
        assert tracer.current_trace["steps"] == []
        assert "start_time" in tracer.current_trace
    
    def test_start_trace_with_image(self, tracer):
        """Test that starting a trace with image sets image_base64 flag"""
        trace_id = tracer.start_trace(
            agent_type="nutrition",
            user_id=1,
            query="What's in this image?",
            image_base64="base64string"
        )
        
        assert tracer.current_trace["image_base64"] is True
    
    def test_log_tool_call(self, tracer):
        """Test that tool calls are logged correctly"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        tracer.log_tool_call(
            tool_name="get_medical_history",
            tool_input={"query": ""},
            tool_output="No medical history"
        )
        
        assert len(tracer.current_trace["tools_called"]) == 1
        tool_call = tracer.current_trace["tools_called"][0]
        assert tool_call["name"] == "get_medical_history"
        assert tool_call["input"] == {"query": ""}
        assert tool_call["output"] == "No medical history"
        assert "timestamp" in tool_call
    
    def test_log_tool_call_truncates_long_output(self, tracer):
        """Test that long tool outputs are truncated"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        long_output = "x" * 1000
        tracer.log_tool_call(
            tool_name="test_tool",
            tool_input={},
            tool_output=long_output
        )
        
        tool_call = tracer.current_trace["tools_called"][0]
        assert len(tool_call["output"]) <= 515  # 500 + "... (truncated)" (15 chars)
        assert "... (truncated)" in tool_call["output"]
    
    def test_log_step(self, tracer):
        """Test that steps are logged correctly"""
        tracer.start_trace("coordinator", 1, "test query")
        
        tracer.log_step("Analyzing your query...")
        tracer.log_step("Routing to Physical Fitness Agent...")
        
        assert len(tracer.current_trace["steps"]) == 2
        assert tracer.current_trace["steps"][0]["step"] == "Analyzing your query..."
        assert tracer.current_trace["steps"][1]["step"] == "Routing to Physical Fitness Agent..."
        assert "timestamp" in tracer.current_trace["steps"][0]
    
    def test_log_tokens(self, tracer):
        """Test that token usage is tracked"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        tracer.log_tokens(100)
        tracer.log_tokens(50)
        
        assert tracer.current_trace["tokens_used"] == 150
    
    def test_log_warning(self, tracer):
        """Test that warnings are logged"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        tracer.log_warning("Exercise may conflict with medical condition")
        tracer.log_warning("Another warning")
        
        assert len(tracer.current_trace["warnings"]) == 2
        assert "Exercise may conflict with medical condition" in tracer.current_trace["warnings"]
        assert "Another warning" in tracer.current_trace["warnings"]
    
    def test_log_warning_no_duplicates(self, tracer):
        """Test that duplicate warnings are not added"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        tracer.log_warning("Same warning")
        tracer.log_warning("Same warning")
        
        assert len(tracer.current_trace["warnings"]) == 1
    
    def test_end_trace_success(self, tracer, mock_db):
        """Test that ending a trace persists to database"""
        tracer.start_trace("physical-fitness", 1, "What exercises?")
        tracer.log_tool_call("get_medical_history", {}, "No history")
        tracer.log_tokens(200)
        
        tracer.end_trace(
            response="Here are some exercises...",
            warnings=["Warning message"],
            success=True
        )
        
        # Verify database operations
        assert mock_db.add.called
        assert mock_db.commit.called
        
        # Verify the log entry was created with correct data
        call_args = mock_db.add.call_args[0][0]
        assert isinstance(call_args, AgentExecutionLog)
        assert call_args.agent_type == "physical-fitness"
        assert call_args.user_id == 1
        assert call_args.success is True
        assert call_args.tokens_used == 200
        assert call_args.duration_ms is not None
        assert call_args.duration_ms > 0
        
        # Verify trace is cleared
        assert tracer.current_trace is None
    
    def test_end_trace_truncates_response(self, tracer, mock_db):
        """Test that long responses are truncated"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        long_response = "x" * 2000
        tracer.end_trace(response=long_response, warnings=None, success=True)
        
        call_args = mock_db.add.call_args[0][0]
        assert len(call_args.response) <= 1015  # 1000 + "... (truncated)" (15 chars)
        assert "... (truncated)" in call_args.response
    
    def test_end_trace_failure(self, tracer, mock_db):
        """Test that failed traces are logged correctly"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        tracer.end_trace(
            response="Error occurred",
            warnings=None,
            success=False,
            error="Test error"
        )
        
        call_args = mock_db.add.call_args[0][0]
        assert call_args.success is False
    
    def test_end_trace_handles_exception(self, tracer, mock_db):
        """Test that exceptions during persistence are handled gracefully"""
        tracer.start_trace("physical-fitness", 1, "test query")
        
        # Make commit raise an exception
        mock_db.commit.side_effect = Exception("Database error")
        
        # Should not raise, but should rollback
        tracer.end_trace(response="test", warnings=None, success=True)
        
        assert mock_db.rollback.called
        assert tracer.current_trace is None  # Should still clear trace
    
    def test_log_tool_call_no_trace(self, tracer):
        """Test that logging without active trace doesn't crash"""
        # Don't start trace
        tracer.log_tool_call("test_tool", {}, "output")
        
        # Should not raise exception
        assert tracer.current_trace is None
    
    def test_log_step_no_trace(self, tracer):
        """Test that logging step without active trace doesn't crash"""
        tracer.log_step("test step")
        
        # Should not raise exception
        assert tracer.current_trace is None
    
    def test_get_current_trace_id(self, tracer):
        """Test getting current trace ID"""
        assert tracer.get_current_trace_id() is None
        
        trace_id = tracer.start_trace("physical-fitness", 1, "test")
        assert tracer.get_current_trace_id() == trace_id
        
        tracer.end_trace("response", None, True)
        assert tracer.get_current_trace_id() is None


class TestAgentExecutionLogModel:
    """Test AgentExecutionLog model structure"""
    
    def test_model_fields(self):
        """Test that model has all required fields"""
        from app.models.agent_execution_log import AgentExecutionLog
        
        # Check that model exists and has expected attributes
        assert hasattr(AgentExecutionLog, 'id')
        assert hasattr(AgentExecutionLog, 'trace_id')
        assert hasattr(AgentExecutionLog, 'agent_type')
        assert hasattr(AgentExecutionLog, 'user_id')
        assert hasattr(AgentExecutionLog, 'query')
        assert hasattr(AgentExecutionLog, 'response')
        assert hasattr(AgentExecutionLog, 'warnings')
        assert hasattr(AgentExecutionLog, 'tools_called')
        assert hasattr(AgentExecutionLog, 'tokens_used')
        assert hasattr(AgentExecutionLog, 'duration_ms')
        assert hasattr(AgentExecutionLog, 'success')
        assert hasattr(AgentExecutionLog, 'created_at')

