"""
Reasoning patterns for agents to provide structured, safe, and thoughtful responses.

This module provides abstract and concrete reasoning pattern classes that implement
a structured three-phase approach: pre-check → reason → post-validate. These patterns
help agents provide safer, more thoughtful responses by incorporating safety checks,
context enhancement, and response validation.

Key Concepts:
- Reasoning Patterns: Abstract patterns for structured agent reasoning
- Pre-check Phase: Analyze query and context for potential issues before reasoning
- Reasoning Phase: Enhance query with context and safety information for LLM
- Post-validation Phase: Validate generated response for safety and correctness

Pattern Types:
- SafetyReasoningPattern: General safety checks (medical history, warnings)
- QueryAnalysisReasoningPattern: Query intent analysis and validation
- ExerciseSafetyReasoningPattern: Specialized exercise conflict detection
- CompositeReasoningPattern: Combines multiple patterns for complex scenarios

Usage:
    Agents use reasoning patterns to:
    1. Pre-check queries for safety concerns (medical conflicts, warnings)
    2. Enhance queries with safety context before LLM reasoning
    3. Post-validate responses for safety violations and correctness

Example Flow:
    1. Agent receives user query
    2. Pattern.pre_check() analyzes query and context
    3. Pattern.reason() enhances query with safety context
    4. LLM generates response using enhanced query
    5. Pattern.post_validate() validates response for safety
    6. Agent returns response with warnings if validation fails
"""

from typing import Dict, Any, Optional, List, Callable, Awaitable
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class ReasoningPattern(ABC):
    """
    Abstract base class for reasoning patterns.
    
    Provides a structured three-phase approach for agent reasoning:
    1. Pre-check: Analyze query and context for potential issues
    2. Reason: Enhance query with context and safety information
    3. Post-validate: Validate generated response for safety and correctness
    
    This pattern ensures agents provide safer, more thoughtful responses by
    incorporating safety checks, context enhancement, and response validation
    at each stage of the reasoning process.
    
    Subclasses should implement:
        - pre_check(): Analyze query and context for potential issues
        - reason(): Enhance query with context and safety information
        - post_validate(): Validate response for safety and correctness
        
    Usage:
        Pattern is used by agents to structure their reasoning process:
        1. Call pre_check() to analyze query and context
        2. Call reason() to enhance query with safety context
        3. Pass enhanced query to LLM for response generation
        4. Call post_validate() to validate response
        5. Return response with warnings if validation fails
    """
    
    @abstractmethod
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-check query for potential issues before reasoning.
        
        This method analyzes the user query and agent context to identify
        potential safety concerns, conflicts, or issues that should be
        considered during reasoning. Results are used to enhance the query
        in the reason() phase.
        
        Args:
            query: User's query requesting guidance or recommendations
            context: Agent context dictionary containing:
                - medical_history: User's medical history (conditions, medications, limitations)
                - preferences: User preferences (goals, activity level, etc.)
                - Other agent-specific context
        
        Returns:
            Dict[str, Any]: Pre-check results dictionary:
                {
                    "has_safety_concerns": bool,  # True if safety concerns detected
                    "warnings": List[str],  # List of warning messages
                    "conflicts": List[Dict],  # List of conflict information
                    # Pattern-specific additional fields
                }
                
        Note:
            - Should be fast and lightweight (no LLM calls)
            - Results are used to enhance query in reason() phase
            - Can include custom safety check functions
        """
        pass
    
    @abstractmethod
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Main reasoning step with pre-check context.
        
        This method enhances the user query with safety context and reasoning
        instructions based on pre-check results. The enhanced query is then
        passed to the LLM for response generation.
        
        Args:
            query: Original user query
            context: Agent context dictionary
            pre_check_results: Results from pre_check() phase
                            Contains safety concerns, warnings, conflicts
        
        Returns:
            str: Enhanced query with safety context and reasoning instructions
                 This enhanced query is passed to LLM for response generation
                 
        Enhancement Strategy:
            - If no safety concerns: Return original query unchanged
            - If safety concerns: Append safety context and reasoning instructions
            - Safety context includes warnings, conflicts, medical history
            - Reasoning instructions guide LLM to consider safety factors
            
        Note:
            - Enhancement is appended to original query
            - LLM receives enhanced query with safety context
            - Pattern-specific enhancement logic (e.g., exercise conflicts)
        """
        pass
    
    @abstractmethod
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-validate response for safety and correctness.
        
        This method validates the agent's generated response for safety
        violations, correctness, and appropriateness. Used to catch issues
        that may have been missed during reasoning.
        
        Args:
            response: Agent's generated response (from LLM)
            query: Original user query
            context: Agent context dictionary
        
        Returns:
            Dict[str, Any]: Validation results dictionary:
                {
                    "is_safe": bool,  # True if response is safe
                    "warnings": List[str] or None,  # List of warning messages
                    "validation_passed": bool  # True if validation passed
                }
                
        Validation Strategy:
            - Check for safety violations (unsafe recommendations)
            - Check for dismissive language regarding medical concerns
            - Check for appropriateness (response matches query type)
            - Pattern-specific validation logic
            
        Note:
            - Warnings are returned to user if validation fails
            - Response may be blocked if critical safety violations detected
            - Pattern-specific validation (e.g., exercise conflicts in response)
        """
        pass


class SafetyReasoningPattern(ReasoningPattern):
    """
    Reasoning pattern focused on general safety checks.
    
    This pattern provides general safety checking capabilities for agents that need
    to consider medical/health safety before responding. It checks for medical history,
    uses custom safety check functions, and validates responses for dismissive language.
    
    Key Features:
        - Medical history checking: Flags queries when user has medical conditions
        - Custom safety functions: Supports pluggable safety check functions
        - Response validation: Checks for dismissive language regarding medical concerns
        
    Usage:
        Used by agents that need general safety checks (not exercise-specific).
        Can be combined with other patterns using CompositeReasoningPattern.
        
    Safety Check Flow:
        1. Pre-check: Check medical history and custom safety function
        2. Reason: Enhance query with safety context if concerns detected
        3. Post-validate: Check response for dismissive language
        
    Attributes:
        safety_check_function: Optional custom function for safety checks
                             Accepts (query: str, context: Dict) -> Dict
                             Returns dict with safety info (has_safety_concerns, warnings, conflicts)
    """
    
    def __init__(self, safety_check_function: Optional[Callable] = None):
        """
        Initialize safety reasoning pattern.
        
        Args:
            safety_check_function: Optional function to check for safety concerns
                Should accept (query: str, context: Dict) and return Dict with safety info:
                {
                    "has_safety_concerns": bool,
                    "warnings": List[str],
                    "conflicts": List[Dict]
                }
                Can be sync or async (will be awaited if async)
                
        Note:
            - Custom safety function is called first in pre_check()
            - Falls back to basic medical history check if no custom function
            - Custom function allows pattern-specific safety logic
        """
        self.safety_check_function = safety_check_function  # Custom safety check function (optional)
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-check query for safety concerns.
        
        This method checks for safety concerns by:
        1. Calling custom safety check function (if provided)
        2. Checking for medical history in context
        3. Flagging queries when user has medical conditions
        
        Args:
            query: User's query requesting guidance
            context: Agent context dictionary (should include medical_history):
                - medical_history: Dict with conditions, medications, limitations
                - preferences: User preferences (optional)
        
        Returns:
            Dict[str, Any]: Safety check results:
                {
                    "has_safety_concerns": bool,  # True if safety concerns detected
                    "warnings": List[str],  # List of warning messages from custom function
                    "conflicts": List[Dict],  # List of conflict information from custom function
                    "medical_history_present": bool  # True if medical history exists
                }
                
        Safety Check Strategy:
            1. Custom function check: Call safety_check_function if provided
            2. Medical history check: Flag if user has medical conditions
            3. Combine results: Merge custom function results with basic checks
            
        Note:
            - Custom function takes precedence if provided
            - Basic check flags any medical conditions for safety review
            - Results are used to enhance query in reason() phase
        """
        has_safety_concerns = False  # Flag indicating if safety concerns detected
        warnings = []  # List of warning messages
        conflicts = []  # List of conflict information
        
        # If custom safety check function provided, use it
        # Custom function allows pattern-specific safety logic
        if self.safety_check_function:
            try:
                check_result = self.safety_check_function(query, context)
                # Handle both sync and async functions
                # Check if result is awaitable (async function)
                if hasattr(check_result, '__await__'):
                    check_result = await check_result
                
                # Extract safety information from custom function result
                if isinstance(check_result, dict):
                    has_safety_concerns = check_result.get("has_safety_concerns", False)
                    warnings = check_result.get("warnings", [])
                    conflicts = check_result.get("conflicts", [])
            except Exception as e:
                # Log exception but continue with basic checks
                logger.warning(f"Safety check function raised exception: {e}")
        
        # Basic safety check: look for medical history in context
        # If user has medical conditions, flag for safety review
        medical_history = context.get("medical_history")
        if medical_history:
            conditions = medical_history.get("conditions", "")
            if conditions and conditions.strip():
                # If user has medical conditions, flag for safety review
                # Ensures medical history is considered even without custom function
                has_safety_concerns = True
        
        return {
            "has_safety_concerns": has_safety_concerns,  # True if safety concerns detected
            "warnings": warnings,  # Warning messages from custom function
            "conflicts": conflicts,  # Conflict information from custom function
            "medical_history_present": medical_history is not None  # Medical history availability flag
        }
    
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Enhance query with safety context for reasoning.
        
        This method enhances the user query with safety context and reasoning
        instructions based on pre-check results. The enhanced query guides
        the LLM to consider safety factors when generating responses.
        
        Args:
            query: Original user query
            context: Agent context dictionary
            pre_check_results: Results from pre_check() phase
                            Contains has_safety_concerns, warnings, conflicts
        
        Returns:
            str: Enhanced query with safety context appended
                 - Original query unchanged if no safety concerns
                 - Query + safety context if concerns detected
                 
        Enhancement Strategy:
            - If no safety concerns: Return original query unchanged
            - If safety concerns: Append safety context section
            - Safety context includes warnings, conflicts, medical history
            - Reasoning instructions guide LLM to prioritize safety
            
        Safety Context Structure:
            [SAFETY CONSIDERATIONS - Review before responding:]
            - Warnings: List of warning messages
            - Conflicts: List of conflict information (if any)
            - Medical Conditions: User's medical conditions
            - Limitations: User's physical limitations
            [Your Task: Consider safety factors, explain conflicts, suggest alternatives]
        """
        # If no safety concerns, return original query unchanged
        # No enhancement needed if no safety issues detected
        if not pre_check_results.get("has_safety_concerns"):
            return query
        
        # Build safety context section
        # This context is appended to query to guide LLM reasoning
        safety_context = "\n\n[SAFETY CONSIDERATIONS - Review before responding:]\n"
        
        # Extract warnings and conflicts from pre-check results
        warnings = pre_check_results.get("warnings", [])
        conflicts = pre_check_results.get("conflicts", [])
        
        # Add warnings section if warnings exist
        if warnings:
            safety_context += "Warnings:\n"
            for warning in warnings:
                safety_context += f"- {warning}\n"
        
        # Add conflicts section if conflicts exist
        # Conflicts can be dicts (structured) or strings (simple)
        if conflicts:
            safety_context += "\nConflicts:\n"
            for conflict in conflicts:
                if isinstance(conflict, dict):
                    # Structured conflict with exercise, message, severity
                    exercise = conflict.get("exercise", "Unknown")
                    message = conflict.get("message", "")
                    severity = conflict.get("severity", "warning")
                    safety_context += f"- {exercise}: {message} (Severity: {severity.upper()})\n"
                else:
                    # Simple conflict string
                    safety_context += f"- {conflict}\n"
        
        # Add medical history information
        # Medical conditions and limitations are important for safety
        medical_history = context.get("medical_history")
        if medical_history:
            conditions = medical_history.get("conditions", "")
            limitations = medical_history.get("limitations", "")
            if conditions:
                safety_context += f"\nUser's Medical Conditions: {conditions}\n"
            if limitations:
                safety_context += f"User's Limitations: {limitations}\n"
        
        # Add reasoning instructions for LLM
        # Guides LLM to prioritize safety and explain conflicts
        safety_context += "\n[Your Task: Consider these safety factors when responding. Prioritize user safety. If conflicts exist, explain them clearly and suggest safer alternatives.]\n"
        
        # Return enhanced query with safety context appended
        return query + safety_context
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-validate response for safety violations.
        
        This method validates the agent's generated response for dismissive language
        regarding medical concerns. It checks for keywords that may indicate the
        response is dismissing or minimizing medical safety concerns.
        
        Args:
            response: Agent's generated response (from LLM)
            query: Original user query
            context: Agent context dictionary (should include medical_history)
        
        Returns:
            Dict[str, Any]: Validation results:
                {
                    "is_safe": bool,  # True if response is safe (no dismissive language)
                    "warnings": List[str],  # List of warning messages (if unsafe)
                    "validation_passed": bool  # True if validation passed (same as is_safe)
                }
                
        Validation Strategy:
            - Check for dismissive keywords in response
            - Only validate if user has medical conditions
            - Flag responses that dismiss medical concerns
            - Simple keyword-based check (can be enhanced with more sophisticated validation)
            
        Unsafe Keywords:
            - "ignore": Dismissing medical concerns
            - "don't worry about": Minimizing safety concerns
            - "it's fine to": Dismissing medical restrictions
            - "you can still": Encouraging unsafe practices
            
        Note:
            - Only validates if user has medical conditions
            - Simple keyword check (can be enhanced with NLP)
            - Warnings are returned to user if validation fails
        """
        is_safe = True  # Flag indicating if response is safe
        warnings = []  # List of warning messages
        
        # Basic validation: check if response mentions unsafe practices
        # This is a simple check - can be enhanced with more sophisticated validation
        # Keywords that indicate dismissive language regarding medical concerns
        unsafe_keywords = ["ignore", "don't worry about", "it's fine to", "you can still"]
        medical_history = context.get("medical_history")
        
        # Only validate if user has medical conditions
        # No need to check dismissive language if no medical concerns
        if medical_history and medical_history.get("conditions"):
            # If user has medical conditions, check for dismissive language
            # Convert response to lowercase for case-insensitive matching
            response_lower = response.lower()
            for keyword in unsafe_keywords:
                if keyword in response_lower:
                    # Check if it's in context of medical conditions
                    # Flag response as unsafe if dismissive keyword found
                    warnings.append(f"Response may dismiss medical concerns: contains '{keyword}'")
                    is_safe = False
                    break  # Stop checking after first unsafe keyword found
        
        return {
            "is_safe": is_safe,  # True if response is safe (no dismissive language)
            "warnings": warnings,  # Warning messages (if unsafe)
            "validation_passed": is_safe  # True if validation passed
        }


class QueryAnalysisReasoningPattern(ReasoningPattern):
    """
    Reasoning pattern for analyzing and understanding user queries.
    
    This pattern helps agents better understand user intent before responding by
    analyzing query structure, type, urgency, and complexity. It validates that
    responses appropriately address the query type and complexity.
    
    Key Features:
        - Query type classification: Identifies planning, how-to, informational, recommendation queries
        - Urgency detection: Flags urgent queries for priority handling
        - Complexity analysis: Detects complex queries requiring detailed responses
        - Response validation: Ensures responses match query type and complexity
    
    Usage:
        Used by agents that need to understand query intent and validate response
        appropriateness. Can be combined with safety patterns for comprehensive reasoning.
        
    Query Analysis Flow:
        1. Pre-check: Analyze query structure, type, urgency, complexity
        2. Reason: Enhance query with analysis context (currently returns original)
        3. Post-validate: Check response appropriateness (length, query type matching)
        
    Query Types:
        - planning: Requests for plans, routines, schedules, programs
        - how_to: Requests for step-by-step guides
        - informational: Questions asking "what", "what is", "what are"
        - recommendation: Requests for recommendations or suggestions
        - general: Other queries
    """
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze query structure and intent.
        
        This method analyzes the user query to determine its type, urgency,
        complexity, and other characteristics that help agents understand intent.
        
        Args:
            query: User's query requesting guidance
            context: Agent context dictionary (optional, not heavily used)
        
        Returns:
            Dict[str, Any]: Query analysis results:
                {
                    "is_question": bool,  # True if query ends with "?"
                    "is_request": bool,  # True if query contains request words
                    "is_informational": bool,  # True if query asks for information
                    "is_urgent": bool,  # True if query indicates urgency
                    "is_complex": bool,  # True if query is complex (long or multi-part)
                    "word_count": int,  # Number of words in query
                    "query_type": str  # Classified query type (planning, how_to, etc.)
                }
                
        Analysis Strategy:
            - Query type: Check for question mark, request words, informational words
            - Urgency: Check for urgent keywords (urgent, asap, immediately, now, emergency)
            - Complexity: Check word count (>20), commas, "and" conjunctions
            - Classification: Categorize into planning, how_to, informational, recommendation, general
        """
        query_lower = query.lower()  # Convert to lowercase for case-insensitive matching
        
        # Analyze query type
        # Check if query is a question (ends with "?")
        is_question = query.strip().endswith("?")
        # Check if query is a request (contains request words)
        is_request = any(word in query_lower for word in ["help", "want", "need", "can you", "please"])
        # Check if query is informational (asks for information)
        is_informational = any(word in query_lower for word in ["what", "how", "why", "when", "where", "tell me", "explain"])
        
        # Check for urgency indicators
        # Urgent queries may need priority handling or faster responses
        is_urgent = any(word in query_lower for word in ["urgent", "asap", "immediately", "now", "emergency"])
        
        # Check for complexity
        # Complex queries may need more detailed responses
        word_count = len(query.split())  # Count words in query
        is_complex = word_count > 20 or "," in query or "and" in query_lower  # Complex if long, has commas, or has "and"
        
        return {
            "is_question": is_question,  # True if query is a question
            "is_request": is_request,  # True if query is a request
            "is_informational": is_informational,  # True if query asks for information
            "is_urgent": is_urgent,  # True if query indicates urgency
            "is_complex": is_complex,  # True if query is complex
            "word_count": word_count,  # Number of words in query
            "query_type": self._classify_query_type(query_lower)  # Classified query type
        }
    
    def _classify_query_type(self, query_lower: str) -> str:
        """
        Classify query into a specific type based on keywords.
        
        Args:
            query_lower: User query in lowercase
            
        Returns:
            str: Query type classification:
                - "planning": Requests for plans, routines, schedules, programs
                - "how_to": Requests for step-by-step guides
                - "informational": Questions asking "what", "what is", "what are"
                - "recommendation": Requests for recommendations or suggestions
                - "general": Other queries
                
        Classification Strategy:
            - Check for planning keywords (plan, routine, schedule, program)
            - Check for how-to keywords (how to, how do, steps, guide)
            - Check for informational keywords (what, what is, what are)
            - Check for recommendation keywords (recommend, suggest, should i)
            - Default to "general" if no match
        """
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
        
        Currently returns the original query unchanged. This method can be enhanced
        to add context based on query analysis (e.g., adding instructions for
        planning queries, how-to queries, etc.).
        
        Args:
            query: Original user query
            context: Agent context dictionary
            pre_check_results: Results from pre_check() phase
                            Contains query type, urgency, complexity
        
        Returns:
            str: Enhanced query (currently returns original query unchanged)
                 
        Future Enhancement:
            - Add context for planning queries (request structured plan)
            - Add context for how-to queries (request step-by-step guide)
            - Add context for urgent queries (prioritize response)
            - Add context for complex queries (request detailed response)
        """
        # For now, return original query
        # This can be enhanced to add context based on analysis
        # Future: Add query-type-specific instructions to guide LLM
        return query
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that response addresses the query appropriately.
        
        This method validates that the agent's response appropriately addresses
        the query type and complexity. It checks for:
        - Response length for complex queries
        - Query type matching (e.g., planning queries should mention planning keywords)
        
        Args:
            response: Agent's generated response (from LLM)
            query: Original user query
            context: Agent context dictionary
        
        Returns:
            Dict[str, Any]: Validation results:
                {
                    "is_appropriate": bool,  # True if response is appropriate
                    "warnings": List[str],  # List of warning messages (if inappropriate)
                    "validation_passed": bool  # True if validation passed (same as is_appropriate)
                }
                
        Validation Strategy:
            - Complex queries: Check if response is long enough (>20 words)
            - Planning queries: Check if response mentions planning keywords
            - Other query types: Can be enhanced with type-specific checks
            
        Note:
            - Re-runs pre_check() to get query analysis
            - Validates response length and query type matching
            - Warnings are returned if validation fails
        """
        is_appropriate = True  # Flag indicating if response is appropriate
        warnings = []  # List of warning messages
        
        # Check if response is too short for complex queries
        # Complex queries should receive detailed responses
        pre_check = await self.pre_check(query, context)
        if pre_check.get("is_complex") and len(response.split()) < 20:
            warnings.append("Response may be too brief for a complex query")
            is_appropriate = False
        
        # Check if response addresses the query type
        # Planning queries should mention planning-related keywords
        query_type = pre_check.get("query_type")
        response_lower = response.lower()
        
        if query_type == "planning" and not any(word in response_lower for word in ["plan", "schedule", "routine", "week", "day"]):
            warnings.append("Response may not address planning request")
            is_appropriate = False
        
        return {
            "is_appropriate": is_appropriate,  # True if response is appropriate
            "warnings": warnings,  # Warning messages (if inappropriate)
            "validation_passed": is_appropriate  # True if validation passed
        }


class ExerciseSafetyReasoningPattern(ReasoningPattern):
    """
    Specialized reasoning pattern for exercise safety checks.
    
    This pattern is specifically designed for PhysicalFitnessAgent to check exercise
    conflicts with medical history. It extracts exercises from queries and responses,
    checks them against medical history, and provides detailed conflict information
    for LLM reasoning.
    
    Key Features:
        - Exercise extraction: Extracts potential exercises from queries and responses
        - Conflict detection: Checks exercises against medical history for conflicts
        - Severity levels: Distinguishes between "block" (critical) and "warning" (moderate) conflicts
        - Detailed context: Provides reasoning context (conditions, medical notes, limitations)
        - Response validation: Validates responses for exercise conflicts
        
    Usage:
        Used by PhysicalFitnessAgent to ensure exercise recommendations are safe
        for users with medical conditions. Prevents recommending exercises that
        conflict with medical history.
        
    Safety Check Flow:
        1. Pre-check: Extract exercises from query, check for conflicts
        2. Reason: Enhance query with conflict context and reasoning instructions
        3. Post-validate: Extract exercises from response, check for conflicts, return warnings
        
    Attributes:
        extract_exercises_fn: Function to extract exercises from text
                             Accepts (text: str) -> List[str]
        check_safety_fn: Function to check exercise safety
                        Accepts (exercise: str) -> Dict with conflict info
    """
    
    def __init__(self, extract_exercises_fn: Callable, check_safety_fn: Callable):
        """
        Initialize exercise safety reasoning pattern.
        
        Args:
            extract_exercises_fn: Function to extract potential exercises from query/responses
                Should accept (text: str) and return List[str] of exercise names
                Used in both pre_check() (query) and post_validate() (response)
            check_safety_fn: Function to check exercise safety against medical history
                Should accept (exercise: str) and return Dict with conflict info:
                {
                    "has_conflict": bool,
                    "severity": str,  # "block" or "warning"
                    "message": str,
                    "reasoning_context": Dict  # Optional detailed context
                }
                
        Note:
            - Both functions are injected for flexibility and testability
            - extract_exercises_fn is used to find exercises in text
            - check_safety_fn is used to check exercises against medical history
        """
        self.extract_exercises_fn = extract_exercises_fn  # Function to extract exercises from text
        self.check_safety_fn = check_safety_fn  # Function to check exercise safety
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-check query for exercise safety concerns.
        
        This method extracts potential exercises from the user query and checks
        them against medical history for conflicts. Results are used to enhance
        the query with conflict context in the reason() phase.
        
        Args:
            query: User's query requesting exercise recommendations
            context: Agent context dictionary (should include medical_history)
        
        Returns:
            Dict[str, Any]: Exercise conflict results:
                {
                    "has_safety_concerns": bool,  # True if conflicts detected
                    "conflicts": List[Dict],  # List of conflict information:
                        [{
                            "exercise": str,  # Exercise name
                            "conflict_info": Dict  # Conflict details (severity, message, etc.)
                        }]
                    "potential_exercises": List[str]  # List of extracted exercises
                }
                
        Pre-check Strategy:
            1. Extract exercises: Use extract_exercises_fn to find exercises in query
            2. Check conflicts: Use check_safety_fn to check each exercise
            3. Collect conflicts: Store exercises with conflicts for enhancement
            
        Note:
            - Extracts exercises from query before LLM reasoning
            - Checks exercises against medical history
            - Results are used to enhance query in reason() phase
        """
        # Extract potential exercises from query
        # Uses injected function to find exercise names in query text
        potential_exercises = self.extract_exercises_fn(query)
        pre_conflicts = []  # List of exercises with conflicts
        
        # Check each extracted exercise for conflicts
        if potential_exercises:
            for exercise in potential_exercises:
                # Check exercise safety against medical history
                conflict_check = self.check_safety_fn(exercise)
                if conflict_check.get("has_conflict"):
                    # Store exercise with conflict information
                    pre_conflicts.append({
                        "exercise": exercise,  # Exercise name
                        "conflict_info": conflict_check  # Conflict details (severity, message, etc.)
                    })
        
        return {
            "has_safety_concerns": len(pre_conflicts) > 0,  # True if conflicts detected
            "conflicts": pre_conflicts,  # List of exercises with conflicts
            "potential_exercises": potential_exercises  # All extracted exercises (for reference)
        }
    
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Enhance query with exercise conflict context.
        
        This method enhances the user query with detailed conflict information
        and reasoning instructions. The enhanced query guides the LLM to consider
        exercise conflicts, severity levels, and medical context when generating
        exercise recommendations.
        
        Args:
            query: Original user query
            context: Agent context dictionary
            pre_check_results: Results from pre_check() phase
                            Contains conflicts, potential_exercises
        
        Returns:
            str: Enhanced query with conflict context appended
                 - Original query unchanged if no conflicts
                 - Query + conflict context if conflicts detected
                 
        Enhancement Strategy:
            - If no conflicts: Return original query unchanged
            - If conflicts: Append detailed conflict context
            - Conflict context includes exercise, severity, message, reasoning context
            - Reasoning instructions guide LLM to consider conflicts and alternatives
            
        Conflict Context Structure:
            [Medical Conflict Analysis - Use this information to reason about safety:]
            - Exercise: Exercise name
            - Conflict: Conflict message
            - Severity: BLOCK or WARNING
            - Conditions: Conflicting medical conditions (if available)
            - Medical Notes: Additional medical notes (if available)
            - Limitations: Physical limitations (if available)
            [Your Task: Reason about conflicts, consider modifications, doctor's approval, alternatives]
        """
        pre_conflicts = pre_check_results.get("conflicts", [])
        
        # If no conflicts, return original query unchanged
        # No enhancement needed if no exercise conflicts detected
        if not pre_conflicts:
            return query
        
        # Build conflict context section
        # This context is appended to query to guide LLM reasoning
        conflict_context = "\n\n[Medical Conflict Analysis - Use this information to reason about safety:]\n"
        for conflict in pre_conflicts:
            conflict_info = conflict["conflict_info"]  # Conflict details from check_safety_fn
            exercise = conflict["exercise"]  # Exercise name
            severity = conflict_info.get("severity", "warning")  # Severity level (block or warning)
            message = conflict_info.get("message", "")  # Conflict message
            reasoning_context = conflict_info.get("reasoning_context", {})  # Detailed context (optional)
            
            # Add exercise conflict information
            conflict_context += f"\n- Exercise: {exercise}\n"
            conflict_context += f"  Conflict: {message}\n"
            conflict_context += f"  Severity: {severity.upper()}\n"
            
            # Add detailed reasoning context if available
            # Provides additional medical information for LLM reasoning
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
        
        # Add reasoning instructions for LLM
        # Guides LLM to consider conflicts, modifications, doctor's approval, alternatives
        conflict_context += "\n[Your Task: Reason about these conflicts. Consider: condition severity, modifications possible, doctor's approval, safer alternatives. Make an informed decision and explain your reasoning.]\n"
        
        # Return enhanced query with conflict context appended
        return query + conflict_context
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-validate response for exercise conflicts.
        
        This method validates the agent's generated response by extracting exercises
        from the response and checking them against medical history for conflicts.
        It returns warnings with severity indicators (BLOCKED or Warning) for the frontend.
        
        Args:
            response: Agent's generated response (from LLM)
            query: Original user query
            context: Agent context dictionary
        
        Returns:
            Dict[str, Any]: Validation results:
                {
                    "is_safe": bool,  # True if no block-level conflicts (only warning-level)
                    "warnings": List[str] or None,  # List of warnings (blocks first, then warnings)
                    "validation_passed": bool  # True if no block-level conflicts
                }
                
        Validation Strategy:
            1. Extract exercises: Use extract_exercises_fn to find exercises in response
            2. Check conflicts: Use check_safety_fn to check each exercise
            3. Format warnings: Ensure warnings have explicit severity indicators
            4. Sort warnings: Block-level warnings first (higher severity), then warning-level
            
        Warning Format:
            - Block-level: "BLOCKED: [message]" (critical conflicts)
            - Warning-level: "Warning: [message]" (moderate conflicts)
            
        Note:
            - Only block-level conflicts make response unsafe
            - Warning-level conflicts are still flagged but don't block response
            - Warnings are sorted by severity (blocks first)
            - Duplicate warnings are filtered (checked_exercises set)
        """
        # Extract exercises from response and check for conflicts
        # This uses the same extraction logic but on the response
        # Validates that LLM didn't recommend conflicting exercises
        response_exercises = self.extract_exercises_fn(response)
        warnings = []  # Final list of warnings (blocks first, then warnings)
        checked_exercises = set()  # Track checked exercises to avoid duplicates
        
        block_warnings = []  # Block-level warnings (critical conflicts)
        warning_warnings = []  # Warning-level warnings (moderate conflicts)
        
        # Check each exercise in response for conflicts
        for exercise in response_exercises:
            if exercise not in checked_exercises:
                checked_exercises.add(exercise)  # Track checked exercises
                # Check exercise safety against medical history
                conflict_check = self.check_safety_fn(exercise)
                if conflict_check.get("has_conflict"):
                    warning_msg = conflict_check.get("message")
                    severity = conflict_check.get("severity", "warning")
                    
                    if warning_msg:
                        # Ensure message has explicit severity indicator for frontend
                        # Frontend needs clear indicators to display warnings appropriately
                        if severity == "block":
                            # Block-level conflict (critical)
                            # Format: "BLOCKED: [message]"
                            if not warning_msg.upper().startswith("BLOCKED"):
                                warning_msg = f"BLOCKED: {warning_msg.replace('MEDICAL CONCERN:', '').replace('BLOCKED:', '').strip()}"
                            if warning_msg not in block_warnings:
                                block_warnings.append(warning_msg)
                        else:
                            # Warning-level conflict (moderate)
                            # Format: "Warning: [message]"
                            if not warning_msg.startswith("Warning:"):
                                warning_msg = f"Warning: {warning_msg.replace('MEDICAL CONSIDERATION:', '').replace('Warning:', '').strip()}"
                            if warning_msg not in warning_warnings:
                                warning_warnings.append(warning_msg)
        
        # Return warnings with blocks first (higher severity)
        # Block-level warnings are more critical and shown first
        warnings = block_warnings + warning_warnings
        
        return {
            "is_safe": len(block_warnings) == 0,  # Only unsafe if there are block-level warnings
            "warnings": warnings if warnings else None,  # Warnings (blocks first, then warnings)
            "validation_passed": len(block_warnings) == 0  # True if no block-level conflicts
        }


class CompositeReasoningPattern(ReasoningPattern):
    """
    Composite pattern that combines multiple reasoning patterns.
    
    This pattern allows combining multiple reasoning patterns to create more
    comprehensive reasoning flows. It executes all patterns in sequence, with
    each pattern's output feeding into the next pattern's input.
    
    Key Features:
        - Pattern composition: Combines multiple patterns for complex scenarios
        - Sequential execution: Patterns execute in order (pre_check → reason → post_validate)
        - Result aggregation: Combines results from all patterns
        - Query enhancement: Each pattern enhances query sequentially
        
    Usage:
        Used when agents need multiple reasoning patterns (e.g., safety + query analysis).
        Example: Combine ExerciseSafetyReasoningPattern with QueryAnalysisReasoningPattern
        for comprehensive exercise recommendation reasoning.
        
    Execution Flow:
        1. Pre-check: Run pre_check() for all patterns, store results by index
        2. Reason: Run reason() for all patterns sequentially, each enhancing the query
        3. Post-validate: Run post_validate() for all patterns, aggregate warnings
        
    Result Structure:
        - Pre-check: Results stored as {"pattern_0": {...}, "pattern_1": {...}, ...}
        - Reason: Query enhanced sequentially by each pattern
        - Post-validate: Warnings aggregated from all patterns
        
    Attributes:
        patterns: List of ReasoningPattern instances to execute
    """
    
    def __init__(self, patterns: List[ReasoningPattern]):
        """
        Initialize composite pattern.
        
        Args:
            patterns: List of reasoning patterns to execute in sequence
                     Patterns execute in order: pre_check → reason → post_validate
                     Each pattern's output feeds into the next pattern's input
                     
        Note:
            - Patterns execute in the order provided
            - Query enhancement is sequential (each pattern enhances previous result)
            - Validation results are aggregated from all patterns
        """
        self.patterns = patterns  # List of reasoning patterns to execute
    
    async def pre_check(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run pre_check for all patterns.
        
        Executes pre_check() for each pattern in sequence and stores results
        by pattern index. Results are used in reason() phase.
        
        Args:
            query: User's query
            context: Agent context dictionary
        
        Returns:
            Dict[str, Any]: Combined pre-check results:
                {
                    "pattern_0": Dict,  # Results from first pattern
                    "pattern_1": Dict,  # Results from second pattern
                    ...
                }
                
        Note:
            - Results stored by pattern index for reason() phase
            - Each pattern's pre_check() runs independently
            - Results are combined into single dictionary
        """
        results = {}  # Dictionary to store results by pattern index
        for i, pattern in enumerate(self.patterns):
            # Run pre_check for each pattern
            pattern_results = await pattern.pre_check(query, context)
            # Store results by pattern index (used in reason() phase)
            results[f"pattern_{i}"] = pattern_results
        return results
    
    async def reason(self, query: str, context: Dict[str, Any], pre_check_results: Dict[str, Any]) -> str:
        """
        Run reason for all patterns in sequence.
        
        Executes reason() for each pattern sequentially, with each pattern
        enhancing the query from the previous pattern. Final enhanced query
        is passed to LLM.
        
        Args:
            query: Original user query
            context: Agent context dictionary
            pre_check_results: Combined pre-check results from all patterns
                             Contains results keyed by pattern index
        
        Returns:
            str: Enhanced query after all patterns have enhanced it
                 Query is enhanced sequentially: pattern_0 → pattern_1 → ...
                 
        Enhancement Strategy:
            - Start with original query
            - Each pattern enhances query sequentially
            - Pattern i uses pre_check results from pattern i
            - Final enhanced query combines enhancements from all patterns
            
        Note:
            - Query enhancement is sequential (each pattern builds on previous)
            - Each pattern receives its own pre_check results
            - Final query includes enhancements from all patterns
        """
        enhanced_query = query  # Start with original query
        for i, pattern in enumerate(self.patterns):
            # Get pre_check results for this pattern
            pattern_pre_check = pre_check_results.get(f"pattern_{i}", {})
            # Enhance query with this pattern (builds on previous enhancements)
            enhanced_query = await pattern.reason(enhanced_query, context, pattern_pre_check)
        return enhanced_query  # Return final enhanced query
    
    async def post_validate(self, response: str, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run post_validate for all patterns.
        
        Executes post_validate() for each pattern and aggregates warnings.
        Response is considered safe only if all patterns pass validation.
        
        Args:
            response: Agent's generated response (from LLM)
            query: Original user query
            context: Agent context dictionary
        
        Returns:
            Dict[str, Any]: Aggregated validation results:
                {
                    "is_safe": bool,  # True if all patterns pass validation
                    "warnings": List[str],  # Combined warnings from all patterns
                    "validation_passed": bool  # True if all patterns pass (same as is_safe)
                }
                
        Validation Strategy:
            - Run post_validate() for each pattern
            - Aggregate warnings from all patterns
            - Response is safe only if all patterns pass validation
            - Warnings include all warnings from all patterns
            
        Note:
            - Validation is strict (all patterns must pass)
            - Warnings are aggregated from all patterns
            - Response is unsafe if any pattern fails validation
        """
        all_warnings = []  # List to aggregate warnings from all patterns
        all_safe = True  # Flag indicating if all patterns pass validation
        
        # Run post_validate for each pattern
        for i, pattern in enumerate(self.patterns):
            validation = await pattern.post_validate(response, query, context)
            # Check if this pattern passed validation
            if not validation.get("validation_passed", True):
                all_safe = False  # Mark as unsafe if any pattern fails
            # Aggregate warnings from this pattern
            warnings = validation.get("warnings", [])
            if warnings:
                all_warnings.extend(warnings)
        
        return {
            "is_safe": all_safe,  # True if all patterns pass validation
            "warnings": all_warnings,  # Combined warnings from all patterns
            "validation_passed": all_safe  # True if all patterns pass (same as is_safe)
        }
