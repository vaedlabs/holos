"""
Physical Fitness Agent - Specialized agent for workout planning and exercise recommendations.

This module provides the PhysicalFitnessAgent class, which specializes in exercise
recommendations, workout planning, and fitness guidance. It extends BaseAgent with
safety checking capabilities to prevent recommending unsafe exercises.

Key Features:
- Exercise recommendations with safety validation
- Workout plan creation
- Medical history integration for safety checking
- Exercise conflict detection (block vs warning)
- Reasoning patterns for pre-check, reasoning, and post-validation
- Tool interception to prevent logging unsafe exercises
- Motivational personality traits

Safety Features:
- Pre-check: Validates exercises before generating recommendations
- Post-validation: Checks response for exercise conflicts
- Tool interception: Prevents logging exercises with block-level conflicts
- Medical history integration: Checks all exercises against user's conditions

Reasoning Pattern:
- Uses ExerciseSafetyReasoningPattern for comprehensive safety checking
- Pre-check: Identifies potential conflicts before response generation
- Reasoning: Enhances query with conflict context
- Post-validation: Validates final response for conflicts
"""

from typing import Dict, Any, Optional, TYPE_CHECKING
import asyncio
import logging

if TYPE_CHECKING:
    from app.services.agent_tracer import AgentTracer
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.services.medical_service import check_user_exercise_conflicts
from app.agents.reasoning_patterns import ExerciseSafetyReasoningPattern
from app.exceptions.agent_exceptions import (
    ToolExecutionError,
    ToolInputValidationError,
    ToolRetryableError,
    ToolNotFoundError
)

# Logger instance for this module
# Used for logging agent operations, safety checks, and errors
logger = logging.getLogger(__name__)


class PhysicalFitnessAgent(BaseAgent):
    """
    Physical Fitness Agent specialized for exercise recommendations and workout planning.
    
    This agent extends BaseAgent with specialized functionality for physical fitness,
    including exercise recommendations, workout planning, and safety validation.
    
    Key Capabilities:
        - Exercise recommendations with safety checking
        - Workout plan creation (structured plans)
        - Medical history integration (prevents unsafe exercises)
        - Exercise conflict detection (block vs warning severity)
        - Reasoning patterns for comprehensive safety validation
        
    Safety Validation Flow:
        1. Pre-check: Identifies potential exercise conflicts before response generation
        2. Reasoning: Enhances query with conflict context for informed recommendations
        3. Response Generation: Agent generates response with conflict awareness
        4. Post-validation: Validates final response for any missed conflicts
        5. Tool Interception: Prevents logging exercises with block-level conflicts
        
    Personality:
        - Motivational and energetic
        - Active voice (action-oriented language)
        - Encouragement phrases ("You've got this!", "Let's crush this!")
        - Celebrates progress
        - Professional but friendly
        
    Attributes:
        exercise_safety_pattern: ExerciseSafetyReasoningPattern instance for safety checking
        _current_user_query: Current user query (for conflict checking)
        _current_context: Current context (medical history + preferences)
        _has_block_conflict: Flag indicating if block-level conflicts exist
    """
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gpt-4.1",
        shared_context: Optional[Dict[str, Optional[Dict]]] = None,
        tracer: Optional["AgentTracer"] = None
    ):
        """
        Initialize PhysicalFitnessAgent with safety checking capabilities.
        
        Args:
            user_id: User ID for user-specific operations
            db: Database session for querying user data
            model_name: LLM model name (default: "gpt-4.1")
            shared_context: Shared user context from ContextManager (optional)
                          Includes medical history and preferences
            tracer: AgentTracer instance for observability (optional)
                   
        Initialization Steps:
            1. Call parent BaseAgent.__init__() to set up LLM, tools, and prompts
            2. Initialize ExerciseSafetyReasoningPattern for safety checking
            3. Configure reasoning pattern with exercise extraction and safety check functions
            
        Note:
            - Inherits all tools and capabilities from BaseAgent
            - Adds exercise safety checking via reasoning pattern
            - Uses shared context to avoid redundant database queries
        """
        # Initialize parent BaseAgent
        # Sets up LLM, tools, prompts, and context management
        super().__init__(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
        
        # Initialize reasoning pattern for exercise safety
        # Provides pre-check, reasoning, and post-validation capabilities
        # Uses exercise extraction and safety check functions for comprehensive validation
        self.exercise_safety_pattern = ExerciseSafetyReasoningPattern(
            extract_exercises_fn=self._extract_potential_exercises,  # Function to extract exercises from query
            check_safety_fn=self.check_exercise_safety  # Function to check exercise safety
        )
    
    def _get_agent_type(self) -> str:
        """
        Get agent type identifier for caching and identification.
        
        Returns:
            str: Agent type identifier ("physical_fitness")
            
        Note:
            - Used for prompt caching (static and enhanced prompts)
            - Used for identification in logs and traces
            - Overrides BaseAgent default implementation
        """
        return "physical_fitness"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for physical fitness agent.
        
        This method retrieves the system prompt for the physical fitness agent,
        checking cache first, then building if not cached.
        
        Returns:
            str: System prompt for physical fitness agent
            
        Prompt Strategy:
            1. Check cache first (static prompt cache)
            2. If cached, return cached prompt
            3. If not cached, build prompt from fitness_prompt module
            4. Cache the built prompt for future use
            
        Note:
            - Uses prompt caching to reduce token usage
            - Static prompts are cached indefinitely (version-based invalidation)
            - Prompt includes fitness-specific guidelines and safety instructions
        """
        # Check cache first (static prompt cache)
        # Reduces token usage by avoiding prompt reconstruction
        agent_type = self._get_agent_type()
        from app.services.prompt_cache import prompt_cache
        cached_prompt = prompt_cache.get_static_prompt(agent_type)
        if cached_prompt:
            return cached_prompt
        
        # Not cached, build it
        # Use prompt component system for modular prompt building
        from app.agents.prompts.fitness_prompt import get_fitness_prompt
        return get_fitness_prompt()
    
    def _get_personality_traits(self) -> str:
        """
        Add physical fitness-specific motivational personality traits.
        
        This method returns personality traits that are appended to the base
        system prompt. These traits make the agent more motivational and
        action-oriented, matching the fitness domain.
        
        Returns:
            str: Personality traits string to append to base prompt
            
        Personality Traits:
            - Motivational & Energetic: Enthusiastic and energetic tone
            - Active Voice: Action-oriented language ("Let's do this!" not "Exercises should be performed")
            - Encouragement Phrases: Motivational language ("You've got this!", "Let's crush this!")
            - Celebrate Progress: Acknowledge achievements
            - Believe in Them: Show confidence in user abilities
            - Professional but Friendly: Expert but approachable
            - Safety with Enthusiasm: Firm but encouraging safety warnings
            - Action-Oriented: Frame everything as actions to DO
            - Match Their Energy: Adapt to user's energy level
            
        Note:
            - These traits are appended to base prompt
            - Makes agent more engaging and motivational
            - Maintains safety focus while being encouraging
        """
        return """- **Motivational & Energetic**: Be enthusiastic and energetic - you're excited about fitness and want to share that energy
- **Active Voice Always**: Use active, action-oriented language: "Let's build strength!", "We're going to crush this workout!", "Let's get those gains!" NOT "Strength can be built" or "Exercises should be performed"
- **Encouragement Phrases**: Use motivational language liberally: "You've got this!", "Let's do this!", "You're going to love this!", "This is going to be awesome!", "You're crushing it!"
- **Celebrate Progress**: Acknowledge achievements: "That's amazing progress!", "You're doing great!", "Look how far you've come!"
- **Believe in Them**: Show confidence in their abilities: "I know you can do this", "You're stronger than you think", "Let's push past your limits"
- **Professional but Friendly**: Maintain expertise while being approachable - like a knowledgeable friend who's also a trainer
- **Safety with Enthusiasm**: When warning about safety, be firm but encouraging: "Let's keep you safe so you can keep crushing it!", "We'll find something that works for you"
- **Action-Oriented**: Frame everything as something to DO: "Let's start with...", "We'll work on...", "I want you to try..."
- **Match Their Energy**: If they're pumped, match that energy; if they're hesitant, be supportive and build confidence"""
    
    async def recommend_exercise(self, user_query: str) -> Dict[str, Any]:
        """
        Recommend exercises based on user query with comprehensive safety validation.
        
        This method implements a multi-step safety validation process using reasoning
        patterns to ensure exercises are safe for the user before and after response
        generation. It checks for medical conflicts at multiple stages.
        
        Safety Validation Flow:
            1. Pre-check: Identifies potential exercise conflicts before response generation
            2. Reasoning: Enhances query with conflict context for informed recommendations
            3. Response Generation: Agent generates response with conflict awareness
            4. Post-validation: Validates final response for any missed conflicts
            5. Block Detection: Identifies block-level conflicts (high severity)
        
        Args:
            user_query: User's query requesting exercise recommendations
            
        Returns:
            Dict[str, Any]: Response dictionary with:
                {
                    "response": str,  # Agent's exercise recommendation
                    "warnings": List[str] or None,  # Medical conflict warnings (if any)
                    "degraded": bool,  # True if fallback model was used
                    "fallback_info": Dict or None  # Fallback model information (if degraded)
                }
                
        Warning Types:
            - Block-level warnings: "BLOCKED: ..." (high severity, exercise should be avoided)
            - Warning-level warnings: "Warning: ..." (moderate severity, exercise needs modification)
            
        Safety Features:
            - Pre-check prevents generating unsafe recommendations
            - Post-validation catches any missed conflicts
            - Block-level conflicts prevent logging unsafe exercises
            - Warnings are included in response for user awareness
            
        Note:
            - Uses ExerciseSafetyReasoningPattern for comprehensive validation
            - Stores user_query and context for tool interception
            - Includes degraded flag if fallback model was used
        """
        # Get context for reasoning pattern
        # Context includes medical history and user preferences
        # Used by reasoning pattern for safety checking
        context = {
            "medical_history": self._shared_context.get("medical_history") if self._shared_context else None,
            "user_preferences": self._shared_context.get("user_preferences") if self._shared_context else None
        }
        
        # STEP 1: Pre-check using reasoning pattern
        # Identifies potential exercise conflicts before response generation
        # Prevents agent from generating unsafe recommendations
        pre_check_results = await self.exercise_safety_pattern.pre_check(user_query, context)
        
        # STEP 2: Enhance query with conflict context using reasoning pattern
        # Adds conflict information to query so agent can make informed recommendations
        # Agent receives conflict context and can suggest alternatives or modifications
        enhanced_query = await self.exercise_safety_pattern.reason(user_query, context, pre_check_results)
        
        # STEP 3: Get agent response (with conflict context if applicable)
        # Store user_query for conflict checking in tool execution
        # Used by tool interception to prevent logging unsafe exercises
        self._current_user_query = user_query  # Original query (for post-validation)
        self._current_context = context  # Context (for tool interception)
        response = await self.run(enhanced_query)  # Generate response with enhanced query
        
        # STEP 4: Post-validate response using reasoning pattern
        # Validates final response for any missed conflicts
        # Catches conflicts that weren't caught in pre-check
        validation_results = await self.exercise_safety_pattern.post_validate(response, user_query, context)
        warnings = validation_results.get("warnings")  # Extract warnings from validation results
        
        # Check if we have block-level conflicts
        # Block-level conflicts indicate high-risk exercises that should be avoided
        # Used to prevent logging unsafe exercises
        self._has_block_conflict = False
        if warnings:
            for warning in warnings:
                if isinstance(warning, str) and "BLOCKED:" in warning.upper():
                    self._has_block_conflict = True
                    break
        
        # P0.3: Include degraded flag and fallback info if fallback model was used
        # Degraded mode indicates fallback model was used (service degradation)
        result = {
            "response": response,  # Agent's exercise recommendation
            "warnings": warnings if warnings else None  # Medical conflict warnings (if any)
        }
        if hasattr(self, '_used_fallback_model') and self._used_fallback_model:
            result["degraded"] = True  # Fallback model was used
            result["fallback_info"] = getattr(self, '_fallback_info', None)  # Fallback model information
        else:
            result["degraded"] = False  # Primary model was used
        return result
    
    async def run(self, user_input: str) -> str:
        """
        Override run method to intercept create_workout_log tool calls.
        
        This method extends BaseAgent.run() to add safety checking for workout
        log creation. It intercepts create_workout_log tool calls and prevents
        logging exercises that have block-level medical conflicts.
        
        Safety Interception:
            - Intercepts create_workout_log tool calls
            - Checks exercises for block-level conflicts before logging
            - Prevents logging unsafe exercises (block severity)
            - Allows logging safe exercises or exercises with warnings only
            
        Tool Execution:
            - Other tools execute normally (no interception)
            - create_workout_log is intercepted for safety checking
            - Block-level conflicts prevent logging with error message
            
        Args:
            user_input: User's input query
            
        Returns:
            str: Agent's final response
            
        Note:
            - Falls back to parent implementation on error
            - Uses exercise keyword matching for conflict detection
            - Prevents logging exercises with block-level conflicts
        """
        from langchain_core.messages import ToolMessage
        
        # Call parent run method but intercept tool calls
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
            
            # Build enhanced system message with full context to reduce tool calls
            enhanced_system_message = self._build_enhanced_system_prompt()
            
            # Load recent conversation history for context
            # This allows agents to recall previous messages in the conversation
            conversation_messages = []
            try:
                # Get recent conversation history for this agent type (last 20 messages)
                # This provides context for follow-up questions and maintains conversation flow
                agent_type = self._get_agent_type()
                from app.models.conversation_message import ConversationMessage
                history_query = self.db.query(ConversationMessage).filter(
                    ConversationMessage.user_id == self.user_id,
                    ConversationMessage.agent_type == agent_type
                ).order_by(ConversationMessage.created_at.desc()).limit(20).all()
                
                # Reverse to get chronological order (oldest first)
                history_query.reverse()
                
                # Convert conversation history to LangChain messages
                for msg in history_query:
                    if msg.role == 'user':
                        conversation_messages.append(HumanMessage(content=msg.content))
                    elif msg.role == 'assistant':
                        conversation_messages.append(AIMessage(content=msg.content))
            except Exception as e:
                # If loading history fails, log but continue without it
                # Don't block agent execution if history loading fails
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to load conversation history: {e}")
            
            # Build messages with enhanced system prompt and conversation history
            messages = [
                SystemMessage(content=enhanced_system_message),
            ]
            # Add conversation history before current message
            messages.extend(conversation_messages)
            # Add current user input
            messages.append(HumanMessage(content=user_input))
            
            max_iterations = 5
            iteration = 0
            
            # Track URLs from web_search tool calls for formatting at end
            web_search_urls = []  # List of (title, url) tuples from web_search calls
            
            while iteration < max_iterations:
                iteration += 1
                
                # Get LLM response with tools (with timeout)
                # P1.1: Add timeout to LLM call
                try:
                    response = await asyncio.wait_for(
                        self.llm_with_tools.ainvoke(messages),
                        timeout=getattr(self, 'llm_timeout', 60.0)
                    )
                except asyncio.TimeoutError:
                    timeout_msg = f"LLM call timed out after {getattr(self, 'llm_timeout', 60.0)} seconds"
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(timeout_msg)
                    if self.tracer:
                        self.tracer.log_timeout(getattr(self, 'llm_timeout', 60.0), "LLM call")
                    raise TimeoutError(f"Request timed out after {getattr(self, 'llm_timeout', 60.0)} seconds. Please try again with a simpler query.")
                
                messages.append(response)
                
                # Check if LLM wants to call tools
                if hasattr(response, 'tool_calls') and response.tool_calls and len(response.tool_calls) > 0:
                    # Execute tool calls
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get("name", "")
                        tool_input = tool_call.get("args", {})
                        tool_call_id = tool_call.get("id", "")
                        
                        # Intercept create_workout_log if there are block conflicts
                        # Safety feature: Prevents logging exercises with block-level conflicts
                        if tool_name == "create_workout_log":
                            # Get the exercises from tool input
                            # Exercises are provided as text (JSON string or plain text)
                            exercises_text = tool_input.get("exercises", "")
                            exercise_type = tool_input.get("exercise_type", "")
                            
                            # Check for conflicts in the exercises
                            # Block-level conflicts prevent logging (high severity)
                            has_block = False
                            if exercises_text:
                                # Check each exercise mentioned in the exercises text
                                # Uses keyword matching to identify exercises
                                exercises_lower = exercises_text.lower()
                                # Use the same exercise keywords from post_validate
                                # Comprehensive list of exercise keywords for conflict detection
                                exercise_keywords = [
                                    "squat", "squats", "deadlift", "deadlifts", "dead lift", "dead lifts",
                                    "lunge", "lunges", "running", "run", "jumping", "jump", "sprinting", "sprint",
                                    "triathlon", "marathon", "ironman", "half ironman", "ultramarathon",
                                    "hiit", "high intensity", "heavy lifting", "heavy", "weights",
                                    "pull-up", "pull-ups", "push-up", "push-ups", "overhead press", "shoulder press",
                                    "burpees", "burpee", "circuit training", "endurance", "swimming", "cycling", "biking"
                                ]
                                
                                # Check each exercise keyword for conflicts
                                for keyword in exercise_keywords:
                                    if keyword in exercises_lower:
                                        # Check exercise safety against medical history
                                        conflict_check = self.check_exercise_safety(keyword)
                                        # Block-level conflicts prevent logging
                                        if conflict_check.get("has_conflict") and conflict_check.get("severity") == "block":
                                            has_block = True
                                            break  # Found block conflict, no need to check more
                            
                            if has_block:
                                # Prevent logging - return error message
                                # Block-level conflicts prevent logging for user safety
                                tool_result = "Workout log NOT created: This exercise conflicts with your medical conditions and has been blocked for your safety."
                                if self.tracer:
                                    self.tracer.log_warning(f"Blocked create_workout_log due to medical conflict")
                            else:
                                # No block conflict, proceed with logging
                                tool_result = None
                                for tool in self.tools:
                                    if tool.name == tool_name:
                                        try:
                                            if self.tracer:
                                                self.tracer.log_tool_call(
                                                    tool_name=tool_name,
                                                    tool_input=tool_input,
                                                    tool_output=""
                                                )
                                            
                                            tool_result = tool._run(**tool_input)
                                            
                                            # Extract URLs from web_search tool results
                                            if tool_name == "web_search" and tool_result:
                                                import re
                                                title_url_pattern = r'Title:\s*([^\n]+)\nURL:\s*(https?://[^\s\n]+)'
                                                url_pattern = r'URL:\s*(https?://[^\s\n]+)'
                                                
                                                matches = re.findall(title_url_pattern, str(tool_result))
                                                for title, url in matches:
                                                    if url not in [u for _, u in web_search_urls]:
                                                        web_search_urls.append((title.strip(), url))
                                                
                                                if not matches:
                                                    urls = re.findall(url_pattern, str(tool_result))
                                                    for url in urls:
                                                        if url not in [u for _, u in web_search_urls]:
                                                            web_search_urls.append(("", url))
                                            
                                            if self.tracer:
                                                if self.tracer.current_trace and self.tracer.current_trace.get("tools_called"):
                                                    self.tracer.current_trace["tools_called"][-1]["output"] = str(tool_result)[:500]
                                            
                                            break
                                        except ToolRetryableError as e:
                                            # P0.4: Retryable errors - retry with exponential backoff
                                            max_tool_retries = 3
                                            tool_retry_delay = 0.1
                                            tool_attempt = 0
                                            
                                            while tool_attempt < max_tool_retries:
                                                try:
                                                    await asyncio.sleep(tool_retry_delay * (2 ** tool_attempt))
                                                    tool_result = tool._run(**tool_input)
                                                    if self.tracer:
                                                        if self.tracer.current_trace and self.tracer.current_trace.get("tools_called"):
                                                            self.tracer.current_trace["tools_called"][-1]["output"] = str(tool_result)[:500]
                                                    break
                                                except ToolRetryableError:
                                                    tool_attempt += 1
                                                    if tool_attempt >= max_tool_retries:
                                                        tool_result = f"Error executing {tool_name}: {str(e)} (failed after {max_tool_retries + 1} retries)"
                                                        if self.tracer:
                                                            self.tracer.log_warning(f"Tool {tool_name} failed after {max_tool_retries + 1} retries")
                                                        break
                                            
                                            if tool_result is None:
                                                tool_result = f"Error executing {tool_name}: {str(e)}"
                                            break
                                        
                                        except (ToolInputValidationError, ToolExecutionError) as e:
                                            # P0.4: Non-retryable tool errors
                                            logger.error(f"Tool {tool_name} error: {e}")
                                            if self.tracer:
                                                if isinstance(e, ToolInputValidationError):
                                                    self.tracer.log_warning(f"Tool {tool_name} input validation error: {e}")
                                                else:
                                                    self.tracer.log_warning(f"Tool {tool_name} execution error: {e}")
                                            tool_result = f"Error executing {tool_name}: {str(e)}"
                                            break
                                        
                                        except Exception as e:
                                            # P0.4: Unexpected errors
                                            logger.error(f"Tool {tool_name} unexpected error: {e}", exc_info=True)
                                            if self.tracer:
                                                self.tracer.log_warning(f"Tool {tool_name} unexpected error: {str(e)}")
                                            tool_result = f"Error executing {tool_name}: {str(e)}"
                                            break
                        else:
                            # Not create_workout_log, proceed normally
                            tool_result = None
                            for tool in self.tools:
                                if tool.name == tool_name:
                                    try:
                                        if self.tracer:
                                            self.tracer.log_tool_call(
                                                tool_name=tool_name,
                                                tool_input=tool_input,
                                                tool_output=""
                                            )
                                        
                                        tool_result = tool._run(**tool_input)
                                        
                                        # Extract URLs from web_search tool results
                                        if tool_name == "web_search" and tool_result:
                                            import re
                                            title_url_pattern = r'Title:\s*([^\n]+)\nURL:\s*(https?://[^\s\n]+)'
                                            url_pattern = r'URL:\s*(https?://[^\s\n]+)'
                                            
                                            matches = re.findall(title_url_pattern, str(tool_result))
                                            for title, url in matches:
                                                if url not in [u for _, u in web_search_urls]:
                                                    web_search_urls.append((title.strip(), url))
                                            
                                            if not matches:
                                                urls = re.findall(url_pattern, str(tool_result))
                                                for url in urls:
                                                    if url not in [u for _, u in web_search_urls]:
                                                        web_search_urls.append(("", url))
                                        
                                        if self.tracer:
                                            if self.tracer.current_trace and self.tracer.current_trace.get("tools_called"):
                                                self.tracer.current_trace["tools_called"][-1]["output"] = str(tool_result)[:500]
                                        
                                        break
                                    except ToolRetryableError as e:
                                        # P0.4: Retryable errors - retry with exponential backoff
                                        max_tool_retries = 3
                                        tool_retry_delay = 0.1
                                        tool_attempt = 0
                                        
                                        while tool_attempt < max_tool_retries:
                                            try:
                                                await asyncio.sleep(tool_retry_delay * (2 ** tool_attempt))
                                                tool_result = tool._run(**tool_input)
                                                if self.tracer:
                                                    if self.tracer.current_trace and self.tracer.current_trace.get("tools_called"):
                                                        self.tracer.current_trace["tools_called"][-1]["output"] = str(tool_result)[:500]
                                                break
                                            except ToolRetryableError:
                                                tool_attempt += 1
                                                if tool_attempt >= max_tool_retries:
                                                    tool_result = f"Error executing {tool_name}: {str(e)} (failed after {max_tool_retries + 1} retries)"
                                                    if self.tracer:
                                                        self.tracer.log_warning(f"Tool {tool_name} failed after {max_tool_retries + 1} retries")
                                                    break
                                        
                                        if tool_result is None:
                                            tool_result = f"Error executing {tool_name}: {str(e)}"
                                        break
                                    
                                    except (ToolInputValidationError, ToolExecutionError) as e:
                                        # P0.4: Non-retryable tool errors
                                        logger.error(f"Tool {tool_name} error: {e}")
                                        if self.tracer:
                                            if isinstance(e, ToolInputValidationError):
                                                self.tracer.log_warning(f"Tool {tool_name} input validation error: {e}")
                                            else:
                                                self.tracer.log_warning(f"Tool {tool_name} execution error: {e}")
                                        tool_result = f"Error executing {tool_name}: {str(e)}"
                                        break
                                    
                                    except Exception as e:
                                        # P0.4: Unexpected errors
                                        logger.error(f"Tool {tool_name} unexpected error: {e}", exc_info=True)
                                        if self.tracer:
                                            self.tracer.log_warning(f"Tool {tool_name} unexpected error: {str(e)}")
                                        tool_result = f"Error executing {tool_name}: {str(e)}"
                                        break
                        
                        if tool_result is None:
                            # P0.4: Use ToolNotFoundError
                            from app.exceptions.agent_exceptions import ToolNotFoundError
                            not_found_error = ToolNotFoundError(tool_name)
                            tool_result = f"Error: {str(not_found_error)}"
                            if self.tracer:
                                self.tracer.log_warning(f"Tool {tool_name} not found")
                                self.tracer.log_warning(f"Tool {tool_name} not found")
                        
                        # Add tool result as ToolMessage
                        messages.append(ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call_id
                        ))
                else:
                    # No tool calls, return the final response
                    final_response = response.content if hasattr(response, 'content') else str(response)
                    return self._append_web_search_links(final_response, web_search_urls)
            
            # If we've reached max iterations, return the last response
            last_response = messages[-1]
            final_response = last_response.content if hasattr(last_response, 'content') else str(last_response)
            return self._append_web_search_links(final_response, web_search_urls)
            
        except Exception as e:
            # Fallback to parent implementation on error
            return await super().run(user_input)
    
    def _extract_potential_exercises(self, query: str) -> list:
        """
        Extract potential exercise mentions from user query.
        
        This method identifies exercise keywords in the user query for safety
        checking. Used by ExerciseSafetyReasoningPattern for pre-check validation.
        
        Args:
            query: User's query string
            
        Returns:
            list: List of exercise keywords found in query
            
        Extraction Strategy:
            - Converts query to lowercase for case-insensitive matching
            - Matches against comprehensive list of exercise keywords
            - Returns all matching keywords (may include duplicates/variations)
            
        Exercise Keywords:
            - Strength exercises: squats, deadlifts, lunges, presses
            - Cardio exercises: running, jumping, sprinting, swimming, cycling
            - High-intensity: HIIT, circuit training, endurance events
            - Endurance events: triathlon, marathon, ironman, ultramarathon
            
        Note:
            - Used by reasoning pattern for pre-check validation
            - Helps identify exercises before response generation
            - Case-insensitive matching
        """
        query_lower = query.lower()  # Convert to lowercase for case-insensitive matching
        # Comprehensive list of exercise keywords for extraction
        # Includes common exercises and variations
        exercise_keywords = [
            "triathlon", "marathon", "ironman", "half ironman", "ultramarathon",
            "squat", "squats", "deadlift", "deadlifts", "dead lift", "dead lifts",
            "lunge", "lunges",
            "running", "run", "jumping", "jump", "sprinting", "sprint",
            "hiit", "high intensity", "heavy lifting", "heavy", "weights",
            "pull-up", "pull-ups", "push-up", "push-ups",
            "overhead press", "shoulder press", "leg press",
            "burpees", "burpee", "circuit training", "endurance",
            "swimming", "cycling", "biking", "marathon training"
        ]
        
        # Find matching exercise keywords in query
        found_exercises = []
        for keyword in exercise_keywords:
            if keyword in query_lower:
                found_exercises.append(keyword)
        
        return found_exercises
    
    def _check_response_for_conflicts(self, response: str) -> list:
        """
        Check agent response for exercise mentions and validate against medical history.
        
        This method scans the agent's response for exercise keywords and checks
        each exercise against the user's medical history for conflicts. Used
        for post-validation to catch any missed conflicts.
        
        Args:
            response: Agent's response text to check for exercise conflicts
            
        Returns:
            list: List of warning messages (block-level warnings first, then warning-level)
            
        Validation Process:
            1. Convert response to lowercase for case-insensitive matching
            2. Match against comprehensive list of exercise keywords
            3. Check each exercise against medical history
            4. Collect warnings grouped by severity (block vs warning)
            5. Return warnings with block-level warnings first
            
        Warning Format:
            - Block-level: "BLOCKED: ..." (high severity, exercise should be avoided)
            - Warning-level: "Warning: ..." (moderate severity, exercise needs modification)
            
        Frontend Detection:
            - Ensures explicit severity indicators ("BLOCKED:" or "Warning:")
            - Frontend uses these prefixes to detect and display warnings appropriately
            
        Note:
            - Used by post-validation in recommend_exercise()
            - Prevents duplicate warnings for same exercise
            - Returns warnings sorted by severity (blocks first)
        """
        warnings = []
        checked_exercises = set()  # Track checked exercises to avoid duplicates
        
        exercise_keywords = [
            "squat", "squats", "deadlift", "deadlifts", "dead lift", "dead lifts",
            "lunge", "lunges",
            "press", "overhead press", "pull-up", "pull-ups", "push-up", "push-ups",
            "running", "run", "jumping", "jump", "jumps", "overhead",
            "heavy lifting", "heavy", "weight", "weights",
            "leg press", "step-up", "step-ups", "bent-over row", "bent-over rows",
            "lateral raise", "lateral raises", "upright row", "upright rows",
            "shoulder press", "shoulder presses", "plank", "planks",
            "handstand", "handstands", "wrist curl", "wrist curls",
            "box jump", "box jumps", "neck bridge", "neck bridges",
            "burpees", "burpee", "hiit", "high intensity", "sprinting", "sprint",
            "circuit training", "max effort", "endurance running", "dips", "dip",
            "plyometrics", "good mornings", "back extensions", "bridges", "headstands",
            "abdominal crunches", "crunches", "lying on back",
            "triathlon", "marathon", "endurance events", "endurance event", "long distance running",
            "ultramarathon", "ultra marathon", "ironman", "half ironman", "iron man", "half iron man",
            "swimming", "cycling", "biking", "long distance", "endurance"
        ]
        
        response_lower = response.lower()
        block_warnings = []
        warning_warnings = []
        
        for keyword in exercise_keywords:
            if keyword in response_lower and keyword not in checked_exercises:
                checked_exercises.add(keyword)
                conflict_check = self.check_exercise_safety(keyword)
                if conflict_check.get("has_conflict"):
                    warning_msg = conflict_check.get("message")
                    severity = conflict_check.get("severity", "warning")
                    
                    if warning_msg:
                        # Ensure message has explicit severity indicator for frontend
                        if severity == "block":
                            # Ensure "BLOCKED:" prefix is present for frontend detection
                            if not warning_msg.upper().startswith("BLOCKED"):
                                warning_msg = f"BLOCKED: {warning_msg.replace('MEDICAL CONCERN:', '').replace('BLOCKED:', '').strip()}"
                            if warning_msg not in block_warnings:
                                block_warnings.append(warning_msg)
                        else:
                            # Ensure "Warning:" prefix is present for frontend detection
                            if not warning_msg.startswith("Warning:"):
                                warning_msg = f"Warning: {warning_msg.replace('MEDICAL CONSIDERATION:', '').replace('Warning:', '').strip()}"
                            if warning_msg not in warning_warnings:
                                warning_warnings.append(warning_msg)
        
        # Return warnings with blocks first (higher severity)
        return block_warnings + warning_warnings
    
    async def create_workout_plan(self, duration_minutes: int = 30, exercise_type: str = None) -> str:
        """
        Create a structured workout plan for the user.
        
        This method creates a structured workout plan with specified duration and
        optional exercise type focus. It uses recommend_exercise() with safety
        validation to ensure the plan is safe for the user.
        
        Args:
            duration_minutes: Duration of workout plan in minutes (default: 30)
            exercise_type: Optional exercise type focus (e.g., "strength", "cardio", "calisthenics")
            
        Returns:
            str: Structured workout plan response
            
        Plan Creation:
            - Builds query requesting workout plan
            - Includes duration and optional exercise type
            - Explicitly requests medical history check for safety
            - Uses recommend_exercise() for safety validation
            
        Safety Features:
            - Checks medical history before creating plan
            - Validates exercises against medical conditions
            - Includes warnings for any conflicts
            - Prevents unsafe exercises from being included
            
        Example:
            create_workout_plan(30, "strength")
            -> Creates 30-minute strength-focused workout plan
            
        Note:
            - Uses recommend_exercise() for comprehensive safety validation
            - Returns only response (warnings are handled separately)
            - Plan is tailored to user's medical history and preferences
        """
        # Build query requesting workout plan
        # Includes duration and optional exercise type focus
        query = f"Create a {duration_minutes}-minute workout plan"
        if exercise_type:
            query += f" focused on {exercise_type}"
        # Explicitly request medical history check for safety
        query += ". Make sure to check my medical history first and create a plan that's safe for me."
        
        # Get workout plan with safety validation
        # recommend_exercise() includes pre-check, reasoning, and post-validation
        result = await self.recommend_exercise(query)
        return result["response"]  # Return only response (warnings handled separately)

