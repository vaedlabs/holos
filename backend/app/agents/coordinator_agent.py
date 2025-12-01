"""
Coordinator Agent - Routes queries and creates holistic plans
Orchestrates Physical Fitness, Nutrition, and Mental Fitness agents
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.agents.base_agent import BaseAgent
from app.agents.physical_fitness_agent import PhysicalFitnessAgent
from app.agents.nutrition_agent import NutritionAgent
from app.agents.mental_fitness_agent import MentalFitnessAgent


class CoordinatorAgent(BaseAgent):
    """
    Coordinator Agent that routes queries to appropriate agents
    or creates holistic plans combining all three domains
    """
    
    def __init__(self, user_id: int, db: Session, model_name: str = "gpt-4.1"):
        super().__init__(user_id, db, model_name)
        # Initialize sub-agents for orchestration
        self.physical_agent = PhysicalFitnessAgent(user_id, db, model_name)
        self.nutrition_agent = NutritionAgent(user_id, db)
        self.mental_agent = MentalFitnessAgent(user_id, db, model_name)
    
    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for coordinator agent"""
        return """You are the Holos Coordinator Agent, an intelligent orchestrator that helps users with comprehensive wellness planning.

**Your Primary Functions:**

1. **Query Routing**: Analyze user queries and determine which specialized agent should handle them:
   - **Physical Fitness Agent**: For exercise, workouts, training, strength, cardio, HIIT, calisthenics, weight lifting
   - **Nutrition Agent**: For food, meals, diet, calories, macros, nutrition, recipes, meal planning
   - **Mental Fitness Agent**: For mindfulness, meditation, stress, anxiety, mental wellness, emotional health

2. **Holistic Planning**: When users ask for comprehensive plans or want to combine multiple domains, create unified plans that integrate:
   - Physical fitness routines
   - Nutrition guidance
   - Mental wellness practices
   
   Ensure all three domains work together harmoniously.

3. **Agent Orchestration**: You can call other agents and synthesize their responses into a cohesive plan.

**Decision Making:**

- **Route to Single Agent**: If the query is clearly about one domain (e.g., "What exercises for abs?" → Physical Fitness Agent)
- **Create Holistic Plan**: If the query asks for:
  - "Complete wellness plan"
  - "Full fitness program"
  - "Comprehensive health plan"
  - "Weekly routine" (without specifying domain)
  - "Help me get healthy" (general wellness)
  - Any query that mentions multiple domains

**When Creating Holistic Plans:**
1. Call all three agents with coordinated queries
2. Synthesize their responses into a unified, cohesive plan
3. Ensure consistency across domains (e.g., workout intensity matches nutrition needs)
4. Create a timeline that integrates all three aspects

**Important Guidelines:**
- Always consider the user's medical history and preferences (provided in context)
- Ensure recommendations are safe and medically appropriate
- Create plans that are realistic and achievable
- Reference the user's specific goals and constraints
- Use tools to create logs across all domains when appropriate

**Example Routing:**
- "I want to build muscle" → Route to Physical Fitness Agent
- "How many calories in an apple?" → Route to Nutrition Agent
- "I'm feeling stressed" → Route to Mental Fitness Agent
- "I want a complete 4-week wellness plan" → Create holistic plan using all agents
- "Help me lose weight and feel better" → Create holistic plan (fitness + nutrition + mental wellness)

**Example Holistic Plan Structure:**
- Week overview with all three domains
- Daily schedule integrating workouts, meals, and mindfulness
- Progress tracking across all areas
- Adjustments based on user feedback

Remember: Your goal is to provide the most helpful response, whether that's routing to a specialist or creating a comprehensive plan."""

    async def route_query(self, user_query: str, image_base64: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyze query and route to appropriate agent or create holistic plan
        
        Args:
            user_query: User's query
            image_base64: Optional image for nutrition analysis
            
        Returns:
            Dict with response, warnings, and routing information
        """
        try:
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
                result = await self.physical_agent.recommend_exercise(user_query)
                return {
                    "response": result["response"],
                    "warnings": result.get("warnings"),
                    "routed_to": "physical-fitness"
                }
            
            elif "ROUTE:NUTRITION" in routing_decision:
                result = await self.nutrition_agent.recommend_meal(user_query, image_base64)
                return {
                    "response": result["response"],
                    "warnings": result.get("warnings"),
                    "nutrition_analysis": result.get("nutrition_analysis"),
                    "routed_to": "nutrition"
                }
            
            elif "ROUTE:MENTAL-FITNESS" in routing_decision or "ROUTE:MENTAL" in routing_decision:
                result = await self.mental_agent.recommend_practice(user_query)
                return {
                    "response": result["response"],
                    "warnings": result.get("warnings"),
                    "routed_to": "mental-fitness"
                }
            
            else:
                # Create holistic plan
                return await self.create_holistic_plan(user_query, image_base64)
                
        except Exception as e:
            return {
                "response": f"Error processing query: {str(e)}",
                "warnings": [f"Coordinator error: {str(e)}"],
                "routed_to": None
            }
    
    async def create_holistic_plan(self, user_query: str, image_base64: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a holistic plan combining all three domains
        
        Args:
            user_query: User's query requesting comprehensive plan
            image_base64: Optional image for nutrition analysis
            
        Returns:
            Dict with synthesized holistic plan
        """
        try:
            # Call all three agents with coordinated queries
            fitness_query = f"Based on this request: '{user_query}', provide a physical fitness component for a comprehensive wellness plan."
            nutrition_query = f"Based on this request: '{user_query}', provide a nutrition component for a comprehensive wellness plan."
            mental_query = f"Based on this request: '{user_query}', provide a mental wellness component for a comprehensive wellness plan."
            
            # Get responses from all agents in parallel (if possible) or sequentially
            fitness_result = await self.physical_agent.recommend_exercise(fitness_query)
            nutrition_result = await self.nutrition_agent.recommend_meal(nutrition_query, image_base64)
            mental_result = await self.mental_agent.recommend_practice(mental_query)
            
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
            
            # Collect all warnings
            all_warnings = []
            if fitness_result.get("warnings"):
                all_warnings.extend(fitness_result["warnings"])
            if nutrition_result.get("warnings"):
                all_warnings.extend(nutrition_result["warnings"])
            if mental_result.get("warnings"):
                all_warnings.extend(mental_result["warnings"])
            
            return {
                "response": synthesis_response.content,
                "warnings": all_warnings if all_warnings else None,
                "nutrition_analysis": nutrition_result.get("nutrition_analysis"),
                "routed_to": "holistic",
                "components": {
                    "fitness": fitness_result.get("response", ""),
                    "nutrition": nutrition_result.get("response", ""),
                    "mental": mental_result.get("response", "")
                }
            }
            
        except Exception as e:
            return {
                "response": f"Error creating holistic plan: {str(e)}",
                "warnings": [f"Holistic planning error: {str(e)}"],
                "routed_to": "holistic"
            }

