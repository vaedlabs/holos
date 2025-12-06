"""
Nutrition Agent - Specialized agent for nutrition, meal planning, and image-based food analysis
Uses Google Gemini for vision capabilities
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
# Using google.generativeai directly (not LangChain wrapper) for better compatibility
import google.generativeai as genai
from langchain_core.tools import BaseTool
import os
import json
import base64
from io import BytesIO
from PIL import Image

from app.agents.base_agent import (
    GetMedicalHistoryTool,
    GetUserPreferencesTool,
    CreateNutritionLogTool,
    WebSearchTool
)
from app.services.medical_service import get_medical_history
from app.services.dietary_service import check_dietary_conflicts
from app.models.user_preferences import UserPreferences


class NutritionAgent:
    """Nutrition Agent specialized for meal planning, dietary advice, and image-based calorie tracking using Gemini Vision"""
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gemini-2.0-flash",
        shared_context: Optional[Dict[str, Optional[Dict]]] = None,
        tracer: Optional[Any] = None
    ):
        self.user_id = user_id
        self.db = db
        
        # Store shared context if provided (from ContextManager)
        self._shared_context = shared_context
        
        # Store tracer for observability (optional)
        self.tracer = tracer
        
        # Get Gemini API key from environment
        api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_GEMINI_API_KEY is not set in environment variables. "
                "Please set it in your .env file or environment."
            )
        
        # Configure Gemini API (using direct SDK, not LangChain wrapper)
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.model_name = model_name
        
        # Initialize tools (for manual tool calling)
        self.tools = {
            "get_medical_history": GetMedicalHistoryTool(user_id=user_id, db=db),
            "get_user_preferences": GetUserPreferencesTool(user_id=user_id, db=db),
            "create_nutrition_log": CreateNutritionLogTool(user_id=user_id, db=db),
            "web_search": WebSearchTool(),
        }
        
        # Create system message
        self.system_message = self._get_system_prompt()
        
        # Cache user context summary
        self._user_context_summary = None
        self._context_fetched = False
    
    def _get_agent_type(self) -> str:
        """Get agent type identifier"""
        return "nutrition"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for nutrition agent.
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
        from app.agents.prompts.nutrition_prompt import get_nutrition_prompt
        return get_nutrition_prompt()

    def _get_user_context_summary(self) -> str:
        """Get minimal summary of user context for nutrition agent"""
        if self._context_fetched and self._user_context_summary:
            return self._user_context_summary
        
        summary_parts = []
        
        # Use shared context if provided (from ContextManager)
        if self._shared_context:
            # Get dietary restrictions from shared context
            preferences = self._shared_context.get("preferences")
            if preferences:
                if preferences.get("dietary_restrictions"):
                    restrictions = preferences["dietary_restrictions"].strip()
                    if restrictions:
                        if len(restrictions) > 50:
                            restrictions = restrictions[:47] + "..."
                        summary_parts.append(f"Dietary: {restrictions}")
                
                if preferences.get("location"):
                    location = preferences["location"].strip()
                    if location:
                        if len(location) > 30:
                            location = location[:27] + "..."
                        summary_parts.append(f"Location: {location}")
            
            # Get medical history from shared context
            medical_history = self._shared_context.get("medical_history")
            if medical_history and medical_history.get("conditions"):
                conditions = medical_history["conditions"].strip()
                if conditions:
                    if len(conditions) > 40:
                        conditions = conditions[:37] + "..."
                    summary_parts.append(f"Medical: {conditions}")
            
            self._user_context_summary = " | ".join(summary_parts) if summary_parts else ""
            self._context_fetched = True
            return self._user_context_summary
        
        # Fallback: Fetch context independently (for backward compatibility)
        # Get dietary restrictions (important for nutrition)
        preferences = self.db.query(UserPreferences).filter(
            UserPreferences.user_id == self.user_id
        ).first()
        
        if preferences:
            if preferences.dietary_restrictions:
                restrictions = preferences.dietary_restrictions.strip()
                if len(restrictions) > 50:
                    restrictions = restrictions[:47] + "..."
                summary_parts.append(f"Dietary: {restrictions}")
            
            if preferences.location:
                location = preferences.location.strip()
                if len(location) > 30:
                    location = location[:27] + "..."
                summary_parts.append(f"Location: {location}")
        
        # Get medical history for dietary considerations
        medical_history = get_medical_history(self.user_id, self.db)
        if medical_history and medical_history.conditions:
            conditions = medical_history.conditions.strip()
            if len(conditions) > 40:
                conditions = conditions[:37] + "..."
            summary_parts.append(f"Medical: {conditions}")
        
        self._user_context_summary = " | ".join(summary_parts) if summary_parts else ""
        self._context_fetched = True
        return self._user_context_summary
    
    def _build_enhanced_system_prompt(self) -> str:
        """
        Build system prompt with enhanced context to reduce tool calls.
        
        Strategy: Include full context in system prompt upfront to reduce tool calls.
        This offsets the cost of larger prompts by reducing tool call tokens.
        
        Returns:
            Enhanced system prompt with full context included
        """
        base_prompt = self.system_message
        
        # Use shared context if available (from ContextManager - already cached)
        if self._shared_context:
            context_parts = []
            
            # Include full medical history if available
            medical_history = self._shared_context.get("medical_history")
            if medical_history:
                medical_parts = []
                if medical_history.get("conditions"):
                    medical_parts.append(f"Medical Conditions: {medical_history['conditions']}")
                if medical_history.get("limitations"):
                    medical_parts.append(f"Physical Limitations: {medical_history['limitations']}")
                if medical_history.get("medications"):
                    medical_parts.append(f"Medications: {medical_history['medications']}")
                if medical_history.get("notes"):
                    medical_parts.append(f"Medical Notes: {medical_history['notes']}")
                
                if medical_parts:
                    context_parts.append("## Medical History\n" + "\n".join(medical_parts))
            
            # Include full user preferences if available (especially important for nutrition)
            preferences = self._shared_context.get("user_preferences")
            if preferences:
                pref_parts = []
                if preferences.get("goals"):
                    pref_parts.append(f"Fitness Goals: {preferences['goals']}")
                if preferences.get("exercise_types"):
                    pref_parts.append(f"Preferred Exercise Types: {preferences['exercise_types']}")
                if preferences.get("dietary_restrictions"):
                    pref_parts.append(f"Dietary Restrictions: {preferences['dietary_restrictions']}")
                if preferences.get("activity_level"):
                    pref_parts.append(f"Activity Level: {preferences['activity_level']}")
                if preferences.get("lifestyle"):
                    pref_parts.append(f"Lifestyle: {preferences['lifestyle']}")
                if preferences.get("age"):
                    pref_parts.append(f"Age: {preferences['age']}")
                if preferences.get("gender"):
                    pref_parts.append(f"Gender: {preferences['gender']}")
                if preferences.get("location"):
                    pref_parts.append(f"Location: {preferences['location']}")
                
                if pref_parts:
                    context_parts.append("## User Preferences\n" + "\n".join(pref_parts))
            
            # Add context section if we have any context
            if context_parts:
                context_section = "\n\n".join(context_parts)
                base_prompt += f"\n\n## User Context (Available Information)\n{context_section}"
                base_prompt += "\n\n**IMPORTANT**: You have full user context above. Only call tools (get_medical_history, get_user_preferences) if you need information NOT provided above or if the context seems outdated. For real-time information (web search) or actions (creating logs), use tools as needed."
            else:
                base_prompt += "\n\n**Note**: No user context available. Use get_medical_history and get_user_preferences tools to fetch user information when needed."
        else:
            # Fallback: Use brief summary if shared context not available
            context_summary = self._get_user_context_summary()
            if context_summary:
                base_prompt += f"\n\nUser context (brief): {context_summary}. Use tools for details."
            else:
                base_prompt += "\n\nUse get_medical_history and get_user_preferences tools to fetch user information."
        
        # Cache the enhanced prompt before returning
        from app.services.prompt_cache import prompt_cache
        prompt_cache.set_enhanced_prompt(self._get_agent_type(), self.user_id, base_prompt)
        
        return base_prompt
    
    def _process_image(self, image_base64: str) -> Image.Image:
        """Process base64 image for Gemini Vision API"""
        try:
            # Decode base64 image
            image_data = base64.b64decode(image_base64)
            image = Image.open(BytesIO(image_data))
            
            # Convert to RGB if necessary (Gemini supports various formats)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            return image
        except Exception as e:
            raise ValueError(f"Error processing image: {str(e)}")
    
    async def analyze_food_image(self, image_base64: str, user_message: str = "") -> Dict[str, Any]:
        """
        Analyze a food image using Gemini Vision API with optional user message context
        
        Args:
            image_base64: Base64-encoded food image
            user_message: User's text message providing context or specific questions about the image
        
        Returns:
            Dict with response, nutrition_analysis, and warnings
        """
        try:
            # Process image
            image = self._process_image(image_base64)
            
            # Get user context (dietary restrictions, medical history, etc.)
            context_summary = self._get_user_context_summary()
            
            # Analyze user message intent
            user_message_lower = user_message.lower() if user_message else ""
            
            # Check if user just wants calories (simple question)
            is_simple_calorie_question = user_message and any(keyword in user_message_lower for keyword in ['calories', 'calorie', 'cal', 'how many']) and len(user_message.split()) < 10
            
            # Detect specific user intents
            wants_healthier_alternatives = any(phrase in user_message_lower for phrase in ['healthier', 'healthier alternative', 'make this healthier', 'better option', 'alternative'])
            wants_meal_planning = any(phrase in user_message_lower for phrase in ['meal plan', 'plan meals', 'suggest meals', 'what should i eat'])
            wants_substitutions = any(phrase in user_message_lower for phrase in ['substitute', 'replace', 'instead of', 'alternative to'])
            wants_nutrition_advice = any(phrase in user_message_lower for phrase in ['is this good', 'should i eat', 'is this healthy', 'nutrition advice'])
            wants_macros = any(keyword in user_message_lower for keyword in ['protein', 'carbs', 'fats', 'macros', 'macronutrients'])
            
            # Build prompt for image analysis based on user intent
            if is_simple_calorie_question:
                # Simple calorie question - be concise but warm, identify the dish
                analysis_prompt = f"""Analyze this food image and provide the dish name and total calories in a friendly, concise way.

User message: {user_message}

Answer format: Use friendly language like "Here's what I see: [Dish name]: ~[calories] calories" or "[Dish name]: ~[calories] calories!" (e.g., "Blueberry pie slice: ~380 calories" or "Here's what I found: Grilled chicken breast, about 250 calories"). 
- Always identify what the food/dish is
- Give the calorie estimate
- Add a friendly touch (exclamation mark, "Here's what I see", etc.)
- Keep it to one short sentence - no explanations, no breakdowns, no advice
- Be warm but concise"""
            
            elif wants_healthier_alternatives:
                # User wants healthier alternatives
                context_instruction = f"\n\nIMPORTANT: Use this context silently to inform recommendations, but DO NOT mention it explicitly: {context_summary}" if context_summary else ""
                analysis_prompt = f"""Analyze this food image and provide healthier alternatives or modifications in a friendly, encouraging way.

User message: {user_message}{context_instruction}

First, identify what food/dish is in the image and its current nutritional profile (calories, macros).
Then, provide specific suggestions to make it healthier with a warm, encouraging tone:
- Healthier ingredient substitutions (use friendly language like "You could swap..." or "Try using...")
- Cooking method improvements (be encouraging: "Here's a great way to...")
- Portion size recommendations
- Alternative dishes that are healthier
- How to modify this specific dish to reduce calories or improve nutrition

Be specific, actionable, and friendly. Use encouraging language: "Great question!", "Here's what I'd suggest...", "You could try...". Reference the actual food in the image. Use any dietary restrictions or preferences silently - don't mention them unless directly relevant to the alternatives."""
            
            elif wants_substitutions:
                # User wants ingredient substitutions
                context_instruction = f"\n\nIMPORTANT: Use this context silently to inform substitutions, but DO NOT mention it explicitly: {context_summary}" if context_summary else ""
                analysis_prompt = f"""Analyze this food image and suggest ingredient substitutions in a friendly, helpful way.

User message: {user_message}{context_instruction}

Identify the food/dish in the image and suggest specific ingredient substitutions based on the user's request.
Use friendly language: "Here's what you could try...", "I'd suggest swapping...", "A great alternative would be..."
Explain why each substitution is beneficial and how it affects the nutritional profile. Be encouraging and warm. Use dietary restrictions silently - don't mention them unless directly relevant."""
            
            elif wants_nutrition_advice:
                # User wants nutrition advice about the food
                context_instruction = f"\n\nIMPORTANT: Use this context silently to inform advice, but DO NOT mention it unless directly relevant: {context_summary}" if context_summary else ""
                analysis_prompt = f"""Analyze this food image and provide nutrition advice in a friendly, supportive way.

User message: {user_message}{context_instruction}

Identify the food/dish in the image, provide its nutritional profile, and give advice based on the user's question.
Use warm, encouraging language: "Here's what I think...", "That's a great question!", "I'd say..."
Be supportive and helpful. Consider dietary restrictions and preferences silently - only mention them if they're critical to the advice or the user specifically asks about them."""
            
            elif wants_macros and not wants_meal_planning:
                # User specifically wants macro breakdown
                analysis_prompt = f"""Analyze this food image and provide detailed macronutrient breakdown in a friendly way.

User message: {user_message}

Identify all food items in the image and provide:
- Total calories
- Protein (grams)
- Carbohydrates (grams)
- Fats (grams)
- Breakdown per food item if multiple items are present

Use friendly language: "Here's the breakdown...", "I found...", "Here's what I see..."
Be specific and accurate with your estimates. Add a warm touch while being informative."""
            
            else:
                # Default: Detailed analysis with user message context
                user_message_context = f"\n\nUser's specific question or request: {user_message}" if user_message else ""
                context_instruction = f"\n\nIMPORTANT: Use this context silently to inform your analysis, but DO NOT mention it explicitly: {context_summary}" if context_summary else ""
                
                analysis_prompt = f"""Analyze this food image and provide detailed nutrition information in a friendly, helpful way.{user_message_context}{context_instruction}

**CRITICAL - Response Format:**
Start your response by clearly identifying the dish/meal name in the first sentence. Use this format:
"This is [DISH NAME]" or "This looks like [DISH NAME]" or "I can see [DISH NAME]"

Then provide:
1. All food items visible in the image (list them clearly)
2. Estimated portion sizes for each item
3. Total calories for the entire meal
4. Macronutrients breakdown (protein, carbohydrates, fats in grams)
5. Suggested meal type (breakfast/lunch/dinner/snack)

{('Address the user\'s specific question: ' + user_message) if user_message and not is_simple_calorie_question else ''}

Use warm, friendly language: "Here's what I found...", "I can see...", "Let me break this down for you..."
Format your response as a clear analysis that can be used to log the meal. Be specific and accurate with your estimates. Be conversational and helpful. Do not mention dietary restrictions, location, or demographics unless directly relevant to the question.

**IMPORTANT**: Always start with the dish name clearly stated in the first sentence."""

            # Use configured model for image analysis
            # Gemini accepts PIL Image objects directly
            response = self.model.generate_content([analysis_prompt, image])
            
            # Extract response text
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            # Try to extract structured data from response
            nutrition_analysis = self._extract_nutrition_data(response_text)
            
            # Check for dietary conflicts
            warnings = []
            dietary_conflict = check_dietary_conflicts(self.user_id, response_text, self.db)
            if dietary_conflict.get("has_conflict"):
                warnings.append(dietary_conflict["message"])
            
            # Automatically log the meal if we have enough data AND no block-level conflicts
            log_result = None
            has_block_conflict = dietary_conflict.get("has_conflict") and dietary_conflict.get("severity") == "block"
            
            if has_block_conflict:
                # Don't log if there's a block-level conflict
                log_result = "Meal NOT logged: This meal conflicts with your dietary restrictions and has been blocked."
            
            if nutrition_analysis and nutrition_analysis.get("calories") and nutrition_analysis.get("meal_type") and not has_block_conflict:
                try:
                    # Extract dish name and food items using improved extraction method
                    dish_name, food_items = self._extract_dish_name_and_items(response_text, nutrition_analysis)
                    
                    # Create structured foods data with dish name and items
                    final_dish_name = dish_name if dish_name else (food_items[0] if food_items else None)
                    foods_structure = {
                        "dish_name": final_dish_name,
                        "items": food_items if food_items else []
                    }
                    foods_data = json.dumps(foods_structure)
                    
                    # Prepare macros
                    macros_dict = nutrition_analysis.get("macros", {})
                    macros_json = json.dumps(macros_dict) if macros_dict else "{}"
                    
                    # Call the create_nutrition_log tool
                    log_tool = self.tools["create_nutrition_log"]
                    log_result = log_tool._run(
                        meal_type=nutrition_analysis["meal_type"],
                        foods=foods_data if isinstance(foods_data, str) else json.dumps(foods_data),
                        calories=nutrition_analysis["calories"],
                        macros=macros_json,
                        notes=f"Auto-logged from image analysis"
                    )
                    
                    # Log tool usage if tracer is available
                    if self.tracer:
                        self.tracer.log_tool_call(
                            tool_name="create_nutrition_log",
                            tool_input={
                                "meal_type": nutrition_analysis["meal_type"],
                                "calories": nutrition_analysis["calories"]
                            },
                            tool_output=log_result
                        )
                except Exception as e:
                    # Don't fail the entire request if logging fails
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to auto-log meal: {str(e)}")
            
            return {
                "response": response_text,
                "nutrition_analysis": nutrition_analysis,
                "warnings": warnings,
                "log_result": log_result
            }
            
        except Exception as e:
            return {
                "response": f"Error analyzing food image: {str(e)}",
                "nutrition_analysis": None,
                "warnings": [f"Image analysis failed: {str(e)}"]
            }
    
    def _extract_dish_name_and_items(self, response_text: str, nutrition_analysis: Dict[str, Any]) -> tuple[Optional[str], list[str]]:
        """
        Extract dish name and food items from response text using improved extraction logic.
        Uses a lightweight LLM call as fallback if regex extraction fails.
        
        Returns:
            Tuple of (dish_name, food_items)
        """
        import re
        
        dish_name = None
        food_items = []
        
        # Step 1: Extract food items first (needed for dish name fallback)
        if nutrition_analysis.get("foods") and len(nutrition_analysis["foods"]) > 0:
            food_items = nutrition_analysis["foods"]
        else:
            # Try to extract food items from response text
            food_patterns = [
                r'(?:^|\n)\s*(?:\d+\.|[-•])\s*\*?\*?([A-Z][^:\n*]+?)\*?\*?(?::|,|\n|$)',
                r'\*\*([A-Z][^:]+?)\*\*:\s*[^:\n]+',
                r'([A-Z][a-z]+(?:\s+[a-z]+)*?)(?:\s*\([^)]+\))?(?:\s*:|\s*-\s*|\s*,\s*|\n)',
            ]
            for pattern in food_patterns:
                matches = re.findall(pattern, response_text, re.MULTILINE | re.IGNORECASE)
                if matches:
                    food_items = [m.strip() for m in matches if m.strip() and len(m.strip()) > 2]
                    # Remove duplicates and common words
                    food_items = list(dict.fromkeys([f for f in food_items if f.lower() not in ['food', 'items', 'item', 'dish', 'meal', 'total', 'calories', 'protein', 'carbs', 'fats']]))
                    if food_items:
                        break
        
        # Step 2: Extract dish name with improved patterns
        # Priority 1: Look for explicit dish name patterns at the start
        dish_patterns = [
            r'^(?:This is|This looks like|I can see|Here\'s|I found)\s+(?:a\s+)?([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*?)(?:\s+(?:breakfast|lunch|dinner|meal|dish|plate|with|and))?',
            r'^(?:This is|This looks like|I can see|Here\'s|I found)\s+(?:a\s+)?([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*?)(?:\.|,|\s|$)',
            r'([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*?)\s+(?:breakfast|lunch|dinner)',
            r'(?:main dish|dish is|meal is)\s+([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*)',
        ]
        
        for pattern in dish_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE | re.MULTILINE)
            if match:
                potential_name = match.group(1).strip()
                # Clean up common prefixes/suffixes
                potential_name = re.sub(r'^(a|an|the)\s+', '', potential_name, flags=re.IGNORECASE)
                # Make sure it's not a common word
                if potential_name.lower() not in ['food', 'items', 'item', 'dish', 'meal', 'this', 'that', 'here', 'breakdown', 'analysis']:
                    if len(potential_name) > 2 and len(potential_name) < 50:
                        dish_name = potential_name
                        break
        
        # Step 3: Fallback to first food item if no explicit dish name
        if not dish_name and food_items and len(food_items) > 0:
            dish_name = food_items[0]
        
        # Step 4: If still no dish name, use lightweight LLM extraction
        if not dish_name:
            try:
                dish_name = self._extract_dish_name_with_llm(response_text)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"LLM dish name extraction failed: {str(e)}")
        
        return dish_name, food_items
    
    def _extract_dish_name_with_llm(self, response_text: str) -> Optional[str]:
        """
        Use a lightweight LLM call to extract dish name from response text.
        This is a fallback when regex extraction fails.
        """
        try:
            import re
            # Use OpenAI for fast, cheap extraction (GPT-3.5-turbo is fast and cheap)
            import openai
            from openai import OpenAI
            
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            extraction_prompt = f"""Extract the dish/meal name from this food analysis text. Return ONLY the dish name, nothing else.

Text: {response_text[:500]}

Dish name:"""
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a food name extractor. Extract only the dish/meal name from food analysis text. Return just the name, nothing else."},
                    {"role": "user", "content": extraction_prompt}
                ],
                max_tokens=30,
                temperature=0.1
            )
            
            extracted_name = response.choices[0].message.content.strip()
            # Clean up any extra text
            extracted_name = re.sub(r'^(dish name|name|meal):\s*', '', extracted_name, flags=re.IGNORECASE)
            extracted_name = extracted_name.strip('"\'.,')
            
            if extracted_name and len(extracted_name) > 2 and len(extracted_name) < 50:
                return extracted_name
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to extract dish name with LLM: {str(e)}")
        
        return None
    
    def _extract_nutrition_data(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract structured nutrition data from agent response"""
        # This is a simple extraction - could be enhanced with more sophisticated parsing
        # or by instructing the LLM to return JSON
        try:
            import re
            # Look for common patterns in the response
            nutrition_data = {
                "foods": [],
                "calories": None,
                "macros": {
                    "protein": None,
                    "carbs": None,
                    "fats": None
                },
                "meal_type": None
            }
            
            # Try to extract food items (look for numbered lists, bullet points, or bold text)
            # Pattern: "1. Food item", "- Food item", "**Food:**", etc.
            food_patterns = [
                r'(?:^|\n)\s*(?:\d+\.|[-•])\s*\*?\*?([A-Z][^:\n*]+?)\*?\*?(?::|,|\n|$)',
                r'\*\*([A-Z][^:]+?)\*\*:\s*[^:\n]+',
                r'([A-Z][a-z]+(?:\s+[a-z]+)*?)(?:\s*\([^)]+\))?(?:\s*:|\s*-\s*|\s*,\s*|\n)',
            ]
            foods_found = []
            for pattern in food_patterns:
                matches = re.findall(pattern, response_text, re.MULTILINE | re.IGNORECASE)
                for match in matches:
                    food_item = match.strip()
                    # Clean up common prefixes/suffixes
                    food_item = re.sub(r'^(?:This is|This looks like|I can see|Here\'s|I found)\s+', '', food_item, flags=re.IGNORECASE)
                    food_item = re.sub(r'\s*\([^)]*approx[^)]*\)', '', food_item, flags=re.IGNORECASE)
                    food_item = food_item.strip()
                    if food_item and len(food_item) > 2 and food_item.lower() not in ['total', 'protein', 'carbs', 'fats', 'calories', 'food', 'items', 'item', 'dish', 'meal']:
                        foods_found.append(food_item)
            
            # Remove duplicates while preserving order
            foods_found = list(dict.fromkeys(foods_found))
            
            # If no structured list found, try to extract from common phrases
            if not foods_found:
                # Look for "contains", "includes", "has" followed by food items
                contains_pattern = r'(?:contains|includes|has|with)\s+([^.\n]+)'
                contains_match = re.search(contains_pattern, response_text, re.IGNORECASE)
                if contains_match:
                    items_text = contains_match.group(1)
                    # Split by commas or "and"
                    items = re.split(r',\s*|\s+and\s+', items_text)
                    foods_found = [item.strip() for item in items if item.strip() and len(item.strip()) > 2]
            
            nutrition_data["foods"] = foods_found[:15]  # Limit to 15 items
            
            # Try to extract calories (look for numbers followed by "cal" or "calories")
            calorie_match = re.search(r'(\d+)\s*(?:cal|calories|kcal)', response_text, re.IGNORECASE)
            if calorie_match:
                nutrition_data["calories"] = float(calorie_match.group(1))
            
            # Try to extract macros
            protein_match = re.search(r'protein[:\s]+(\d+(?:\.\d+)?)\s*g', response_text, re.IGNORECASE)
            if protein_match:
                nutrition_data["macros"]["protein"] = float(protein_match.group(1))
            
            carbs_match = re.search(r'(?:carbs|carbohydrates)[:\s]+(\d+(?:\.\d+)?)\s*g', response_text, re.IGNORECASE)
            if carbs_match:
                nutrition_data["macros"]["carbs"] = float(carbs_match.group(1))
            
            fats_match = re.search(r'fat[s]?[:\s]+(\d+(?:\.\d+)?)\s*g', response_text, re.IGNORECASE)
            if fats_match:
                nutrition_data["macros"]["fats"] = float(fats_match.group(1))
            
            # Try to identify meal type
            meal_types = ["breakfast", "lunch", "dinner", "snack"]
            for meal_type in meal_types:
                if meal_type in response_text.lower():
                    nutrition_data["meal_type"] = meal_type
                    break
            
            return nutrition_data if nutrition_data["calories"] or any(nutrition_data["macros"].values()) else None
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error extracting nutrition data: {str(e)}")
            return None
    
    async def recommend_meal(self, user_input: str, image_base64: Optional[str] = None) -> Dict[str, Any]:
        """
        Main method to handle user queries - supports both text and image input together
        
        Args:
            user_input: User's text message (can be empty if only image provided)
            image_base64: Optional base64-encoded food image
        
        Returns:
            Dict with response, nutrition_analysis (if image provided), and warnings
        """
        try:
            # If image is provided, analyze it with user message context
            if image_base64:
                # Use user_input as context even if it's not a direct question
                # This allows users to ask questions like "Can I make this healthier?" with an image
                return await self.analyze_food_image(image_base64, user_input if user_input else "")
            
            # Otherwise, handle as regular text query using direct Gemini SDK
            # Detect if this is a simple question (calories, macros, etc.) - don't include context for these
            simple_question_keywords = ['calories', 'calorie', 'cal', 'protein', 'carbs', 'fat', 'macro', 'how many', 'what is', 'nutrition facts']
            is_simple_question = any(keyword in user_input.lower() for keyword in simple_question_keywords) and len(user_input.split()) < 15
            
            # Build enhanced prompt with full context for complex queries, minimal for simple ones
            if is_simple_question:
                # Simple questions: minimal context to keep tokens low
                enhanced_prompt = f"{self.system_message}\n\nUser query: {user_input}"
            else:
                # Complex queries: full context in system prompt to reduce tool calls
                enhanced_system_prompt = self._build_enhanced_system_prompt()
                enhanced_prompt = f"{enhanced_system_prompt}\n\nUser query: {user_input}"
            
            # Get response from Gemini (direct SDK, no LangChain)
            response = self.model.generate_content(enhanced_prompt)
            
            # Extract response text
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            return {
                "response": response_text,
                "nutrition_analysis": None,
                "warnings": []
            }
            
        except Exception as e:
            return {
                "response": f"Error processing request: {str(e)}",
                "nutrition_analysis": None,
                "warnings": [f"Agent error: {str(e)}"]
            }

