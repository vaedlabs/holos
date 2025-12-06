"""
Physical Fitness Agent - Specialized agent for workout planning and exercise recommendations
"""

from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent_tracer import AgentTracer
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.services.medical_service import check_user_exercise_conflicts
from app.agents.reasoning_patterns import ExerciseSafetyReasoningPattern


class PhysicalFitnessAgent(BaseAgent):
    """Physical Fitness Agent specialized for exercise recommendations and workout planning"""
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gpt-4.1",
        shared_context: Optional[Dict[str, Optional[Dict]]] = None,
        tracer: Optional["AgentTracer"] = None
    ):
        super().__init__(user_id, db, model_name, shared_context=shared_context, tracer=tracer)
        
        # Initialize reasoning pattern for exercise safety
        self.exercise_safety_pattern = ExerciseSafetyReasoningPattern(
            extract_exercises_fn=self._extract_potential_exercises,
            check_safety_fn=self.check_exercise_safety
        )
    
    def _get_agent_type(self) -> str:
        """Get agent type identifier"""
        return "physical_fitness"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for physical fitness agent.
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
        from app.agents.prompts.fitness_prompt import get_fitness_prompt
        return get_fitness_prompt()
    
    def _get_personality_traits(self) -> str:
        """Add physical fitness-specific motivational personality traits"""
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
        Recommend exercises based on user query.
        Uses reasoning patterns to check for potential conflicts BEFORE generating response.
        Returns response with medical conflict warnings.
        """
        # Get context for reasoning pattern
        context = {
            "medical_history": self._shared_context.get("medical_history") if self._shared_context else None,
            "user_preferences": self._shared_context.get("user_preferences") if self._shared_context else None
        }
        
        # STEP 1: Pre-check using reasoning pattern
        pre_check_results = await self.exercise_safety_pattern.pre_check(user_query, context)
        
        # STEP 2: Enhance query with conflict context using reasoning pattern
        enhanced_query = await self.exercise_safety_pattern.reason(user_query, context, pre_check_results)
        
        # STEP 3: Get agent response (with conflict context if applicable)
        # Store user_query for conflict checking in tool execution
        self._current_user_query = user_query
        self._current_context = context
        response = await self.run(enhanced_query)
        
        # STEP 4: Post-validate response using reasoning pattern
        validation_results = await self.exercise_safety_pattern.post_validate(response, user_query, context)
        warnings = validation_results.get("warnings")
        
        # Check if we have block-level conflicts
        self._has_block_conflict = False
        if warnings:
            for warning in warnings:
                if isinstance(warning, str) and "BLOCKED:" in warning.upper():
                    self._has_block_conflict = True
                    break
        
        return {
            "response": response,
            "warnings": warnings if warnings else None
        }
    
    async def run(self, user_input: str) -> str:
        """
        Override run method to intercept create_workout_log tool calls
        and prevent logging if there are block-level conflicts.
        """
        from langchain_core.messages import ToolMessage
        
        # Call parent run method but intercept tool calls
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
            
            # Build enhanced system message with full context to reduce tool calls
            enhanced_system_message = self._build_enhanced_system_prompt()
            
            # Build messages with enhanced system prompt
            messages = [
                SystemMessage(content=enhanced_system_message),
                HumanMessage(content=user_input)
            ]
            
            max_iterations = 5
            iteration = 0
            
            while iteration < max_iterations:
                iteration += 1
                
                # Get LLM response with tools
                response = await self.llm_with_tools.ainvoke(messages)
                messages.append(response)
                
                # Check if LLM wants to call tools
                if hasattr(response, 'tool_calls') and response.tool_calls and len(response.tool_calls) > 0:
                    # Execute tool calls
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get("name", "")
                        tool_input = tool_call.get("args", {})
                        tool_call_id = tool_call.get("id", "")
                        
                        # Intercept create_workout_log if there are block conflicts
                        if tool_name == "create_workout_log":
                            # Get the exercises from tool input
                            exercises_text = tool_input.get("exercises", "")
                            exercise_type = tool_input.get("exercise_type", "")
                            
                            # Check for conflicts in the exercises
                            has_block = False
                            if exercises_text:
                                # Check each exercise mentioned in the exercises text
                                exercises_lower = exercises_text.lower()
                                # Use the same exercise keywords from post_validate
                                exercise_keywords = [
                                    "squat", "squats", "deadlift", "deadlifts", "dead lift", "dead lifts",
                                    "lunge", "lunges", "running", "run", "jumping", "jump", "sprinting", "sprint",
                                    "triathlon", "marathon", "ironman", "half ironman", "ultramarathon",
                                    "hiit", "high intensity", "heavy lifting", "heavy", "weights",
                                    "pull-up", "pull-ups", "push-up", "push-ups", "overhead press", "shoulder press",
                                    "burpees", "burpee", "circuit training", "endurance", "swimming", "cycling", "biking"
                                ]
                                
                                for keyword in exercise_keywords:
                                    if keyword in exercises_lower:
                                        conflict_check = self.check_exercise_safety(keyword)
                                        if conflict_check.get("has_conflict") and conflict_check.get("severity") == "block":
                                            has_block = True
                                            break
                            
                            if has_block:
                                # Prevent logging - return error message
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
                                            
                                            if self.tracer:
                                                if self.tracer.current_trace and self.tracer.current_trace.get("tools_called"):
                                                    self.tracer.current_trace["tools_called"][-1]["output"] = str(tool_result)[:500]
                                            
                                            break
                                        except Exception as e:
                                            tool_result = f"Error executing {tool_name}: {str(e)}"
                                            if self.tracer:
                                                self.tracer.log_warning(f"Tool {tool_name} error: {str(e)}")
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
                                        
                                        if self.tracer:
                                            if self.tracer.current_trace and self.tracer.current_trace.get("tools_called"):
                                                self.tracer.current_trace["tools_called"][-1]["output"] = str(tool_result)[:500]
                                        
                                        break
                                    except Exception as e:
                                        tool_result = f"Error executing {tool_name}: {str(e)}"
                                        if self.tracer:
                                            self.tracer.log_warning(f"Tool {tool_name} error: {str(e)}")
                                        break
                        
                        if tool_result is None:
                            tool_result = f"Tool {tool_name} not found"
                            if self.tracer:
                                self.tracer.log_warning(f"Tool {tool_name} not found")
                        
                        # Add tool result as ToolMessage
                        messages.append(ToolMessage(
                            content=str(tool_result),
                            tool_call_id=tool_call_id
                        ))
                else:
                    # No tool calls, return the final response
                    return response.content if hasattr(response, 'content') else str(response)
            
            # If we've reached max iterations, return the last response
            last_response = messages[-1]
            return last_response.content if hasattr(last_response, 'content') else str(last_response)
            
        except Exception as e:
            # Fallback to parent implementation on error
            return await super().run(user_input)
    
    def _extract_potential_exercises(self, query: str) -> list:
        """Extract potential exercise mentions from user query"""
        query_lower = query.lower()
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
        
        found_exercises = []
        for keyword in exercise_keywords:
            if keyword in query_lower:
                found_exercises.append(keyword)
        
        return found_exercises
    
    def _check_response_for_conflicts(self, response: str) -> list:
        """Check agent response for exercise mentions and validate against medical history"""
        warnings = []
        checked_exercises = set()
        
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
        """
        query = f"Create a {duration_minutes}-minute workout plan"
        if exercise_type:
            query += f" focused on {exercise_type}"
        query += ". Make sure to check my medical history first and create a plan that's safe for me."
        
        result = await self.recommend_exercise(query)
        return result["response"]

