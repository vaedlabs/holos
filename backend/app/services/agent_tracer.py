"""
Agent Tracer - tracks agent execution for observability and debugging.

This module provides the AgentTracer class, which implements observability tracking
for AI agent executions. It collects detailed information about agent interactions,
including queries, responses, tool calls, token usage, and performance metrics.

Key Features:
- Trace lifecycle management (start -> log -> end)
- Tool call tracking with inputs and outputs
- Token usage tracking
- Performance metrics (duration, success rate)
- Warning tracking
- Step-by-step execution logging (for coordinator agent)
- Database persistence of execution logs

Usage Pattern:
    1. Create AgentTracer instance with database session
    2. Call start_trace() at the beginning of agent execution
    3. Call log methods (log_tool_call, log_tokens, log_warning, etc.) during execution
    4. Call end_trace() at the end to persist the trace to database

The tracer is designed to be lightweight and non-blocking, with error handling
to ensure agent execution continues even if tracing fails.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.agent_execution_log import AgentExecutionLog
import json
import logging
import uuid

# Logger instance for this module
# Used for logging trace events and errors
logger = logging.getLogger(__name__)


class AgentTracer:
    """
    Tracks agent execution for observability, debugging, and optimization.
    
    This class provides comprehensive tracking of AI agent executions, collecting
    detailed information about queries, responses, tool usage, token consumption,
    and performance metrics. The collected data is persisted to the database for
    analysis, debugging, and optimization.
    
    Trace Lifecycle:
        1. start_trace(): Initialize a new trace with query and agent type
        2. log_* methods: Record events during execution (tool calls, tokens, warnings)
        3. end_trace(): Persist the complete trace to database
    
    Key Capabilities:
        - Tool call tracking: Records which tools were called with inputs/outputs
        - Token usage tracking: Accumulates token consumption across LLM calls
        - Performance metrics: Calculates execution duration and success rate
        - Warning tracking: Collects warnings about degraded functionality or issues
        - Step logging: Records step-by-step updates (for coordinator agent)
        
    Attributes:
        db: Database session for persisting execution logs
        current_trace: Dictionary storing current trace data (None when no active trace)
        
    Note:
        - Only one trace can be active at a time per AgentTracer instance
        - Trace data is stored in memory until end_trace() is called
        - Errors during tracing don't affect agent execution (fail gracefully)
        - Trace data is truncated to manage storage (response: 1000 chars, query: 500 chars)
    """
    
    def __init__(self, db: Session):
        """
        Initialize AgentTracer with database session.
        
        Args:
            db: SQLAlchemy database session for persisting execution logs
            
        Note:
            The database session should be provided by the caller and will be used
            to persist execution logs. The tracer doesn't manage session lifecycle.
        """
        # Database session for persisting execution logs
        # Provided by caller (typically from FastAPI dependency injection)
        self.db = db
        
        # Current trace data dictionary (None when no trace is active)
        # Structure: {
        #     "trace_id": str,
        #     "agent_type": str,
        #     "user_id": int,
        #     "query": str,
        #     "image_base64": bool,
        #     "start_time": datetime,
        #     "tools_called": List[Dict],
        #     "tokens_used": int,
        #     "steps": List[Dict],
        #     "warnings": List[str]
        # }
        self.current_trace: Optional[Dict] = None
    
    def start_trace(
        self, 
        agent_type: str, 
        user_id: int, 
        query: str,
        image_base64: Optional[str] = None
    ) -> str:
        """
        Start a new trace for an agent execution.
        
        This method initializes a new trace, generating a unique trace ID and
        storing initial trace data. Must be called before any log_* methods.
        
        Args:
            agent_type: Type of agent executing (coordinator, physical-fitness, nutrition, mental-fitness)
            user_id: User ID making the request
            query: User's query/input text
            image_base64: Optional base64-encoded image (for nutrition agent food analysis)
        
        Returns:
            str: Unique trace identifier for this execution
            
        Trace ID Format:
            Format: "{agent_type}_{user_id}_{uuid}_{timestamp}"
            Example: "nutrition_123_a1b2c3d4_1704067200000"
            
            Components:
            - agent_type: Type of agent
            - user_id: User making the request
            - uuid: Random 8-character hex string for uniqueness
            - timestamp: Milliseconds since epoch for chronological ordering
            
        Note:
            - If a trace is already active, it will be overwritten
            - Image data is not stored (only boolean flag indicating presence)
            - Trace data accumulates until end_trace() is called
        """
        # Generate unique trace ID
        # Format: {agent_type}_{user_id}_{random_uuid}_{timestamp_ms}
        # This ensures uniqueness and allows easy filtering/sorting
        trace_id = f"{agent_type}_{user_id}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp() * 1000)}"
        
        # Initialize trace data structure
        # All tracking data accumulates in this dictionary until end_trace()
        self.current_trace = {
            "trace_id": trace_id,  # Unique identifier for this trace
            "agent_type": agent_type,  # Type of agent executing
            "user_id": user_id,  # User making the request
            "query": query,  # User's input query (may be truncated on persistence)
            "image_base64": image_base64 is not None,  # Boolean flag (don't store actual image data)
            "start_time": datetime.now(),  # Trace start time (for duration calculation)
            "tools_called": [],  # List of tool calls (accumulated during execution)
            "tokens_used": 0,  # Total tokens consumed (accumulated during execution)
            "steps": [],  # Step-by-step updates (for coordinator agent)
            "warnings": []  # Warning messages (accumulated during execution)
        }
        
        logger.debug(f"Started trace {trace_id} for agent {agent_type}, user {user_id}")
        return trace_id
    
    def log_tool_call(self, tool_name: str, tool_input: Dict, tool_output: str):
        """
        Log a tool call during agent execution.
        
        This method records when an agent calls a tool, storing the tool name,
        input parameters, and output. Tool calls are accumulated in the trace
        and persisted when end_trace() is called.
        
        Args:
            tool_name: Name of the tool called (e.g., "get_medical_history", "create_workout_log")
            tool_input: Dictionary containing input parameters passed to the tool
            tool_output: Output string from the tool (will be truncated to 500 chars)
            
        Tool Call Structure:
            Each tool call is stored as a dictionary:
            {
                "name": "get_medical_history",
                "input": {"query": ""},
                "output": "No medical history on file.",
                "timestamp": "2024-01-01T12:00:00"
            }
            
        Note:
            - Tool output is truncated to 500 characters to manage storage
            - If no trace is active, logs a warning and returns (non-blocking)
            - Tool calls are stored in chronological order
            - Used for debugging and understanding agent behavior
        """
        # Check if trace is active
        # If not, log warning and return (don't block agent execution)
        if not self.current_trace:
            logger.warning("log_tool_call called but no active trace")
            return
        
        # Truncate long outputs to manage storage
        # Tool outputs can be very long (e.g., web search results)
        # Keep first 500 characters for debugging purposes
        output_preview = tool_output[:500] if tool_output else ""
        if tool_output and len(tool_output) > 500:
            output_preview += "... (truncated)"
        
        # Append tool call to trace data
        # Tool calls are stored in chronological order
        self.current_trace["tools_called"].append({
            "name": tool_name,  # Tool identifier
            "input": tool_input,  # Input parameters (full dictionary)
            "output": output_preview,  # Output (truncated to 500 chars)
            "timestamp": datetime.now().isoformat()  # ISO format timestamp
        })
        
        logger.debug(f"Logged tool call: {tool_name}")
    
    def log_step(self, step: str):
        """
        Log a step in the agent execution process.
        
        This method records step-by-step updates during agent execution. Primarily
        used by the coordinator agent to show what it's doing (e.g., "Analyzing query...",
        "Routing to Physical Fitness Agent...").
        
        Args:
            step: Description of the current step (e.g., "Analyzing query", "Creating holistic plan")
            
        Step Structure:
            Each step is stored as a dictionary:
            {
                "step": "Analyzing query...",
                "timestamp": "2024-01-01T12:00:00"
            }
            
        Note:
            - If no trace is active, logs a warning and returns (non-blocking)
            - Steps are stored in chronological order
            - Used for coordinator agent to provide real-time updates to users
            - Steps can be streamed to clients via Server-Sent Events (SSE)
        """
        # Check if trace is active
        if not self.current_trace:
            logger.warning("log_step called but no active trace")
            return
        
        # Append step to trace data
        # Steps are stored in chronological order for coordinator agent updates
        self.current_trace["steps"].append({
            "step": step,  # Step description
            "timestamp": datetime.now().isoformat()  # ISO format timestamp
        })
    
    def log_tokens(self, tokens: int):
        """
        Log token usage during agent execution.
        
        This method accumulates token consumption across multiple LLM calls.
        Token usage is tracked for cost analysis and optimization.
        
        Args:
            tokens: Number of tokens consumed in this call (will be added to total)
            
        Token Tracking:
            - Tokens are accumulated across all LLM calls during execution
            - Includes both input tokens (prompt, context) and output tokens (response)
            - Used for cost tracking and identifying high-token queries
            
        Note:
            - If no trace is active, logs a warning and returns (non-blocking)
            - Token count is accumulated (not replaced) for multiple calls
            - Final token count is persisted when end_trace() is called
        """
        # Check if trace is active
        if not self.current_trace:
            logger.warning("log_tokens called but no active trace")
            return
        
        # Accumulate token usage
        # Tokens from multiple LLM calls are summed together
        self.current_trace["tokens_used"] += tokens
    
    def log_warning(self, warning: str):
        """
        Log a warning during agent execution.
        
        This method records warnings about issues, limitations, or degraded functionality
        during agent execution. Warnings are collected and returned to users.
        
        Args:
            warning: Warning message string (e.g., "Exercise may conflict with knee injury",
                     "Using fallback model due to API errors")
            
        Warning Types:
            - Safety warnings: Exercise conflicts with medical conditions
            - Data quality warnings: Incomplete or missing information
            - Service degradation warnings: Fallback models used, timeouts, etc.
            - Performance warnings: Slow queries, high token usage
            
        Note:
            - If no trace is active, logs a warning and returns (non-blocking)
            - Duplicate warnings are automatically filtered (only unique warnings stored)
            - Warnings are persisted and returned to users in API responses
        """
        # Check if trace is active
        if not self.current_trace:
            logger.warning("log_warning called but no active trace")
            return
        
        # Add warning if not already present (avoid duplicates)
        # Warnings are stored as a list of unique strings
        if warning not in self.current_trace["warnings"]:
            self.current_trace["warnings"].append(warning)
    
    def log_timeout(self, timeout_seconds: float, operation: str = "LLM call"):
        """
        Log a timeout event during agent execution.
        
        This method records when an operation (typically an LLM call) exceeds its
        timeout limit. Timeouts are logged as warnings and tracked for analysis.
        
        Args:
            timeout_seconds: Timeout duration in seconds that was exceeded
            operation: Description of the operation that timed out (default: "LLM call")
                       Examples: "LLM call", "Gemini image analysis", "Tool execution"
            
        Timeout Handling:
            - Timeouts are logged as warnings
            - Timeout messages follow format: "{operation} timed out after {timeout_seconds} seconds"
            - Used to identify slow queries and optimize timeout settings
            
        Note:
            - If no trace is active, logs a warning and returns (non-blocking)
            - Timeout warnings are added to the warnings list
            - Helps identify performance issues and optimize timeout configurations
        """
        # Check if trace is active
        if not self.current_trace:
            logger.warning("log_timeout called but no active trace")
            return
        
        # Create timeout warning message
        # Format: "{operation} timed out after {timeout_seconds} seconds"
        timeout_msg = f"{operation} timed out after {timeout_seconds} seconds"
        
        # Add timeout warning if not already present
        if timeout_msg not in self.current_trace["warnings"]:
            self.current_trace["warnings"].append(timeout_msg)
        
        # Log timeout event for monitoring
        logger.warning(f"Timeout in trace {self.current_trace.get('trace_id')}: {timeout_msg}")
    
    def end_trace(
        self, 
        response: str, 
        warnings: Optional[List[str]] = None, 
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        End the current trace and persist it to the database.
        
        This method finalizes the trace, calculates performance metrics, and persists
        all collected data to the database. This is the final step in the trace lifecycle.
        
        Args:
            response: Agent's final response text (will be truncated to 1000 chars)
            warnings: Optional list of additional warning messages to merge with trace warnings
            success: Whether execution completed successfully (default: True)
            error: Optional error message if execution failed
            
        Performance Metrics Calculated:
            - duration_ms: Total execution time in milliseconds
            - Calculated as: (end_time - start_time) * 1000
            
        Data Truncation:
            - response: Truncated to 1000 characters (with "... (truncated)" suffix)
            - query: Truncated to 500 characters (if present)
            - Tool outputs: Already truncated to 500 chars in log_tool_call()
            
        Warning Merging:
            - Warnings from trace are merged with provided warnings parameter
            - Duplicates are removed while preserving order
            - Empty warning lists are stored as None
            
        Database Persistence:
            - Creates AgentExecutionLog model instance with all trace data
            - Commits to database (atomic operation)
            - On error, rolls back transaction and logs error (doesn't raise)
            
        Note:
            - If no trace is active, logs a warning and returns (non-blocking)
            - Errors during persistence are logged but don't affect agent execution
            - Trace is cleared after persistence (success or failure)
            - Always clears current_trace in finally block to prevent memory leaks
        """
        # Check if trace is active
        if not self.current_trace:
            logger.warning("end_trace called but no active trace")
            return
        
        try:
            # Calculate execution duration
            # Duration is calculated from start_time to current time
            end_time = datetime.now()
            duration_ms = (end_time - self.current_trace["start_time"]).total_seconds() * 1000
            
            # Merge warnings from trace and provided parameter
            # Start with warnings collected during execution
            all_warnings = list(self.current_trace["warnings"])
            # Add any additional warnings provided as parameter
            if warnings:
                all_warnings.extend(warnings)
            # Remove duplicates while preserving order
            # dict.fromkeys() preserves insertion order (Python 3.7+)
            all_warnings = list(dict.fromkeys(all_warnings))
            
            # Truncate response to manage storage
            # Responses can be very long, keep first 1000 characters
            response_preview = response[:1000] if response else ""
            if response and len(response) > 1000:
                response_preview += "... (truncated)"
            
            # Create database log entry with all trace data
            # AgentExecutionLog model matches the trace data structure
            log_entry = AgentExecutionLog(
                trace_id=self.current_trace["trace_id"],  # Unique trace identifier
                agent_type=self.current_trace["agent_type"],  # Agent type
                user_id=self.current_trace["user_id"],  # User ID
                query=self.current_trace["query"][:500] if self.current_trace["query"] else None,  # Truncate query to 500 chars
                response=response_preview,  # Truncated response (1000 chars)
                warnings=all_warnings if all_warnings else None,  # Merged warnings (None if empty)
                tools_called=self.current_trace["tools_called"] if self.current_trace["tools_called"] else None,  # Tool calls (None if empty)
                tokens_used=self.current_trace["tokens_used"],  # Total tokens consumed
                duration_ms=duration_ms,  # Execution duration in milliseconds
                success=success  # Success/failure status
            )
            
            # Persist to database
            # Add log entry to session and commit transaction
            self.db.add(log_entry)
            self.db.commit()
            
            # Log successful trace completion
            # Includes key metrics for monitoring
            logger.info(
                f"Trace {self.current_trace['trace_id']} completed: "
                f"agent={self.current_trace['agent_type']}, "
                f"duration={duration_ms:.2f}ms, "
                f"tokens={self.current_trace['tokens_used']}, "
                f"success={success}"
            )
            
        except Exception as e:
            # Handle errors during persistence
            # Log error but don't raise (don't block agent execution)
            logger.error(f"Error persisting trace {self.current_trace.get('trace_id', 'unknown')}: {e}", exc_info=True)
            # Rollback database transaction on error
            self.db.rollback()
        finally:
            # Always clear current trace
            # Prevents memory leaks and ensures clean state
            self.current_trace = None
    
    def get_current_trace_id(self) -> Optional[str]:
        """
        Get the current trace ID if a trace is active.
        
        This method returns the trace ID of the currently active trace, or None
        if no trace is active. Useful for logging or debugging purposes.
        
        Returns:
            Optional[str]: Current trace ID if trace is active, None otherwise
            
        Note:
            - Returns None if no trace is active
            - Trace ID can be used for correlation in logs or error messages
        """
        return self.current_trace["trace_id"] if self.current_trace else None

