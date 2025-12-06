"""
Agent Execution Log model - tracks agent executions for observability
"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class AgentExecutionLog(Base):
    __tablename__ = "agent_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String, unique=True, index=True, nullable=False)
    agent_type = Column(String, index=True, nullable=False)  # coordinator, physical-fitness, nutrition, mental-fitness
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    
    # Execution details
    query = Column(Text, nullable=True)  # User's query/input
    response = Column(Text, nullable=True)  # Agent's response (truncated to 1000 chars)
    warnings = Column(JSON, nullable=True)  # List of warnings if any
    
    # Tools and tokens
    tools_called = Column(JSON, nullable=True)  # List of tools called with inputs/outputs
    tokens_used = Column(Integer, default=0)  # Total tokens used
    
    # Performance metrics
    duration_ms = Column(Float, nullable=True)  # Execution duration in milliseconds
    success = Column(Boolean, default=True)  # Whether execution succeeded
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationship
    user = relationship("User", back_populates="agent_execution_logs")

