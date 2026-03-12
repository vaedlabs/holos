"""
Coordinator Agent - Routes queries and creates holistic plans.

This module provides the CoordinatorAgent class, which orchestrates Physical Fitness,
Nutrition, and Mental Fitness agents. It analyzes user queries to determine routing
strategy and can create comprehensive holistic plans combining all three domains.

Key Features:
- Query routing: Analyzes queries and routes to appropriate specialized agent
- Holistic planning: Creates comprehensive plans combining all three domains
- Streaming support: Provides real-time step updates during processing
- Parallel execution: Executes multiple agents in parallel for holistic plans
- Error handling: Gracefully handles agent failures with degraded mode
- Context sharing: Shares user context across all sub-agents for efficiency

Routing Strategy:
- Physical Fitness: Exercise, workout, training, strength, cardio
- Nutrition: Food, meal, diet, calories, macros, protein, eating
- Mental Fitness: Mindfulness, meditation, stress, anxiety, sleep, mood
- Holistic: Comprehensive planning across all domains

Technical Approach:
- Extends BaseAgent for common functionality
- Uses LLM-based routing decision making
- Implements streaming for real-time updates
- Parallel agent execution with timeout protection
- Degraded mode handling for partial failures
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import asyncio
from asyncio import TimeoutError as AsyncTimeoutError
import logging
from app.agents.base_agent import BaseAgent
from app.agents.physical_fitness_agent import PhysicalFitnessAgent
from app.agents.nutrition_agent import NutritionAgent
from app.agents.mental_fitness_agent import MentalFitnessAgent
from app.services.context_manager import context_manager

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    """
    Coordinator Agent that routes queries to appropriate agents or creates holistic plans.
    
    The CoordinatorAgent acts as the orchestrator for the entire agent system. It analyzes
    user queries to determine the best routing strategy and either routes to a specialized
    agent (Physical Fitness, Nutrition, or Mental Fitness) or creates a comprehensive
    holistic plan combining all three domains.
    
    Key Capabilities:
        - Query analysis and routing: Determines which agent should handle the query
        - Single-agent routing: Routes to Physical Fitness, Nutrition, or Mental Fitness
        - Holistic planning: Creates comprehensive plans combining all three domains
        - Streaming support: Provides real-time step updates during processing
        - Parallel execution: Executes multiple agents in parallel for efficiency
        - Error handling: Gracefully handles agent failures with degraded mode
        
    Routing Logic:
        - Uses LLM to analyze query intent and keywords
        - Routes to Physical Fitness for exercise/workout queries
        - Routes to Nutrition for food/diet queries
        - Routes to Mental Fitness for mindfulness/stress queries
        - Creates holistic plan for comprehensive planning requests
        
    Holistic Planning:
        - Executes all three agents in parallel
        - Synthesizes results into unified plan
        - Handles partial failures gracefully (degraded mode)
        - Provides component-level breakdown
        
    Attributes:
        user_id: User ID for user-specific operations
        db: Database session for querying user data
        model_name: LLM model name (default: "gpt-4.1")
        tracer: AgentTracer instance for observability (optional)
        physical_agent: PhysicalFitnessAgent instance
        nutrition_agent: NutritionAgent instance
        mental_agent: MentalFitnessAgent instance
        _shared_context: Shared user context from ContextManager (inherited from BaseAgent)
    """
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gpt-4.1",
        tracer: Optional[Any] = None
    ):
        """
        Initialize CoordinatorAgent with sub-agents for orchestration.
        
        This method initializes the coordinator agent and all sub-agents (Physical Fitness,
        Nutrition, and Mental Fitness). It fetches shared context once and passes it to all
        sub-agents to reduce redundant database queries.
        
        Args:
            user_id: User ID for user-specific operations
            db: Database session for querying user data
            model_name: LLM model name (default: "gpt-4.1")
            tracer: AgentTracer instance for observability (optional)
            
        Initialization Steps:
            1. Fetch shared context once (medical history, preferences)
            2. Initialize BaseAgent with shared context and tracer
            3. Initialize PhysicalFitnessAgent with shared context
            4. Initialize NutritionAgent with shared context
            5. Initialize MentalFitnessAgent with shared context
            
        Context Sharing:
            - Shared context is fetched once and passed to all sub-agents
            - Reduces redundant database queries
            - Ensures consistent context across all agents
            
        Note:
            - Sub-agents share the same context for consistency
            - Tracer is passed to all sub-agents for unified observability
            - Sub-agents can be called directly or via router endpoints
        """
        # Fetch shared context once for all sub-agents
        # Shared context includes medical history and preferences
        # Reduces redundant database queries across all agents
        shared_context = context_manager.get_user_context(user_id, db)
        
        # Initialize base agent with shared context and tracer
        # BaseAgent provides common functionality (LLM, tools, prompts)
        super().__init__(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
        
        # Initialize sub-agents for orchestration, passing shared context and tracer
        # All sub-agents receive the same shared context for consistency
        # Note: Sub-agents will get their own tracers when called via router endpoints
        # But if coordinator calls them directly, they can use coordinator's tracer
        self.physical_agent = PhysicalFitnessAgent(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
        self.nutrition_agent = NutritionAgent(user_id, db, shared_context=shared_context, tracer=tracer)
        self.mental_agent = MentalFitnessAgent(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
    
    def _get_agent_type(self) -> str:
        """
        Get agent type identifier for caching and identification.
        
        Returns:
            str: Agent type identifier ("coordinator")
            
        Note:
            - Used for prompt caching (static and enhanced prompts)
            - Used for identification in logs and traces
        """
        return "coordinator"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for coordinator agent.
        
        This method retrieves the system prompt for the coordinator agent,
        checking cache first, then building if not cached.
        
        Returns:
            str: System prompt for coordinator agent
            
        Prompt Strategy:
            1. Check cache first (static prompt cache)
            2. If cached, return cached prompt
            3. If not cached, build prompt from coordinator_prompt module
            4. Cache the built prompt for future use
            
        Note:
            - Uses prompt caching to reduce token usage
            - Static prompts are cached indefinitely (version-based invalidation)
            - Prompt includes routing guidelines and holistic planning instructions
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
        from app.agents.prompts.coordinator_prompt import get_coordinator_prompt
        return get_coordinator_prompt()
    
    def _get_personality_traits(self) -> str:
        """
        Get coordinator-specific personality traits for humanization.
        
        Returns:
            str: Personality traits string for coordinator agent
            
        Personality Traits:
            - Moderate: Friendly and warm, but balanced (not overly enthusiastic or too formal)
            - Natural Language: Conversational patterns ("Hey!", "Got it!")
            - Encouragement: Supportive phrases ("That's a great goal!", "I'm here to help!")
            - Transparency: Explains routing/coordination naturally
            - Collaborative: Uses "we" and "us" language
            - Acknowledges Complexity: Recognizes comprehensive planning requests
            - Matches User Energy: Adapts to user's tone (excited vs. calm)
            
        Note:
            - These traits are used in prompt building for humanization
            - Helps coordinator feel more natural and approachable
            - Balances professionalism with friendliness
        """
        return """- **Moderate Personality**: Friendly and warm, but balanced - not overly enthusiastic or too formal
- **Natural Language**: Use conversational patterns like "Hey!", "Got it!", "Let me figure out the best way to help you"
- **Occasional Encouragement**: Sprinkle in supportive phrases like "That's a great goal!", "I'm here to help!", "We'll figure this out together"
- **Transparency**: When routing or coordinating, explain what you're doing naturally: "Let me connect you with our nutrition expert", "I'm putting together a complete plan for you"
- **Collaborative Tone**: Use "we" and "us" - "Let's get you set up", "We can create a plan that works for you"
- **Acknowledge Complexity**: When creating holistic plans, acknowledge it's comprehensive: "This is going to be awesome - let me bring everything together for you"
- **Match User Energy**: If they're excited, match that energy; if they're calm, be measured and supportive"""

    async def route_query_stream(self, user_query: str, image_base64: Optional[str] = None):
        """
        Analyze query and route to appropriate agent or create holistic plan (streaming version).
        
        This method analyzes the user query using LLM to determine routing strategy,
        then either routes to a specialized agent or creates a holistic plan. It yields
        step updates in real-time and finally yields the complete result.
        
        Execution Flow:
            1. Analyze query using LLM routing decision
            2. Route to appropriate agent (Physical Fitness, Nutrition, Mental Fitness)
            3. Or create holistic plan combining all three domains
            4. Yield step updates throughout processing
            5. Yield final result with response, warnings, and routing information
        
        Routing Decision:
            - Uses LLM to analyze query intent and keywords
            - Routes to Physical Fitness for exercise/workout queries
            - Routes to Nutrition for food/diet queries
            - Routes to Mental Fitness for mindfulness/stress queries
            - Creates holistic plan for comprehensive requests
            
        Args:
            user_query: User's query requesting guidance
                       Examples: "Help me plan a workout", "What should I eat?",
                                "I'm stressed", "Create a complete wellness plan"
            image_base64: Optional base64-encoded image for nutrition analysis
                         Used when routing to Nutrition agent
            
        Yields:
            Dict[str, Any]: Step updates and final result:
                - Step updates: {"type": "step", "data": "step text"}
                - Final result: {"type": "response", "data": {...}}
                
        Final Result Structure:
            {
                "response": str,  # Agent's response
                "warnings": List[str] or None,  # Warnings (if any)
                "routed_to": str,  # "physical-fitness", "nutrition", "mental-fitness", or "holistic"
                "steps": List[str],  # List of step updates
                "nutrition_analysis": Dict or None,  # Nutrition analysis (if routed to nutrition)
                "degraded": bool,  # True if degraded mode (holistic plans only)
                "fallback_info": Dict or None  # Fallback info (holistic plans only)
            }
            
        Error Handling:
            - Routing errors: Returns error message with routing information
            - Agent errors: Handled by individual agents
            - Timeout errors: Logged and raised with user-friendly message
            
        Note:
            - Streaming allows real-time updates for better UX
            - Routing decision is strict to avoid bias toward physical fitness
            - Image is only used when routing to Nutrition agent
        """
        steps = []  # Track step updates for final result
        try:
            # Step 1: Analyzing query
            # Inform user that query is being analyzed
            step_text = "Analyzing your query..."
            steps.append(step_text)
            if self.tracer:
                self.tracer.log_step(step_text)
            yield {"type": "step", "data": step_text}
            
            # Use LLM to determine routing strategy with system context
            # Routing prompt includes system message and explicit routing guidelines
            # Critical: Avoid defaulting to physical fitness - analyze objectively
            routing_prompt = f"""{self.system_message}

---

TASK: Analyze this user query and determine the best routing approach.

User Query: "{user_query}"

IMPORTANT: Analyze the query objectively. Do NOT default to physical fitness. Consider all three domains equally:
- Physical Fitness: exercise, workout, training, strength, cardio, running, lifting
- Nutrition: food, meal, diet, calories, macros, protein, eating, recipes, meal planning
- Mental Fitness: mindfulness, meditation, stress, anxiety, sleep, mood, mental wellness, emotional health

Based on your role as Coordinator Agent and the domain classification guidelines above, determine if this query should be:
1. Routed to a single agent (Physical Fitness, Nutrition, or Mental Fitness)
2. Handled as a holistic plan requiring all three agents

CRITICAL: Match the query to the MOST APPROPRIATE domain based on keywords and intent. If the query mentions nutrition keywords, route to nutrition. If it mentions mental wellness keywords, route to mental fitness. Only route to physical fitness if the query is clearly about exercise or training.

Respond with ONLY one of these EXACT formats (no additional text):
- "ROUTE:physical-fitness" - ONLY if query is about exercise, workouts, or training
- "ROUTE:nutrition" - If query is about food, diet, calories, or eating
- "ROUTE:mental-fitness" - If query is about stress, sleep, mood, mindfulness, or mental wellness
- "HOLISTIC" - If query explicitly requests comprehensive planning or mentions multiple domains

Your response:"""

            # Use async LLM call with retry logic and timeout
            # Routing decision is critical - uses retry logic for reliability
            async def invoke_routing():
                """
                Invoke LLM for routing decision with timeout protection.
                
                This function wraps the LLM call with timeout protection to prevent
                hanging on slow API responses.
                """
                # P1.1: Add timeout to routing call
                # Prevents hanging on slow API responses
                try:
                    return await asyncio.wait_for(
                        self.llm.ainvoke(routing_prompt),  # LLM call for routing decision
                        timeout=getattr(self, 'llm_timeout', 60.0)  # Timeout in seconds
                    )
                except asyncio.TimeoutError:
                    timeout_msg = f"Routing call timed out after {getattr(self, 'llm_timeout', 60.0)} seconds"
                    logger.warning(timeout_msg)
                    if self.tracer:
                        self.tracer.log_timeout(getattr(self, 'llm_timeout', 60.0), "Routing call")
                    raise TimeoutError(f"Request timed out after {getattr(self, 'llm_timeout', 60.0)} seconds. Please try again.")
            
            from app.services.llm_retry import retry_llm_call
            # Get model name (should be set by BaseAgent, but fallback to None if not)
            routing_model_name = getattr(self, 'model_name', None)
            # Call LLM with retry logic for routing decision
            # Retry logic handles transient errors with exponential backoff
            routing_response = await retry_llm_call(
                func=invoke_routing,  # LLM invocation function
                max_retries=3,  # Maximum retry attempts
                initial_delay=1.0,  # Initial delay before retry (seconds)
                max_delay=60.0,  # Maximum delay cap (seconds)
                tracer=self.tracer,  # Tracer for logging retries
                model_name=routing_model_name,  # Current model name
                update_model_fn=None,  # Routing doesn't need model fallback (simple decision)
                service_name="openai",  # Coordinator uses OpenAI
            )
            routing_decision = routing_response.content.strip().upper()  # Normalize routing decision
            
            # Route to appropriate agent (strict matching to avoid bias)
            # Strict matching prevents accidental routing to wrong agent
            # Each routing branch follows same pattern: step update -> agent call -> synthesize -> yield result
            
            if routing_decision.startswith("ROUTE:PHYSICAL-FITNESS") or routing_decision == "ROUTE:PHYSICAL-FITNESS":
                # Route to Physical Fitness Agent
                # For exercise, workout, training queries
                step_text = "Routing to Physical Fitness Agent..."
                steps.append(step_text)
                if self.tracer:
                    self.tracer.log_step(step_text)
                yield {"type": "step", "data": step_text}
                
                # Call Physical Fitness Agent
                # recommend_exercise() handles exercise recommendations with safety checks
                result = await self.physical_agent.recommend_exercise(user_query)
                
                # Synthesize response
                step_text = "Synthesizing response..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                # Yield final result with routing information
                yield {
                    "type": "response",
                    "data": {
                        "response": result["response"],  # Agent's exercise recommendation
                        "warnings": result.get("warnings"),  # Safety warnings (if any)
                        "routed_to": "physical-fitness",  # Routing information
                        "steps": steps  # Step updates for UI
                    }
                }
            
            elif routing_decision.startswith("ROUTE:NUTRITION") or routing_decision == "ROUTE:NUTRITION":
                # Route to Nutrition Agent
                # For food, meal, diet queries
                step_text = "Routing to Nutrition Agent..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                # Call Nutrition Agent
                # recommend_meal() handles meal recommendations and image analysis
                # image_base64 is passed for food image analysis (if provided)
                result = await self.nutrition_agent.recommend_meal(user_query, image_base64)
                
                # Synthesize response
                step_text = "Synthesizing response..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                # Yield final result with routing information and nutrition analysis
                yield {
                    "type": "response",
                    "data": {
                        "response": result["response"],  # Agent's meal recommendation
                        "warnings": result.get("warnings"),  # Dietary restriction warnings (if any)
                        "nutrition_analysis": result.get("nutrition_analysis"),  # Nutrition data (if image provided)
                        "routed_to": "nutrition",  # Routing information
                        "steps": steps  # Step updates for UI
                    }
                }
            
            elif routing_decision.startswith("ROUTE:MENTAL-FITNESS") or routing_decision == "ROUTE:MENTAL-FITNESS":
                # Route to Mental Fitness Agent
                # For mindfulness, stress, sleep queries
                step_text = "Routing to Mental Fitness Agent..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                # Call Mental Fitness Agent
                # recommend_practice() handles mental wellness recommendations
                result = await self.mental_agent.recommend_practice(user_query)
                
                # Synthesize response
                step_text = "Synthesizing response..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                # Yield final result with routing information
                yield {
                    "type": "response",
                    "data": {
                        "response": result["response"],  # Agent's mental wellness recommendation
                        "warnings": result.get("warnings"),  # Warnings (if any)
                        "routed_to": "mental-fitness",  # Routing information
                        "steps": steps  # Step updates for UI
                    }
                }
            
            else:
                # Create holistic plan
                # For comprehensive planning requests or ambiguous queries
                # Holistic plans combine all three domains
                step_text = "Creating holistic plan..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                # Delegate to holistic plan creation (streaming)
                # create_holistic_plan_stream() handles parallel agent execution and synthesis
                async for item in self.create_holistic_plan_stream(user_query, image_base64, steps):
                    yield item
                
        except Exception as e:
            step_text = "Error occurred during processing"
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            yield {
                "type": "response",
                "data": {
                    "response": f"Error processing query: {str(e)}",
                    "warnings": [f"Coordinator error: {str(e)}"],
                    "routed_to": None,
                    "steps": steps
                }
            }
    
    async def route_query(self, user_query: str, image_base64: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze query and route to appropriate agent or create holistic plan (non-streaming version).
        
        This is a convenience wrapper around route_query_stream() that collects all
        step updates and returns only the final result. Useful for backward compatibility
        or when streaming is not needed.
        
        Args:
            user_query: User's query requesting guidance
            image_base64: Optional base64-encoded image for nutrition analysis
            
        Returns:
            Dict[str, Any]: Final result dictionary:
                {
                    "response": str,  # Agent's response
                    "warnings": List[str] or None,  # Warnings (if any)
                    "routed_to": str,  # Routing information
                    "steps": List[str],  # List of step updates
                    "nutrition_analysis": Dict or None,  # Nutrition analysis (if applicable)
                    "degraded": bool,  # True if degraded mode (holistic plans only)
                    "fallback_info": Dict or None  # Fallback info (holistic plans only)
                }
                
        Note:
            - Non-streaming version for backward compatibility
            - Collects all step updates and returns final result only
            - Returns error dict if no response received
        """
        final_result = None
        # Iterate through streaming results and collect final response
        async for item in self.route_query_stream(user_query, image_base64):
            if item["type"] == "response":
                final_result = item["data"]
        # Return final result or error dict if no response received
        return final_result or {
            "response": "Error: No response received",
            "warnings": ["Coordinator error: No response"],
            "routed_to": None,
            "steps": []
        }
    
    async def create_holistic_plan_stream(self, user_query: str, image_base64: Optional[str] = None, steps: Optional[List[str]] = None):
        """
        Create a holistic plan combining all three domains (streaming version).
        
        This method creates a comprehensive wellness plan by executing all three
        specialized agents in parallel and synthesizing their results into a unified plan.
        It yields step updates throughout processing and handles partial failures gracefully.
        
        Execution Flow:
            1. Prepare queries for all three agents
            2. Execute all agents in parallel with timeout protection
            3. Handle partial failures (degraded mode)
            4. Synthesize results into unified plan
            5. Yield step updates and final result
        
        Parallel Execution:
            - All three agents execute simultaneously for efficiency
            - Each agent has timeout protection (60 seconds default)
            - Partial failures are handled gracefully (degraded mode)
            - Failed agents are marked and excluded from synthesis
            
        Degraded Mode:
            - If some agents fail, plan is created with available components
            - Missing components are clearly indicated
            - User is informed about partial plan availability
            
        Args:
            user_query: User's query requesting comprehensive wellness plan
                       Examples: "Create a complete wellness plan", "Help me with everything"
            image_base64: Optional base64-encoded image for nutrition analysis
                         Passed to Nutrition agent if provided
            steps: Optional list of steps already tracked (will be extended)
                  Used when called from route_query_stream()
            
        Yields:
            Dict[str, Any]: Step updates and final result:
                - Step updates: {"type": "step", "data": "step text"}
                - Final result: {"type": "response", "data": {...}}
                
        Final Result Structure:
            {
                "response": str,  # Synthesized holistic plan
                "warnings": List[str] or None,  # Combined warnings from all agents
                "routed_to": "holistic",  # Routing information
                "steps": List[str],  # List of step updates
                "degraded": bool,  # True if some agents failed
                "fallback_info": Dict,  # Agent status information
                "components": Dict,  # Individual agent responses
                "nutrition_analysis": Dict or None  # Nutrition analysis (if available)
            }
            
        Error Handling:
            - Agent timeouts: Handled gracefully with error messages
            - Agent errors: Logged and marked as failed
            - Partial failures: Plan created with available components
            - Complete failure: Error message returned
            
        Note:
            - Parallel execution improves performance significantly
            - Degraded mode ensures partial plans are still useful
            - Component-level breakdown provides transparency
        """
        if steps is None:
            steps = []
        
        try:
            # Step 2: Gathering recommendations from all agents in parallel
            # Inform user that all agents are being consulted
            step_text = "Gathering recommendations from all agents..."
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            
            # Prepare queries for all agents
            # Each query is tailored to request a component for comprehensive plan
            # Queries reference original user request for context
            fitness_query = f"Based on this request: '{user_query}', provide a physical fitness component for a comprehensive wellness plan."
            nutrition_query = f"Based on this request: '{user_query}', provide a nutrition component for a comprehensive wellness plan."
            mental_query = f"Based on this request: '{user_query}', provide a mental wellness component for a comprehensive wellness plan."
            
            # Helper function to wrap agent calls with timeout and error handling
            # P0.3: Enhanced to track success/failure status
            # This wrapper ensures robust error handling and timeout protection
            async def call_with_timeout(agent_call, agent_name: str, timeout: int = 60):
                """
                Execute an agent call with timeout and error handling.
                
                This function wraps agent calls with timeout protection and error handling.
                It tracks success/failure status for degraded mode detection.
                
                Args:
                    agent_call: Coroutine for the agent call
                    agent_name: Name of the agent for logging (e.g., "Physical Fitness")
                    timeout: Timeout in seconds (default: 60)
                             Prevents hanging on slow agent responses
                
                Returns:
                    Dict with response, warnings, and success status:
                        {
                            "response": str,  # Agent response (empty if failed)
                            "warnings": List[str],  # Warnings from agent
                            "_success": bool,  # True if agent succeeded
                            "_agent_name": str,  # Agent name for tracking
                            "_error": str or None  # Error type if failed
                        }
                        
                Error Handling:
                    - Timeout errors: Returns timeout error message
                    - Other errors: Returns error message with exception details
                    - Invalid responses: Marked as failed with error message
                """
                try:
                    # Execute agent call with timeout protection
                    result = await asyncio.wait_for(agent_call, timeout=timeout)
                    # Mark as successful if we got a valid response
                    # Valid response must be dict with "response" key
                    if isinstance(result, dict) and result.get("response"):
                        result["_success"] = True  # Mark as successful
                        result["_agent_name"] = agent_name  # Track agent name
                    else:
                        # Invalid response - mark as failed
                        result = result or {}
                        result["_success"] = False
                        result["_agent_name"] = agent_name
                        result["response"] = f"{agent_name} agent returned invalid response"
                        result["warnings"] = result.get("warnings", []) + [f"{agent_name} agent returned invalid response"]
                    return result
                except AsyncTimeoutError:
                    # Timeout error - agent took too long
                    logger.error(f"{agent_name} agent timeout after {timeout} seconds")
                    return {
                        "response": "",  # Empty response
                        "warnings": [f"{agent_name} agent timeout"],  # Timeout warning
                        "_success": False,  # Mark as failed
                        "_agent_name": agent_name,
                        "_error": "timeout"  # Error type
                    }
                except Exception as e:
                    # Other errors - log and return error message
                    logger.error(f"{agent_name} agent error: {e}", exc_info=True)
                    return {
                        "response": "",  # Empty response
                        "warnings": [f"{agent_name} agent error: {str(e)}"],  # Error warning
                        "_success": False,  # Mark as failed
                        "_agent_name": agent_name,
                        "_error": str(e)  # Error details
                    }
            
            # Execute all three agents in parallel
            # Parallel execution improves performance significantly
            # Each agent call is wrapped with timeout and error handling
            fitness_task = call_with_timeout(
                self.physical_agent.recommend_exercise(fitness_query),  # Physical Fitness agent call
                "Physical Fitness"  # Agent name for logging
            )
            nutrition_task = call_with_timeout(
                self.nutrition_agent.recommend_meal(nutrition_query, image_base64),  # Nutrition agent call (with image if provided)
                "Nutrition"  # Agent name for logging
            )
            mental_task = call_with_timeout(
                self.mental_agent.recommend_practice(mental_query),  # Mental Fitness agent call
                "Mental Fitness"  # Agent name for logging
            )
            
            # Wait for all agents to complete (or timeout/error)
            # asyncio.gather() executes all tasks in parallel and waits for completion
            # return_exceptions=True ensures exceptions are returned as results, not raised
            fitness_result, nutrition_result, mental_result = await asyncio.gather(
                fitness_task,
                nutrition_task,
                mental_task,
                return_exceptions=True  # Return exceptions as results instead of raising
            )
            
            # Handle any exceptions that weren't caught by call_with_timeout
            # Some exceptions may slip through (e.g., from asyncio.gather with return_exceptions=True)
            # Convert exceptions to error result dictionaries for consistent handling
            if isinstance(fitness_result, Exception):
                # Physical Fitness agent raised exception
                logger.error(f"Physical Fitness agent raised exception: {fitness_result}", exc_info=True)
                fitness_result = {
                    "response": "",  # Empty response
                    "warnings": [f"Physical Fitness agent error: {str(fitness_result)}"],  # Error warning
                    "_success": False,  # Mark as failed
                    "_agent_name": "Physical Fitness",
                    "_error": str(fitness_result)  # Error details
                }
            if isinstance(nutrition_result, Exception):
                # Nutrition agent raised exception
                logger.error(f"Nutrition agent raised exception: {nutrition_result}", exc_info=True)
                nutrition_result = {
                    "response": "",  # Empty response
                    "warnings": [f"Nutrition agent error: {str(nutrition_result)}"],  # Error warning
                    "_success": False,  # Mark as failed
                    "_agent_name": "Nutrition",
                    "_error": str(nutrition_result)  # Error details
                }
            if isinstance(mental_result, Exception):
                # Mental Fitness agent raised exception
                logger.error(f"Mental Fitness agent raised exception: {mental_result}", exc_info=True)
                mental_result = {
                    "response": "",  # Empty response
                    "warnings": [f"Mental Fitness agent error: {str(mental_result)}"],  # Error warning
                    "_success": False,  # Mark as failed
                    "_agent_name": "Mental Fitness",
                    "_error": str(mental_result)  # Error details
                }
            
            # P0.3: Track which agents succeeded/failed
            # Agent status tracking for degraded mode detection and fallback info
            # Used to determine if plan should be created with partial components
            agent_status = {
                "fitness": {
                    "success": fitness_result.get("_success", False),  # True if Physical Fitness agent succeeded
                    "agent": fitness_result.get("_agent_name", "Physical Fitness"),  # Agent name
                    "error": fitness_result.get("_error")  # Error type if failed (None if succeeded)
                },
                "nutrition": {
                    "success": nutrition_result.get("_success", False),  # True if Nutrition agent succeeded
                    "agent": nutrition_result.get("_agent_name", "Nutrition"),  # Agent name
                    "error": nutrition_result.get("_error")  # Error type if failed (None if succeeded)
                },
                "mental": {
                    "success": mental_result.get("_success", False),  # True if Mental Fitness agent succeeded
                    "agent": mental_result.get("_agent_name", "Mental Fitness"),  # Agent name
                    "error": mental_result.get("_error")  # Error type if failed (None if succeeded)
                }
            }
            
            # Determine if degraded mode (some agents failed)
            # Degraded mode: Some agents failed, but plan can still be created with available components
            # degraded = True if any agent failed, False if all agents succeeded
            degraded = not all(status["success"] for status in agent_status.values())
            # List of failed agent names (e.g., ["fitness", "nutrition"])
            failed_agents = [name for name, status in agent_status.items() if not status["success"]]
            
            # Step 5: Synthesizing plan
            # Inform user that plan synthesis is in progress
            # Include degraded mode note if some agents failed
            step_text = "Synthesizing comprehensive plan..."
            if degraded:
                step_text += f" (Note: {len(failed_agents)} agent(s) unavailable - providing partial plan)"
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            
            # P0.3: Enhanced synthesis prompt that handles missing components
            # Extract agent responses (empty strings if agents failed)
            fitness_component = fitness_result.get("response", "").strip()  # Physical Fitness component (empty if failed)
            nutrition_component = nutrition_result.get("response", "").strip()  # Nutrition component (empty if failed)
            mental_component = mental_result.get("response", "").strip()  # Mental Wellness component (empty if failed)
            
            # Track missing components for degraded mode handling
            # Used to inform LLM about unavailable components
            missing_components = []
            if not fitness_component:
                missing_components.append("Physical Fitness")
            if not nutrition_component:
                missing_components.append("Nutrition")
            if not mental_component:
                missing_components.append("Mental Wellness")
            
            # Build synthesis prompt with available components
            # Prompt includes original user request and all available components
            # Missing components are marked as UNAVAILABLE
            # LLM is instructed to create best possible plan with available components
            synthesis_prompt = f"""You are synthesizing a comprehensive wellness plan from specialized agents.

User's Original Request: "{user_query}"

{f"Physical Fitness Component:\n{fitness_component}\n" if fitness_component else "Physical Fitness Component: [UNAVAILABLE - This component could not be generated due to service issues]\n"}
{f"Nutrition Component:\n{nutrition_component}\n" if nutrition_component else "Nutrition Component: [UNAVAILABLE - This component could not be generated due to service issues]\n"}
{f"Mental Wellness Component:\n{mental_component}\n" if mental_component else "Mental Wellness Component: [UNAVAILABLE - This component could not be generated due to service issues]\n"}

{"⚠️ NOTE: Some components are unavailable. Please create the best possible plan with the available components and clearly indicate what is missing." if missing_components else ""}

Synthesize the available components into a unified, cohesive wellness plan. Ensure:
1. All available domains work together harmoniously
2. The plan is realistic and achievable
3. There's consistency across available domains
4. The plan addresses the user's original request as comprehensively as possible with available information
5. Create a clear structure (weekly/daily breakdown if appropriate)
{f"6. Clearly note which components are missing and suggest the user try again later for a complete plan" if missing_components else ""}

Provide a well-organized plan that integrates all available aspects."""

            # P1.1: Use async call with timeout for synthesis
            # Synthesis LLM call with timeout protection
            async def invoke_synthesis():
                """
                Invoke LLM for plan synthesis with timeout protection.
                
                This function wraps the synthesis LLM call with timeout protection
                to prevent hanging on slow API responses.
                """
                try:
                    return await asyncio.wait_for(
                        self.llm.ainvoke(synthesis_prompt),  # LLM call for plan synthesis
                        timeout=getattr(self, 'llm_timeout', 60.0)  # Timeout in seconds
                    )
                except asyncio.TimeoutError:
                    timeout_msg = f"Synthesis call timed out after {getattr(self, 'llm_timeout', 60.0)} seconds"
                    logger.warning(timeout_msg)
                    if self.tracer:
                        self.tracer.log_timeout(getattr(self, 'llm_timeout', 60.0), "Synthesis call")
                    raise TimeoutError(f"Plan synthesis timed out after {getattr(self, 'llm_timeout', 60.0)} seconds. Please try again.")
            
            # Call synthesis LLM
            synthesis_response = await invoke_synthesis()
            
            # Step 6: Finalizing response
            # Inform user that response is being finalized
            step_text = "Finalizing response..."
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            
            # Collect all warnings from all agents
            # Warnings include safety warnings, dietary restrictions, and errors
            all_warnings = []
            if fitness_result.get("warnings"):
                all_warnings.extend(fitness_result["warnings"])  # Physical Fitness warnings (safety, conflicts)
            if nutrition_result.get("warnings"):
                all_warnings.extend(nutrition_result["warnings"])  # Nutrition warnings (dietary restrictions)
            if mental_result.get("warnings"):
                all_warnings.extend(mental_result["warnings"])  # Mental Fitness warnings (if any)
            
            # P0.3: Add degraded mode warning if applicable
            # Inform user about partial plan availability
            if degraded:
                degraded_warning = f"Partial plan generated: {', '.join(failed_agents)} component(s) unavailable. Please try again later for a complete plan."
                all_warnings.append(degraded_warning)
            
            # Yield final result with synthesized plan and metadata
            yield {
                "type": "response",
                "data": {
                    "response": synthesis_response.content,  # Synthesized holistic plan
                    "warnings": all_warnings if all_warnings else None,  # Combined warnings from all agents
                    "nutrition_analysis": nutrition_result.get("nutrition_analysis"),  # Nutrition analysis (if image provided)
                    "routed_to": "holistic",  # Routing information
                    "steps": steps,  # Step updates for UI
                    "degraded": degraded,  # P0.3: Indicate if degraded mode was used
                    "fallback_info": {  # P0.3: Track which agents/models succeeded/failed
                        "agent_status": agent_status,  # Detailed agent status (success, error)
                        "failed_agents": failed_agents,  # List of failed agent names
                        "available_components": [name for name, status in agent_status.items() if status["success"]]  # List of successful agent names
                    },
                    "components": {  # Individual agent responses (for transparency)
                        "fitness": fitness_result.get("response", ""),  # Physical Fitness component (empty if failed)
                        "nutrition": nutrition_result.get("response", ""),  # Nutrition component (empty if failed)
                        "mental": mental_result.get("response", "")  # Mental Wellness component (empty if failed)
                    }
                }
            }
            
        except Exception as e:
            step_text = "Error occurred during holistic planning"
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            yield {
                "type": "response",
                "data": {
                    "response": f"Error creating holistic plan: {str(e)}",
                    "warnings": [f"Holistic planning error: {str(e)}"],
                    "routed_to": "holistic",
                    "steps": steps
                }
            }
    
    async def create_holistic_plan(self, user_query: str, image_base64: Optional[str] = None, steps: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Create a holistic plan combining all three domains (non-streaming version).
        
        This is a convenience wrapper around create_holistic_plan_stream() that collects
        all step updates and returns only the final result. Useful for backward compatibility
        or when streaming is not needed.
        
        Args:
            user_query: User's query requesting comprehensive wellness plan
            image_base64: Optional base64-encoded image for nutrition analysis
            steps: Optional list of steps already tracked (will be extended)
            
        Returns:
            Dict[str, Any]: Final result dictionary:
                {
                    "response": str,  # Synthesized holistic plan
                    "warnings": List[str] or None,  # Combined warnings from all agents
                    "routed_to": "holistic",  # Routing information
                    "steps": List[str],  # List of step updates
                    "degraded": bool,  # True if some agents failed
                    "fallback_info": Dict,  # Agent status information
                    "components": Dict,  # Individual agent responses
                    "nutrition_analysis": Dict or None  # Nutrition analysis (if available)
                }
                
        Note:
            - Non-streaming version for backward compatibility
            - Collects all step updates and returns final result only
            - Returns error dict if no response received
        """
        final_result = None
        # Iterate through streaming results and collect final response
        async for item in self.create_holistic_plan_stream(user_query, image_base64, steps):
            if item["type"] == "response":
                final_result = item["data"]
        # Return final result or error dict if no response received
        return final_result or {
            "response": "Error: No response received",
            "warnings": ["Holistic planning error: No response"],
            "routed_to": "holistic",
            "steps": steps or []
        }

