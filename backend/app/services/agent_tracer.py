"""
Agent Tracer - tracks agent execution for observability and debugging
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.agent_execution_log import AgentExecutionLog
import json
import logging
import uuid

logger = logging.getLogger(__name__)


class AgentTracer:
    """
    Tracks agent execution for observability, debugging, and optimization.
    Logs agent calls, tool usage, token consumption, and performance metrics.
    """
    
    def __init__(self, db: Session):
        self.db = db
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
        
        Args:
            agent_type: Type of agent (coordinator, physical-fitness, nutrition, mental-fitness)
            user_id: User ID making the request
            query: User's query/input
            image_base64: Optional base64-encoded image (for nutrition agent)
        
        Returns:
            trace_id: Unique identifier for this trace
        """
        # Generate unique trace ID
        trace_id = f"{agent_type}_{user_id}_{uuid.uuid4().hex[:8]}_{int(datetime.now().timestamp() * 1000)}"
        
        self.current_trace = {
            "trace_id": trace_id,
            "agent_type": agent_type,
            "user_id": user_id,
            "query": query,
            "image_base64": image_base64 is not None,  # Store boolean, not the actual image
            "start_time": datetime.now(),
            "tools_called": [],
            "tokens_used": 0,
            "steps": [],
            "warnings": []
        }
        
        logger.debug(f"Started trace {trace_id} for agent {agent_type}, user {user_id}")
        return trace_id
    
    def log_tool_call(self, tool_name: str, tool_input: Dict, tool_output: str):
        """
        Log a tool call during agent execution.
        
        Args:
            tool_name: Name of the tool called
            tool_input: Input parameters passed to the tool
            tool_output: Output from the tool (truncated to 500 chars)
        """
        if not self.current_trace:
            logger.warning("log_tool_call called but no active trace")
            return
        
        # Truncate long outputs
        output_preview = tool_output[:500] if tool_output else ""
        if tool_output and len(tool_output) > 500:
            output_preview += "... (truncated)"
        
        self.current_trace["tools_called"].append({
            "name": tool_name,
            "input": tool_input,
            "output": output_preview,
            "timestamp": datetime.now().isoformat()
        })
        
        logger.debug(f"Logged tool call: {tool_name}")
    
    def log_step(self, step: str):
        """
        Log a step in the agent execution process.
        
        Args:
            step: Description of the step
        """
        if not self.current_trace:
            logger.warning("log_step called but no active trace")
            return
        
        self.current_trace["steps"].append({
            "step": step,
            "timestamp": datetime.now().isoformat()
        })
    
    def log_tokens(self, tokens: int):
        """
        Log token usage.
        
        Args:
            tokens: Number of tokens used
        """
        if not self.current_trace:
            logger.warning("log_tokens called but no active trace")
            return
        
        self.current_trace["tokens_used"] += tokens
    
    def log_warning(self, warning: str):
        """
        Log a warning during agent execution.
        
        Args:
            warning: Warning message
        """
        if not self.current_trace:
            logger.warning("log_warning called but no active trace")
            return
        
        if warning not in self.current_trace["warnings"]:
            self.current_trace["warnings"].append(warning)
    
    def end_trace(
        self, 
        response: str, 
        warnings: Optional[List[str]] = None, 
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        End the current trace and persist it to the database.
        
        Args:
            response: Agent's response (truncated to 1000 chars)
            warnings: List of warning messages
            success: Whether execution succeeded
            error: Error message if execution failed
        """
        if not self.current_trace:
            logger.warning("end_trace called but no active trace")
            return
        
        try:
            end_time = datetime.now()
            duration_ms = (end_time - self.current_trace["start_time"]).total_seconds() * 1000
            
            # Merge warnings
            all_warnings = list(self.current_trace["warnings"])
            if warnings:
                all_warnings.extend(warnings)
            # Remove duplicates while preserving order
            all_warnings = list(dict.fromkeys(all_warnings))
            
            # Truncate response
            response_preview = response[:1000] if response else ""
            if response and len(response) > 1000:
                response_preview += "... (truncated)"
            
            # Create log entry
            log_entry = AgentExecutionLog(
                trace_id=self.current_trace["trace_id"],
                agent_type=self.current_trace["agent_type"],
                user_id=self.current_trace["user_id"],
                query=self.current_trace["query"][:500] if self.current_trace["query"] else None,  # Truncate query too
                response=response_preview,
                warnings=all_warnings if all_warnings else None,
                tools_called=self.current_trace["tools_called"] if self.current_trace["tools_called"] else None,
                tokens_used=self.current_trace["tokens_used"],
                duration_ms=duration_ms,
                success=success
            )
            
            self.db.add(log_entry)
            self.db.commit()
            
            logger.info(
                f"Trace {self.current_trace['trace_id']} completed: "
                f"agent={self.current_trace['agent_type']}, "
                f"duration={duration_ms:.2f}ms, "
                f"tokens={self.current_trace['tokens_used']}, "
                f"success={success}"
            )
            
        except Exception as e:
            logger.error(f"Error persisting trace {self.current_trace.get('trace_id', 'unknown')}: {e}", exc_info=True)
            self.db.rollback()
        finally:
            # Clear current trace
            self.current_trace = None
    
    def get_current_trace_id(self) -> Optional[str]:
        """Get the current trace ID if a trace is active"""
        return self.current_trace["trace_id"] if self.current_trace else None

