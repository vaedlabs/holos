"""
Coordinator Agent - Routes queries and creates holistic plans
Orchestrates Physical Fitness, Nutrition, and Mental Fitness agents
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
    Coordinator Agent that routes queries to appropriate agents
    or creates holistic plans combining all three domains
    """
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gpt-4.1",
        tracer: Optional[Any] = None
    ):
        # Fetch shared context once for all sub-agents
        shared_context = context_manager.get_user_context(user_id, db)
        
        # Initialize base agent with shared context and tracer
        super().__init__(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
        
        # Initialize sub-agents for orchestration, passing shared context and tracer
        # Note: Sub-agents will get their own tracers when called via router endpoints
        # But if coordinator calls them directly, they can use coordinator's tracer
        self.physical_agent = PhysicalFitnessAgent(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
        self.nutrition_agent = NutritionAgent(user_id, db, shared_context=shared_context, tracer=tracer)
        self.mental_agent = MentalFitnessAgent(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
    
    def _get_agent_type(self) -> str:
        """Get agent type identifier"""
        return "coordinator"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for coordinator agent.
        Checks cache first, then builds if not cached.
        """
        # Check cache first
        agent_type = self._get_agent_type()
        from app.services.prompt_cache import prompt_cache
        cached_prompt = prompt_cache.get_static_prompt(agent_type)
        if cached_prompt:
            return cached_prompt
        
        # Not cached, build it
        # Use prompt component system
        from app.agents.prompts.coordinator_prompt import get_coordinator_prompt
        return get_coordinator_prompt()
    
    def _get_personality_traits(self) -> str:
        """Add coordinator-specific personality traits"""
        return """- **Moderate Personality**: Friendly and warm, but balanced - not overly enthusiastic or too formal
- **Natural Language**: Use conversational patterns like "Hey!", "Got it!", "Let me figure out the best way to help you"
- **Occasional Encouragement**: Sprinkle in supportive phrases like "That's a great goal!", "I'm here to help!", "We'll figure this out together"
- **Transparency**: When routing or coordinating, explain what you're doing naturally: "Let me connect you with our nutrition expert", "I'm putting together a complete plan for you"
- **Collaborative Tone**: Use "we" and "us" - "Let's get you set up", "We can create a plan that works for you"
- **Acknowledge Complexity**: When creating holistic plans, acknowledge it's comprehensive: "This is going to be awesome - let me bring everything together for you"
- **Match User Energy**: If they're excited, match that energy; if they're calm, be measured and supportive"""

    async def route_query_stream(self, user_query: str, image_base64: Optional[str] = None):
        """
        Analyze query and route to appropriate agent or create holistic plan
        Yields step updates as they happen, then yields final result
        
        Args:
            user_query: User's query
            image_base64: Optional image for nutrition analysis
            
        Yields:
            First: Step updates as dict {"type": "step", "data": "step text"}
            Finally: Final result as dict {"type": "response", "data": {...}}
        """
        steps = []
        try:
            # Step 1: Analyzing query
            step_text = "Analyzing your query..."
            steps.append(step_text)
            if self.tracer:
                self.tracer.log_step(step_text)
            yield {"type": "step", "data": step_text}
            
            # Use LLM to determine routing strategy
            routing_prompt = f"""Analyze this user query and determine the best approach:

User Query: "{user_query}"

Determine if this query should be:
1. Routed to a single agent (Physical Fitness, Nutrition, or Mental Fitness)
2. Handled as a holistic plan requiring all three agents

Respond with ONLY one of these formats:
- "ROUTE:physical-fitness" - Route to Physical Fitness Agent
- "ROUTE:nutrition" - Route to Nutrition Agent  
- "ROUTE:mental-fitness" - Route to Mental Fitness Agent
- "HOLISTIC" - Create a holistic plan using all three agents

Your response:"""

            routing_response = self.llm.invoke(routing_prompt)
            routing_decision = routing_response.content.strip().upper()
            
            # Route to appropriate agent
            if "ROUTE:PHYSICAL-FITNESS" in routing_decision or "ROUTE:PHYSICAL" in routing_decision:
                step_text = "Routing to Physical Fitness Agent..."
                steps.append(step_text)
                if self.tracer:
                    self.tracer.log_step(step_text)
                yield {"type": "step", "data": step_text}
                
                result = await self.physical_agent.recommend_exercise(user_query)
                
                step_text = "Synthesizing response..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                yield {
                    "type": "response",
                    "data": {
                        "response": result["response"],
                        "warnings": result.get("warnings"),
                        "routed_to": "physical-fitness",
                        "steps": steps
                    }
                }
            
            elif "ROUTE:NUTRITION" in routing_decision:
                step_text = "Routing to Nutrition Agent..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                result = await self.nutrition_agent.recommend_meal(user_query, image_base64)
                
                step_text = "Synthesizing response..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                yield {
                    "type": "response",
                    "data": {
                        "response": result["response"],
                        "warnings": result.get("warnings"),
                        "nutrition_analysis": result.get("nutrition_analysis"),
                        "routed_to": "nutrition",
                        "steps": steps
                    }
                }
            
            elif "ROUTE:MENTAL-FITNESS" in routing_decision or "ROUTE:MENTAL" in routing_decision:
                step_text = "Routing to Mental Fitness Agent..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                result = await self.mental_agent.recommend_practice(user_query)
                
                step_text = "Synthesizing response..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
                yield {
                    "type": "response",
                    "data": {
                        "response": result["response"],
                        "warnings": result.get("warnings"),
                        "routed_to": "mental-fitness",
                        "steps": steps
                    }
                }
            
            else:
                # Create holistic plan
                step_text = "Creating holistic plan..."
                steps.append(step_text)
                yield {"type": "step", "data": step_text}
                
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
        Analyze query and route to appropriate agent or create holistic plan
        Non-streaming version for backward compatibility
        
        Args:
            user_query: User's query
            image_base64: Optional image for nutrition analysis
            
        Returns:
            Dict with response, warnings, routing information, and steps
        """
        final_result = None
        async for item in self.route_query_stream(user_query, image_base64):
            if item["type"] == "response":
                final_result = item["data"]
        return final_result or {
            "response": "Error: No response received",
            "warnings": ["Coordinator error: No response"],
            "routed_to": None,
            "steps": []
        }
    
    async def create_holistic_plan_stream(self, user_query: str, image_base64: Optional[str] = None, steps: Optional[List[str]] = None):
        """
        Create a holistic plan combining all three domains (streaming version)
        Yields step updates as they happen, then yields final result
        
        Args:
            user_query: User's query requesting comprehensive plan
            image_base64: Optional image for nutrition analysis
            steps: Optional list of steps already tracked (will be extended)
            
        Yields:
            Step updates and final response
        """
        if steps is None:
            steps = []
        
        try:
            # Step 2: Gathering recommendations from all agents in parallel
            step_text = "Gathering recommendations from all agents..."
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            
            # Prepare queries for all agents
            fitness_query = f"Based on this request: '{user_query}', provide a physical fitness component for a comprehensive wellness plan."
            nutrition_query = f"Based on this request: '{user_query}', provide a nutrition component for a comprehensive wellness plan."
            mental_query = f"Based on this request: '{user_query}', provide a mental wellness component for a comprehensive wellness plan."
            
            # Helper function to wrap agent calls with timeout and error handling
            async def call_with_timeout(agent_call, agent_name: str, timeout: int = 60):
                """
                Execute an agent call with timeout and error handling.
                
                Args:
                    agent_call: Coroutine for the agent call
                    agent_name: Name of the agent for logging
                    timeout: Timeout in seconds (default: 60)
                
                Returns:
                    Dict with response and warnings, or error response on failure
                """
                try:
                    return await asyncio.wait_for(agent_call, timeout=timeout)
                except AsyncTimeoutError:
                    logger.error(f"{agent_name} agent timeout after {timeout} seconds")
                    return {
                        "response": f"{agent_name} agent timeout - please try again",
                        "warnings": [f"{agent_name} agent timeout"]
                    }
                except Exception as e:
                    logger.error(f"{agent_name} agent error: {e}", exc_info=True)
                    return {
                        "response": f"{agent_name} agent error: {str(e)}",
                        "warnings": [f"{agent_name} agent error: {str(e)}"]
                    }
            
            # Execute all three agents in parallel
            fitness_task = call_with_timeout(
                self.physical_agent.recommend_exercise(fitness_query),
                "Physical Fitness"
            )
            nutrition_task = call_with_timeout(
                self.nutrition_agent.recommend_meal(nutrition_query, image_base64),
                "Nutrition"
            )
            mental_task = call_with_timeout(
                self.mental_agent.recommend_practice(mental_query),
                "Mental Fitness"
            )
            
            # Wait for all agents to complete (or timeout/error)
            fitness_result, nutrition_result, mental_result = await asyncio.gather(
                fitness_task,
                nutrition_task,
                mental_task,
                return_exceptions=True
            )
            
            # Handle any exceptions that weren't caught by call_with_timeout
            if isinstance(fitness_result, Exception):
                logger.error(f"Physical Fitness agent raised exception: {fitness_result}", exc_info=True)
                fitness_result = {
                    "response": "Physical Fitness agent error",
                    "warnings": [f"Physical Fitness agent error: {str(fitness_result)}"]
                }
            if isinstance(nutrition_result, Exception):
                logger.error(f"Nutrition agent raised exception: {nutrition_result}", exc_info=True)
                nutrition_result = {
                    "response": "Nutrition agent error",
                    "warnings": [f"Nutrition agent error: {str(nutrition_result)}"]
                }
            if isinstance(mental_result, Exception):
                logger.error(f"Mental Fitness agent raised exception: {mental_result}", exc_info=True)
                mental_result = {
                    "response": "Mental Fitness agent error",
                    "warnings": [f"Mental Fitness agent error: {str(mental_result)}"]
                }
            
            # Step 5: Synthesizing plan
            step_text = "Synthesizing comprehensive plan..."
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            
            # Synthesize responses into unified plan
            synthesis_prompt = f"""You are synthesizing a comprehensive wellness plan from three specialized agents.

User's Original Request: "{user_query}"

Physical Fitness Component:
{fitness_result.get("response", "")}

Nutrition Component:
{nutrition_result.get("response", "")}

Mental Wellness Component:
{mental_result.get("response", "")}

Synthesize these three components into a unified, cohesive wellness plan. Ensure:
1. All three domains work together harmoniously
2. The plan is realistic and achievable
3. There's consistency across domains (e.g., workout intensity matches nutrition needs)
4. The plan addresses the user's original request comprehensively
5. Create a clear structure (weekly/daily breakdown if appropriate)

Provide a well-organized, comprehensive plan that integrates all three aspects."""

            synthesis_response = self.llm.invoke(synthesis_prompt)
            
            # Step 6: Finalizing response
            step_text = "Finalizing response..."
            steps.append(step_text)
            yield {"type": "step", "data": step_text}
            
            # Collect all warnings
            all_warnings = []
            if fitness_result.get("warnings"):
                all_warnings.extend(fitness_result["warnings"])
            if nutrition_result.get("warnings"):
                all_warnings.extend(nutrition_result["warnings"])
            if mental_result.get("warnings"):
                all_warnings.extend(mental_result["warnings"])
            
            yield {
                "type": "response",
                "data": {
                    "response": synthesis_response.content,
                    "warnings": all_warnings if all_warnings else None,
                    "nutrition_analysis": nutrition_result.get("nutrition_analysis"),
                    "routed_to": "holistic",
                    "steps": steps,
                    "components": {
                        "fitness": fitness_result.get("response", ""),
                        "nutrition": nutrition_result.get("response", ""),
                        "mental": mental_result.get("response", "")
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
        Create a holistic plan combining all three domains
        Non-streaming version for backward compatibility
        
        Args:
            user_query: User's query requesting comprehensive plan
            image_base64: Optional image for nutrition analysis
            steps: Optional list of steps already tracked (will be extended)
            
        Returns:
            Dict with synthesized holistic plan and steps
        """
        final_result = None
        async for item in self.create_holistic_plan_stream(user_query, image_base64, steps):
            if item["type"] == "response":
                final_result = item["data"]
        return final_result or {
            "response": "Error: No response received",
            "warnings": ["Holistic planning error: No response"],
            "routed_to": "holistic",
            "steps": steps or []
        }

