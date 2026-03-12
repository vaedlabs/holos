"""
Agent Execution Log model for observability and performance tracking.

This module defines the AgentExecutionLog model, which stores detailed execution
logs for AI agent interactions. This model is used for observability, debugging,
performance monitoring, and optimization of agent behavior.

Key Features:
- Trace ID for request tracking
- Agent type identification
- Query and response storage
- Tool call tracking
- Token usage tracking
- Performance metrics (duration, success rate)
- Warning tracking
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class AgentExecutionLog(Base):
    """
    Agent Execution Log model storing observability data for AI agent executions.
    
    This model stores detailed logs of every agent execution, including queries,
    responses, tool calls, token usage, and performance metrics. The model has a
    many-to-one relationship with User model, allowing tracking of all agent
    interactions per user.
    
    Attributes:
        id: Primary key, auto-incrementing integer
        trace_id: Unique trace identifier for this execution (unique, indexed)
        agent_type: Type of agent that executed (indexed, required)
        user_id: Foreign key to User model (indexed, required)
        query: User's query/input that triggered the agent (nullable)
        response: Agent's response text (truncated to 1000 chars, nullable)
        warnings: List of warnings associated with the execution (JSON, nullable)
        tools_called: List of tools called during execution with inputs/outputs (JSON, nullable)
        tokens_used: Total tokens consumed during execution (Integer, default: 0)
        duration_ms: Execution duration in milliseconds (Float, nullable)
        success: Whether execution succeeded (Boolean, default: True)
        created_at: Timestamp when execution log was created (indexed)
        
    Relationships:
        user: Many-to-one relationship with User model
        
    Trace ID Format:
        Trace IDs are unique identifiers generated for each agent execution.
        Format: "{agent_type}_{user_id}_{uuid}_{timestamp}"
        Example: "nutrition_123_a1b2c3d4_1704067200000"
        
        This format allows:
        - Quick identification of agent type and user
        - Unique identification across all executions
        - Timestamp-based sorting and filtering
        
    Agent Types:
        The agent_type field identifies which agent executed:
        - "coordinator": Coordinator Agent (routes queries or creates holistic plans)
        - "physical-fitness": Physical Fitness Agent
        - "nutrition": Nutrition Agent
        - "mental-fitness": Mental Fitness Agent
        
    Tools Called Format (JSON):
        The tools_called field stores structured data about tool usage:
        [
            {
                "name": "get_medical_history",
                "input": {"query": ""},
                "output": "No medical history on file.",
                "timestamp": "2024-01-01T12:00:00"
            },
            {
                "name": "create_workout_log",
                "input": {"exercise_type": "calisthenics", "exercises": "...", "duration_minutes": 30},
                "output": "Workout log created successfully. Log ID: 456",
                "timestamp": "2024-01-01T12:00:01"
            }
        ]
        
    Warnings Format (JSON):
        The warnings field stores warnings as JSON array:
        [
            "Exercise may conflict with knee injury",
            "Using fallback model due to API errors",
            "LLM call timed out after 30 seconds"
        ]
        
    Performance Metrics:
        - duration_ms: Total execution time in milliseconds (includes LLM calls, tool execution)
        - tokens_used: Total tokens consumed (input + output tokens)
        - success: Boolean indicating if execution completed successfully
        
        These metrics help identify:
        - Slow queries or performance bottlenecks
        - High token usage patterns
        - Failure rates and error patterns
        
    Note:
        - Multiple execution logs can exist per user (many-to-one relationship)
        - Trace ID is unique across all executions for request tracking
        - Response is truncated to 1000 characters to manage storage
        - Tools called and warnings are stored as JSON for structured querying
        - Indexes on trace_id, agent_type, user_id, and created_at enable fast queries
        - Used by observability tools and debugging interfaces
    """
    __tablename__ = "agent_execution_logs"

    # Primary key - auto-incrementing integer
    # Indexed for fast lookups by ID
    id = Column(Integer, primary_key=True, index=True)
    
    # Trace ID - unique identifier for this execution
    # Format: "{agent_type}_{user_id}_{uuid}_{timestamp}"
    # Unique constraint ensures no duplicate trace IDs
    # Indexed for fast lookups by trace ID
    # Required field - cannot be null
    # Used for request tracking and debugging
    trace_id = Column(String, unique=True, index=True, nullable=False)
    
    # Agent type - identifies which agent executed
    # Values: "coordinator", "physical-fitness", "nutrition", "mental-fitness"
    # Indexed for fast queries filtering by agent type
    # Required field - cannot be null
    # Used for agent-specific analytics and debugging
    agent_type = Column(String, index=True, nullable=False)  # coordinator, physical-fitness, nutrition, mental-fitness
    
    # Foreign key to User model
    # Many-to-one relationship (each user can have multiple execution logs)
    # Indexed for fast queries filtering by user
    # Required field - cannot be null
    # Cascade delete: if user is deleted, execution logs are also deleted
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    
    # Execution details - user's query/input
    # Format: Plain text containing the user's query
    # Used for debugging and understanding what triggered the agent
    # Nullable to allow logs without query (e.g., system-initiated executions)
    # May be truncated if very long
    query = Column(Text, nullable=True)  # User's query/input
    
    # Execution details - agent's response
    # Format: Plain text containing the agent's response
    # Truncated to 1000 characters to manage storage size
    # Used for debugging and response analysis
    # Nullable to allow logs without response (e.g., failed executions)
    response = Column(Text, nullable=True)  # Agent's response (truncated to 1000 chars)
    
    # Warnings - warnings associated with the execution
    # Format: JSON array of warning strings
    # Example: ["Exercise may conflict with knee injury", "Using fallback model"]
    # Used to track issues, limitations, or degraded functionality
    # Nullable to allow executions without warnings
    warnings = Column(JSON, nullable=True)  # List of warnings if any
    
    # Tools and tokens - tools called during execution
    # Format: JSON array of tool call objects
    # Each object contains: name, input, output, timestamp
    # Used for debugging tool usage and understanding agent behavior
    # Nullable to allow executions without tool calls
    tools_called = Column(JSON, nullable=True)  # List of tools called with inputs/outputs
    
    # Tokens used - total tokens consumed during execution
    # Includes both input tokens (prompt, context) and output tokens (response)
    # Used for cost tracking and optimization
    # Defaults to 0 if not tracked
    # Integer type (tokens are whole numbers)
    tokens_used = Column(Integer, default=0)  # Total tokens used
    
    # Performance metrics - execution duration
    # Format: Float representing milliseconds
    # Includes time for LLM calls, tool execution, and processing
    # Used for performance monitoring and identifying slow queries
    # Nullable to allow logs without duration tracking
    duration_ms = Column(Float, nullable=True)  # Execution duration in milliseconds
    
    # Performance metrics - execution success status
    # Boolean indicating if execution completed successfully
    # True: Execution completed without errors
    # False: Execution failed or encountered errors
    # Defaults to True (optimistic)
    # Used for failure rate analysis and error tracking
    success = Column(Boolean, default=True)  # Whether execution succeeded
    
    # Timestamps - execution log creation timestamp
    # Automatically set to current time when log entry is created
    # Timezone-aware DateTime for accurate time tracking
    # Indexed for fast queries filtering by date/time
    # Used for time-based analytics and log retrieval
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationship to User model
    # Many-to-one relationship (each user can have multiple execution logs)
    # Access via: execution_log.user (returns User object)
    # Back-populates with User.agent_execution_logs (returns list of AgentExecutionLog objects)
    user = relationship("User", back_populates="agent_execution_logs")

