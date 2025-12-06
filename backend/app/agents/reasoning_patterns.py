"""
Reasoning patterns for agents to provide structured, safe, and thoughtful responses.
Implements pre-check, reasoning, and post-validation phases.
"""

from typing import Dict, Any, Optional, List, Callable, Awaitable
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class ReasoningPattern(ABC):
    """
    Base class for reasoning patterns.
    Provides structured approach: pre-check → reason → post-validate
    """
    
    @abstractmethod
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-check query for potential issues before reasoning.
        
        Args:
            query: User's query
            context: Agent context (medical history, preferences, etc.)
            
        Returns:
            Dictionary with pre-check results (e.g., {"has_safety_concerns": True, "warnings": [...]})
        """
        pass
    
    @abstractmethod
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Main reasoning step with pre-check context.
        
        Args:
            query: User's query
            context: Agent context
            pre_check_results: Results from pre_check phase
            
        Returns:
            Enhanced query or reasoning context to pass to LLM
        """
        pass
    
    @abstractmethod
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-validate response for safety and correctness.
        
        Args:
            response: Agent's generated response
            query: Original user query
            context: Agent context
            
        Returns:
            Dictionary with validation results (e.g., {"is_safe": True, "warnings": [...]})
        """
        pass


class SafetyReasoningPattern(ReasoningPattern):
    """
    Reasoning pattern focused on safety checks.
    Used by agents that need to check medical/health safety before responding.
    """
    
    def __init__(self, safety_check_function: Optional[Callable] = None):
        """
        Initialize safety reasoning pattern.
        
        Args:
            safety_check_function: Optional function to check for safety concerns
                Should accept (query: str, context: Dict) and return Dict with safety info
        """
        self.safety_check_function = safety_check_function
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-check query for safety concerns.
        
        Args:
            query: User's query
            context: Agent context (should include medical_history)
            
        Returns:
            Dictionary with safety check results
        """
        has_safety_concerns = False
        warnings = []
        conflicts = []
        
        # If custom safety check function provided, use it
        if self.safety_check_function:
            try:
                check_result = self.safety_check_function(query, context)
                # Handle both sync and async functions
                if hasattr(check_result, '__await__'):
                    check_result = await check_result
                
                if isinstance(check_result, dict):
                    has_safety_concerns = check_result.get("has_safety_concerns", False)
                    warnings = check_result.get("warnings", [])
                    conflicts = check_result.get("conflicts", [])
            except Exception as e:
                logger.warning(f"Safety check function raised exception: {e}")
        
        # Basic safety check: look for medical history in context
        medical_history = context.get("medical_history")
        if medical_history:
            conditions = medical_history.get("conditions", "")
            if conditions and conditions.strip():
                # If user has medical conditions, flag for safety review
                has_safety_concerns = True
        
        return {
            "has_safety_concerns": has_safety_concerns,
            "warnings": warnings,
            "conflicts": conflicts,
            "medical_history_present": medical_history is not None
        }
    
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Enhance query with safety context for reasoning.
        
        Args:
            query: Original user query
            context: Agent context
            pre_check_results: Results from pre_check
            
        Returns:
            Enhanced query with safety context
        """
        if not pre_check_results.get("has_safety_concerns"):
            return query
        
        # Build safety context
        safety_context = "\n\n[SAFETY CONSIDERATIONS - Review before responding:]\n"
        
        warnings = pre_check_results.get("warnings", [])
        conflicts = pre_check_results.get("conflicts", [])
        
        if warnings:
            safety_context += "Warnings:\n"
            for warning in warnings:
                safety_context += f"- {warning}\n"
        
        if conflicts:
            safety_context += "\nConflicts:\n"
            for conflict in conflicts:
                if isinstance(conflict, dict):
                    exercise = conflict.get("exercise", "Unknown")
                    message = conflict.get("message", "")
                    severity = conflict.get("severity", "warning")
                    safety_context += f"- {exercise}: {message} (Severity: {severity.upper()})\n"
                else:
                    safety_context += f"- {conflict}\n"
        
        medical_history = context.get("medical_history")
        if medical_history:
            conditions = medical_history.get("conditions", "")
            limitations = medical_history.get("limitations", "")
            if conditions:
                safety_context += f"\nUser's Medical Conditions: {conditions}\n"
            if limitations:
                safety_context += f"User's Limitations: {limitations}\n"
        
        safety_context += "\n[Your Task: Consider these safety factors when responding. Prioritize user safety. If conflicts exist, explain them clearly and suggest safer alternatives.]\n"
        
        return query + safety_context
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-validate response for safety violations.
        
        Args:
            response: Agent's generated response
            query: Original user query
            context: Agent context
            
        Returns:
            Validation results
        """
        is_safe = True
        warnings = []
        
        # Basic validation: check if response mentions unsafe practices
        # This is a simple check - can be enhanced with more sophisticated validation
        unsafe_keywords = ["ignore", "don't worry about", "it's fine to", "you can still"]
        medical_history = context.get("medical_history")
        
        if medical_history and medical_history.get("conditions"):
            # If user has medical conditions, check for dismissive language
            response_lower = response.lower()
            for keyword in unsafe_keywords:
                if keyword in response_lower:
                    # Check if it's in context of medical conditions
                    warnings.append(f"Response may dismiss medical concerns: contains '{keyword}'")
                    is_safe = False
                    break
        
        return {
            "is_safe": is_safe,
            "warnings": warnings,
            "validation_passed": is_safe
        }


class QueryAnalysisReasoningPattern(ReasoningPattern):
    """
    Reasoning pattern for analyzing and understanding user queries.
    Helps agents better understand user intent before responding.
    """
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze query structure and intent.
        
        Args:
            query: User's query
            context: Agent context
            
        Returns:
            Query analysis results
        """
        query_lower = query.lower()
        
        # Analyze query type
        is_question = query.strip().endswith("?")
        is_request = any(word in query_lower for word in ["help", "want", "need", "can you", "please"])
        is_informational = any(word in query_lower for word in ["what", "how", "why", "when", "where", "tell me", "explain"])
        
        # Check for urgency indicators
        is_urgent = any(word in query_lower for word in ["urgent", "asap", "immediately", "now", "emergency"])
        
        # Check for complexity
        word_count = len(query.split())
        is_complex = word_count > 20 or "," in query or "and" in query_lower
        
        return {
            "is_question": is_question,
            "is_request": is_request,
            "is_informational": is_informational,
            "is_urgent": is_urgent,
            "is_complex": is_complex,
            "word_count": word_count,
            "query_type": self._classify_query_type(query_lower)
        }
    
    def _classify_query_type(self, query_lower: str) -> str:
        """Classify query into a type"""
        if any(word in query_lower for word in ["plan", "routine", "schedule", "program"]):
            return "planning"
        elif any(word in query_lower for word in ["how to", "how do", "steps", "guide"]):
            return "how_to"
        elif any(word in query_lower for word in ["what", "what is", "what are"]):
            return "informational"
        elif any(word in query_lower for word in ["recommend", "suggest", "should i"]):
            return "recommendation"
        else:
            return "general"
    
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Enhance query with analysis context if needed.
        
        Args:
            query: Original user query
            context: Agent context
            pre_check_results: Results from pre_check
            
        Returns:
            Enhanced query (or original if no enhancement needed)
        """
        # For now, return original query
        # This can be enhanced to add context based on analysis
        return query
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that response addresses the query appropriately.
        
        Args:
            response: Agent's generated response
            query: Original user query
            context: Agent context
            
        Returns:
            Validation results
        """
        is_appropriate = True
        warnings = []
        
        # Check if response is too short for complex queries
        pre_check = await self.pre_check(query, context)
        if pre_check.get("is_complex") and len(response.split()) < 20:
            warnings.append("Response may be too brief for a complex query")
            is_appropriate = False
        
        # Check if response addresses the query type
        query_type = pre_check.get("query_type")
        response_lower = response.lower()
        
        if query_type == "planning" and not any(word in response_lower for word in ["plan", "schedule", "routine", "week", "day"]):
            warnings.append("Response may not address planning request")
            is_appropriate = False
        
        return {
            "is_appropriate": is_appropriate,
            "warnings": warnings,
            "validation_passed": is_appropriate
        }


class ExerciseSafetyReasoningPattern(ReasoningPattern):
    """
    Specialized reasoning pattern for exercise safety checks.
    Used by PhysicalFitnessAgent to check exercise conflicts with medical history.
    """
    
    def __init__(self, extract_exercises_fn: Callable, check_safety_fn: Callable):
        """
        Initialize exercise safety reasoning pattern.
        
        Args:
            extract_exercises_fn: Function to extract potential exercises from query
                Should accept (query: str) and return List[str]
            check_safety_fn: Function to check exercise safety
                Should accept (exercise: str) and return Dict with conflict info
        """
        self.extract_exercises_fn = extract_exercises_fn
        self.check_safety_fn = check_safety_fn
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-check query for exercise safety concerns.
        
        Args:
            query: User's query
            context: Agent context
            
        Returns:
            Dictionary with exercise conflict results
        """
        # Extract potential exercises from query
        potential_exercises = self.extract_exercises_fn(query)
        pre_conflicts = []
        
        if potential_exercises:
            for exercise in potential_exercises:
                conflict_check = self.check_safety_fn(exercise)
                if conflict_check.get("has_conflict"):
                    pre_conflicts.append({
                        "exercise": exercise,
                        "conflict_info": conflict_check
                    })
        
        return {
            "has_safety_concerns": len(pre_conflicts) > 0,
            "conflicts": pre_conflicts,
            "potential_exercises": potential_exercises
        }
    
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Enhance query with exercise conflict context.
        
        Args:
            query: Original user query
            context: Agent context
            pre_check_results: Results from pre_check
            
        Returns:
            Enhanced query with conflict context
        """
        pre_conflicts = pre_check_results.get("conflicts", [])
        
        if not pre_conflicts:
            return query
        
        # Build conflict context
        conflict_context = "\n\n[Medical Conflict Analysis - Use this information to reason about safety:]\n"
        for conflict in pre_conflicts:
            conflict_info = conflict["conflict_info"]
            exercise = conflict["exercise"]
            severity = conflict_info.get("severity", "warning")
            message = conflict_info.get("message", "")
            reasoning_context = conflict_info.get("reasoning_context", {})
            
            conflict_context += f"\n- Exercise: {exercise}\n"
            conflict_context += f"  Conflict: {message}\n"
            conflict_context += f"  Severity: {severity.upper()}\n"
            
            if reasoning_context:
                conditions = reasoning_context.get("conflicting_conditions", [])
                medical_notes = reasoning_context.get("medical_notes")
                limitations = reasoning_context.get("limitations")
                
                if conditions:
                    conflict_context += f"  Conditions: {', '.join(conditions)}\n"
                if medical_notes:
                    conflict_context += f"  Medical Notes: {medical_notes}\n"
                if limitations:
                    conflict_context += f"  Limitations: {limitations}\n"
            
            conflict_context += "\n"
        
        conflict_context += "\n[Your Task: Reason about these conflicts. Consider: condition severity, modifications possible, doctor's approval, safer alternatives. Make an informed decision and explain your reasoning.]\n"
        
        return query + conflict_context
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-validate response for exercise conflicts.
        
        Args:
            response: Agent's generated response
            query: Original user query
            context: Agent context
            
        Returns:
            Validation results with warnings
        """
        # Extract exercises from response and check for conflicts
        # This uses the same extraction logic but on the response
        response_exercises = self.extract_exercises_fn(response)
        warnings = []
        checked_exercises = set()
        
        block_warnings = []
        warning_warnings = []
        
        for exercise in response_exercises:
            if exercise not in checked_exercises:
                checked_exercises.add(exercise)
                conflict_check = self.check_safety_fn(exercise)
                if conflict_check.get("has_conflict"):
                    warning_msg = conflict_check.get("message")
                    severity = conflict_check.get("severity", "warning")
                    
                    if warning_msg:
                        # Ensure message has explicit severity indicator for frontend
                        if severity == "block":
                            if not warning_msg.upper().startswith("BLOCKED"):
                                warning_msg = f"BLOCKED: {warning_msg.replace('MEDICAL CONCERN:', '').replace('BLOCKED:', '').strip()}"
                            if warning_msg not in block_warnings:
                                block_warnings.append(warning_msg)
                        else:
                            if not warning_msg.startswith("Warning:"):
                                warning_msg = f"Warning: {warning_msg.replace('MEDICAL CONSIDERATION:', '').replace('Warning:', '').strip()}"
                            if warning_msg not in warning_warnings:
                                warning_warnings.append(warning_msg)
        
        # Return warnings with blocks first (higher severity)
        warnings = block_warnings + warning_warnings
        
        return {
            "is_safe": len(block_warnings) == 0,  # Only unsafe if there are block-level warnings
            "warnings": warnings if warnings else None,
            "validation_passed": len(block_warnings) == 0
        }


class CompositeReasoningPattern(ReasoningPattern):
    """
    Composite pattern that combines multiple reasoning patterns.
    Executes all patterns in sequence.
    """
    
    def __init__(self, patterns: List[ReasoningPattern]):
        """
        Initialize composite pattern.
        
        Args:
            patterns: List of reasoning patterns to execute
        """
        self.patterns = patterns
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run pre_check for all patterns"""
        results = {}
        for i, pattern in enumerate(self.patterns):
            pattern_results = await pattern.pre_check(query, context)
            results[f"pattern_{i}"] = pattern_results
        return results
    
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """Run reason for all patterns in sequence"""
        enhanced_query = query
        for i, pattern in enumerate(self.patterns):
            pattern_pre_check = pre_check_results.get(f"pattern_{i}", {})
            enhanced_query = await pattern.reason(enhanced_query, context, pattern_pre_check)
        return enhanced_query
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run post_validate for all patterns"""
        all_warnings = []
        all_safe = True
        
        for i, pattern in enumerate(self.patterns):
            validation = await pattern.post_validate(response, query, context)
            if not validation.get("validation_passed", True):
                all_safe = False
            warnings = validation.get("warnings", [])
            if warnings:
                all_warnings.extend(warnings)
        
        return {
            "is_safe": all_safe,
            "warnings": all_warnings,
            "validation_passed": all_safe
        }
