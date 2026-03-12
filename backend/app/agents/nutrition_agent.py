"""
Nutrition Agent - Specialized agent for nutrition, meal planning, and image-based food analysis.

This module provides the NutritionAgent class, which specializes in nutrition advice,
meal planning, and image-based food analysis using Google Gemini Vision API. Unlike
other agents that extend BaseAgent, this agent uses Gemini directly for vision capabilities.

Key Features:
- Image-based food analysis using Gemini Vision API
- Meal planning and recommendations
- Dietary restriction checking
- Automatic meal logging from image analysis
- Nutrition data extraction (calories, macros)
- Intent detection for personalized responses
- Context-aware recommendations

Vision Capabilities:
- Analyzes food images (base64-encoded)
- Identifies dishes and food items
- Estimates calories and macronutrients
- Provides nutrition advice based on images
- Supports various user intents (calories, macros, alternatives, etc.)

Dietary Integration:
- Checks dietary restrictions against analyzed foods
- Prevents logging meals with block-level conflicts
- Provides warnings for dietary conflicts
- Considers user preferences and medical history

Technical Approach:
- Uses Google Gemini SDK directly (not LangChain wrapper)
- Manual tool calling (not bound to LLM)
- Async/await pattern for Gemini API calls
- Retry logic with model fallback
- Timeout protection for API calls
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
# Using google.generativeai directly (not LangChain wrapper) for better compatibility
# Direct SDK provides better control over Gemini Vision API
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
from app.services.llm_retry import retry_llm_call, get_fallback_model
from app.models.user_preferences import UserPreferences
from app.models.conversation_message import ConversationMessage


class NutritionAgent:
    """
    Nutrition Agent specialized for meal planning, dietary advice, and image-based calorie tracking.
    
    This agent uses Google Gemini Vision API for image-based food analysis. Unlike other
    agents that extend BaseAgent, this agent uses Gemini directly for vision capabilities
    and implements manual tool calling.
    
    Key Capabilities:
        - Image-based food analysis (identify dishes, estimate calories, macros)
        - Meal planning and recommendations
        - Dietary restriction checking
        - Automatic meal logging from image analysis
        - Intent detection (calories, macros, alternatives, meal planning, etc.)
        - Context-aware nutrition advice
        
    Vision Analysis:
        - Analyzes base64-encoded food images
        - Identifies dishes and food items
        - Estimates calories and macronutrients
        - Provides nutrition advice based on images
        
    Dietary Safety:
        - Checks dietary restrictions against analyzed foods
        - Prevents logging meals with block-level conflicts
        - Provides warnings for dietary conflicts
        - Considers user preferences and medical history
        
    Attributes:
        user_id: User ID for user-specific operations
        db: Database session for querying user data
        model: Gemini GenerativeModel instance for vision analysis
        model_name: Gemini model name (default: "gemini-2.5-flash-lite")
        _shared_context: Shared user context from ContextManager (optional)
        tracer: AgentTracer instance for observability (optional)
        llm_timeout: Timeout for LLM calls in seconds (default: 60s)
        tools: Dictionary of tools for manual calling
        system_message: System prompt for nutrition agent
        _user_context_summary: Cached user context summary
        _context_fetched: Flag indicating if context has been fetched
    """
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gemini-2.5-flash-lite",
        shared_context: Optional[Dict[str, Optional[Dict]]] = None,
        tracer: Optional[Any] = None,
        llm_timeout: float = 60.0  # P1.1: Timeout for LLM calls in seconds (default: 60s)
    ):
        """
        Initialize NutritionAgent with Gemini Vision API configuration.
        
        Args:
            user_id: User ID for user-specific operations
            db: Database session for querying user data
            model_name: Gemini model name (default: "gemini-2.5-flash-lite")
                       Used for vision analysis and text generation
            shared_context: Shared user context from ContextManager (optional)
                          Includes medical history and preferences
            tracer: AgentTracer instance for observability (optional)
            llm_timeout: Timeout for LLM calls in seconds (default: 60s)
                        Prevents hanging on slow API responses
            
        Initialization Steps:
            1. Store user_id, db, and configuration
            2. Store shared context and tracer
            3. Validate and configure Gemini API key
            4. Initialize Gemini model
            5. Initialize tools (for manual tool calling)
            6. Build and cache system prompt
            7. Initialize context caching
            
        Note:
            - Raises ValueError if GOOGLE_GEMINI_API_KEY is not set
            - Uses Gemini SDK directly (not LangChain wrapper)
            - Tools are stored in dictionary for manual calling
            - System prompt is cached for future use
        """
        # Store user and database references
        self.user_id = user_id  # User ID for user-specific operations
        self.db = db  # Database session for querying user data
        
        # Store shared context if provided (from ContextManager)
        # Shared context includes medical history and preferences
        # Reduces redundant database queries
        self._shared_context = shared_context
        
        # Store tracer for observability (optional)
        # Used for logging agent execution, tool calls, and token usage
        self.tracer = tracer
        
        # P1.1: Store LLM timeout configuration
        # Prevents hanging on slow API responses
        self.llm_timeout = llm_timeout
        
        # Get Gemini API key from environment
        # This should have been validated at startup, but check here as a safety measure
        # Required for Nutrition Agent (image analysis and meal planning)
        api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_GEMINI_API_KEY is not set in environment variables. "
                "This key is required for the Nutrition Agent (image analysis and meal planning). "
                "Please set it in your .env file or environment. "
                "The application should have validated this at startup - if you see this error, "
                "the environment may have been changed after startup."
            )
        
        # Configure Gemini API (using direct SDK, not LangChain wrapper)
        # Direct SDK provides better control over Gemini Vision API
        genai.configure(api_key=api_key)
        # Initialize Gemini model for vision analysis
        # Default model: "gemini-2.5-flash-lite" (fast and cost-effective)
        self.model = genai.GenerativeModel(model_name)
        self.model_name = model_name  # Store model name for fallback logic
        
        # Initialize tools (for manual tool calling)
        # Unlike BaseAgent, tools are stored in dictionary for manual calling
        # Tools are not bound to LLM (manual tool calling pattern)
        self.tools = {
            "get_medical_history": GetMedicalHistoryTool(user_id=user_id, db=db),  # Get user's medical history
            "get_user_preferences": GetUserPreferencesTool(user_id=user_id, db=db),  # Get user's preferences
            "create_nutrition_log": CreateNutritionLogTool(user_id=user_id, db=db),  # Create nutrition log entries
            "web_search": WebSearchTool(),  # Web search tool (no user_id or db needed - global)
        }
        
        # Create system message
        # Checks cache first, builds if not cached
        self.system_message = self._get_system_prompt()
        
        # Cache user context summary
        # Context summary is minimal (max 150 chars) to reduce token usage
        self._user_context_summary = None  # Cached user context summary
        self._context_fetched = False  # Flag indicating if context has been fetched
    
    def _get_agent_type(self) -> str:
        """
        Get agent type identifier for caching and identification.
        
        Returns:
            str: Agent type identifier ("nutrition")
            
        Note:
            - Used for prompt caching (static and enhanced prompts)
            - Used for identification in logs and traces
        """
        return "nutrition"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for nutrition agent.
        
        This method retrieves the system prompt for the nutrition agent,
        checking cache first, then building if not cached.
        
        Returns:
            str: System prompt for nutrition agent
            
        Prompt Strategy:
            1. Check cache first (static prompt cache)
            2. If cached, return cached prompt
            3. If not cached, build prompt from nutrition_prompt module
            4. Cache the built prompt for future use
            
        Note:
            - Uses prompt caching to reduce token usage
            - Static prompts are cached indefinitely (version-based invalidation)
            - Prompt includes nutrition-specific guidelines and dietary instructions
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
            preferences = self._shared_context.get("preferences")
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
                base_prompt += "\n\n**IMPORTANT**: You have full user context above. Use this information to make autonomous recommendations. Work with partial information from the conversation - if the user mentions 'post-workout', use that as intended use. Don't ask for all details upfront if you can make a reasonable recommendation based on available context. Only call tools (get_medical_history, get_user_preferences) if you need information NOT provided above or if the context seems outdated. For real-time information (web search) or actions (creating logs), use tools as needed."
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
        """
        Process base64 image for Gemini Vision API.
        
        This method decodes a base64-encoded image and converts it to a PIL Image
        object suitable for Gemini Vision API. Ensures RGB format for compatibility.
        
        Args:
            image_base64: Base64-encoded image string
            
        Returns:
            Image.Image: PIL Image object in RGB format
            
        Processing Steps:
            1. Decode base64 string to binary image data
            2. Open image using PIL Image
            3. Convert to RGB format if necessary (Gemini compatibility)
            4. Return processed image
            
        Error Handling:
            - Raises ValueError if image processing fails
            - Handles base64 decoding errors
            - Handles image format conversion errors
            
        Note:
            - Gemini Vision API accepts PIL Image objects directly
            - RGB format ensures compatibility across image types
            - Used by analyze_food_image() for image preprocessing
        """
        try:
            # Decode base64 image
            # Converts base64 string to binary image data
            image_data = base64.b64decode(image_base64)
            # Open image using PIL Image
            # BytesIO creates file-like object from binary data
            image = Image.open(BytesIO(image_data))
            
            # Convert to RGB if necessary (Gemini supports various formats)
            # RGB format ensures compatibility across different image types
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            return image
        except Exception as e:
            # Raise ValueError with descriptive error message
            raise ValueError(f"Error processing image: {str(e)}")
    
    async def analyze_food_image(self, image_base64: str, user_message: str = "") -> Dict[str, Any]:
        """
        Analyze a food image using Gemini Vision API with optional user message context.
        
        This method performs comprehensive food image analysis using Gemini Vision API.
        It detects user intent, analyzes the image, extracts nutrition data, checks
        dietary conflicts, and optionally logs the meal automatically.
        
        Analysis Flow:
            1. Process image (decode base64, convert to PIL Image)
            2. Get user context (dietary restrictions, medical history)
            3. Detect user intent (calories, macros, alternatives, meal planning, etc.)
            4. Build intent-specific prompt
            5. Analyze image with Gemini Vision API (with retry logic and timeout)
            6. Extract nutrition data from response
            7. Check dietary conflicts
            8. Auto-log meal if sufficient data and no block conflicts
        
        Intent Detection:
            - Simple calorie question: Concise calorie estimate
            - Healthier alternatives: Suggestions for making dish healthier
            - Substitutions: Ingredient substitution recommendations
            - Nutrition advice: General nutrition guidance
            - Macros: Detailed macronutrient breakdown
            - Meal planning: Meal planning suggestions
            - Default: Comprehensive nutrition analysis
        
        Args:
            image_base64: Base64-encoded food image
            user_message: User's text message providing context or specific questions
                         Examples: "How many calories?", "Make this healthier", "What are the macros?"
        
        Returns:
            Dict[str, Any]: Analysis results:
                {
                    "response": str,  # Gemini's analysis response
                    "nutrition_analysis": Dict or None,  # Extracted nutrition data
                    "warnings": List[str] or None,  # Dietary conflict warnings
                    "log_result": str or None,  # Meal logging result
                    "degraded": bool,  # True if fallback model was used
                    "fallback_info": Dict or None  # Fallback model information
                }
                
        Nutrition Analysis Structure:
            {
                "dish_name": str,  # Name of dish/meal
                "calories": float,  # Total calories
                "macros": {  # Macronutrients
                    "protein": float,  # Protein in grams
                    "carbs": float,  # Carbohydrates in grams
                    "fats": float  # Fats in grams
                },
                "meal_type": str  # breakfast/lunch/dinner/snack
            }
            
        Auto-Logging:
            - Automatically logs meal if sufficient nutrition data extracted
            - Prevents logging if block-level dietary conflicts exist
            - Includes dish name, food items, calories, and macros
            
        Error Handling:
            - Handles image processing errors
            - Handles Gemini API errors (with retry logic)
            - Handles timeout errors
            - Handles logging errors (doesn't fail entire request)
            
        Note:
            - Uses Gemini Vision API for image analysis
            - Supports various user intents for personalized responses
            - Checks dietary restrictions before logging
            - Includes retry logic with model fallback
        """
        try:
            # Process image
            image = self._process_image(image_base64)
            
            # Get user context (dietary restrictions, medical history, etc.)
            context_summary = self._get_user_context_summary()
            
            # Analyze user message intent
            # Intent detection allows personalized responses based on user's specific needs
            # Different intents trigger different prompt strategies for better user experience
            user_message_lower = user_message.lower() if user_message else ""
            
            # Check if user just wants calories (simple question)
            # Simple calorie questions get concise, friendly responses
            # Criteria: Contains calorie keywords AND short message (< 10 words)
            is_simple_calorie_question = user_message and any(keyword in user_message_lower for keyword in ['calories', 'calorie', 'cal', 'how many']) and len(user_message.split()) < 10
            
            # Detect specific user intents
            # Each intent triggers a different prompt strategy for personalized responses
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

            # Use configured model for image analysis (with retry logic)
            # Gemini accepts PIL Image objects directly (no need for base64 encoding)
            # P0.3: Track original model name to detect fallback usage
            # Used to detect if model fallback occurred during execution
            original_model_name = self.model_name
            self._used_fallback_model = False  # Flag indicating if fallback was used
            self._fallback_info = None  # Fallback information (original model, fallback model, reason)
            
            def update_gemini_model(new_model: str):
                """
                Update Gemini model if fallback is needed.
                
                This function updates the Gemini model instance to use a fallback model
                when the primary model fails. Used by retry logic for model fallback.
                
                Args:
                    new_model: Fallback model name (e.g., "gemini-2.0-flash-lite")
                """
                import google.generativeai as genai
                # Get API key (should be validated at startup)
                api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
                if not api_key:
                    raise ValueError(
                        "GOOGLE_GEMINI_API_KEY is not set. This should have been validated at startup. "
                        "Please restart the application with the key set in your environment variables."
                    )
                # Reconfigure Gemini API with fallback model
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(new_model)
                self.model_name = new_model
                # P0.3: Track fallback usage
                self._used_fallback_model = True
                self._fallback_info = {
                    "original_model": original_model_name,
                    "fallback_model": new_model,
                    "reason": "Model fallback due to errors"
                }
                logger.info(f"Fell back to Gemini model: {new_model}")
            
            # Run in executor since Gemini SDK is synchronous
            # Gemini SDK is synchronous, so we run it in executor for async compatibility
            import asyncio
            loop = asyncio.get_event_loop()
            
            def sync_generate():
                """
                Synchronous Gemini API call.
                
                This function calls Gemini API synchronously. It's run in an executor
                to make it compatible with async/await pattern.
                
                Returns:
                    Gemini API response
                """
                # Gemini accepts list of [prompt, image] for vision analysis
                return self.model.generate_content([analysis_prompt, image])
            
            async def async_generate():
                """
                Async wrapper for Gemini API call with timeout protection.
                
                This function wraps the synchronous Gemini call in an executor and
                adds timeout protection to prevent hanging on slow API responses.
                
                Returns:
                    Gemini API response
                    
                Raises:
                    TimeoutError: If API call exceeds timeout
                """
                # P1.1: Add timeout to Gemini call
                # Prevents hanging on slow API responses
                try:
                    return await asyncio.wait_for(
                        loop.run_in_executor(None, sync_generate),  # Run sync call in executor
                        timeout=self.llm_timeout  # Timeout in seconds
                    )
                except asyncio.TimeoutError:
                    timeout_msg = f"Gemini image analysis timed out after {self.llm_timeout} seconds"
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(timeout_msg)
                    if self.tracer:
                        self.tracer.log_timeout(self.llm_timeout, "Gemini image analysis")
                    raise TimeoutError(f"Image analysis timed out after {self.llm_timeout} seconds. Please try again with a simpler image.")
            
            # Call Gemini API with retry logic and timeout protection
            # Retry logic handles transient errors with exponential backoff
            # Model fallback handles persistent errors by switching to cheaper model
            response = await retry_llm_call(
                func=async_generate,  # Async Gemini invocation function
                max_retries=3,  # Maximum retry attempts
                initial_delay=1.0,  # Initial delay before retry (seconds)
                max_delay=60.0,  # Maximum delay cap (seconds)
                tracer=self.tracer,  # Tracer for logging retries and token usage
                model_name=self.model_name,  # Current model name (for fallback)
                update_model_fn=update_gemini_model if self.model_name else None,  # Model update function
                service_name="gemini",  # Service name for circuit breaker
            )
            
            # Extract response text from Gemini API response
            # Gemini response has .text attribute containing the analysis
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            # Try to extract structured data from response
            # Extracts nutrition data (calories, macros, meal type) from text response
            # Uses regex and parsing to extract structured data
            nutrition_analysis = self._extract_nutrition_data(response_text)
            
            # Check for dietary conflicts
            # Checks if analyzed foods conflict with user's dietary restrictions
            # Prevents logging meals that violate dietary restrictions
            warnings = []
            dietary_conflict = check_dietary_conflicts(self.user_id, response_text, self.db)
            if dietary_conflict.get("has_conflict"):
                warnings.append(dietary_conflict["message"])  # Add conflict warning
            
            # Automatically log the meal if we have enough data AND no block-level conflicts
            # Auto-logging improves user experience by automatically tracking meals
            # Only logs if sufficient nutrition data extracted and no block conflicts
            log_result = None
            has_block_conflict = dietary_conflict.get("has_conflict") and dietary_conflict.get("severity") == "block"
            
            if has_block_conflict:
                # Don't log if there's a block-level conflict
                # Block-level conflicts indicate meals that should be completely avoided
                log_result = "Meal NOT logged: This meal conflicts with your dietary restrictions and has been blocked."
            
            # Auto-log meal if we have sufficient nutrition data and no block conflicts
            # Auto-logging improves user experience by automatically tracking meals
            # Only logs if calories, meal_type extracted and no block-level conflicts
            if nutrition_analysis and nutrition_analysis.get("calories") and nutrition_analysis.get("meal_type") and not has_block_conflict:
                try:
                    # Extract dish name and food items using improved extraction method
                    # Extracts structured data from response text for logging
                    dish_name, food_items = self._extract_dish_name_and_items(response_text, nutrition_analysis)
                    
                    # Create structured foods data with dish name and items
                    # Structure: {"dish_name": "...", "items": ["...", "..."]}
                    # Used for nutrition log entry
                    final_dish_name = dish_name if dish_name else (food_items[0] if food_items else None)
                    foods_structure = {
                        "dish_name": final_dish_name,  # Main dish name
                        "items": food_items if food_items else []  # List of food items
                    }
                    foods_data = json.dumps(foods_structure)  # Convert to JSON string
                    
                    # Prepare macros for logging
                    # Macros: protein, carbs, fats in grams
                    macros_dict = nutrition_analysis.get("macros", {})
                    macros_json = json.dumps(macros_dict) if macros_dict else "{}"
                    
                    # Call the create_nutrition_log tool
                    # Manually calls tool (not bound to LLM)
                    log_tool = self.tools["create_nutrition_log"]
                    log_result = log_tool._run(
                        meal_type=nutrition_analysis["meal_type"],  # breakfast/lunch/dinner/snack
                        foods=foods_data if isinstance(foods_data, str) else json.dumps(foods_data),  # Structured foods data
                        calories=nutrition_analysis["calories"],  # Total calories
                        macros=macros_json,  # Macros JSON string
                        notes=f"Auto-logged from image analysis"  # Auto-logging note
                    )
                    
                    # Log tool usage if tracer is available
                    # Tracks tool calls for observability
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
                    # Logging errors are logged but don't prevent returning analysis results
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to auto-log meal: {str(e)}")
            
            result = {
                "response": response_text,
                "nutrition_analysis": nutrition_analysis,
                "warnings": warnings,
                "log_result": log_result
            }
            # P0.3: Include degraded flag and fallback info if fallback model was used
            if hasattr(self, '_used_fallback_model') and self._used_fallback_model:
                result["degraded"] = True
                result["fallback_info"] = getattr(self, '_fallback_info', None)
            else:
                result["degraded"] = False
            return result
            
        except Exception as e:
            return {
                "response": f"Error analyzing food image: {str(e)}",
                "nutrition_analysis": None,
                "warnings": [f"Image analysis failed: {str(e)}"],
                "degraded": False
            }
    
    def _extract_dish_name_and_items(self, response_text: str, nutrition_analysis: Dict[str, Any]) -> tuple[Optional[str], list[str]]:
        """
        Extract dish name and food items from response text using improved extraction logic.
        
        This method extracts structured data (dish name and food items) from Gemini's
        text response. Uses regex patterns first, with LLM call as fallback if extraction fails.
        
        Args:
            response_text: Gemini's analysis response text
            nutrition_analysis: Extracted nutrition data dictionary
            
        Returns:
            tuple[Optional[str], list[str]]: Tuple of (dish_name, food_items)
                - dish_name: Name of the dish/meal (e.g., "Grilled Chicken Salad")
                - food_items: List of individual food items (e.g., ["chicken", "lettuce", "tomatoes"])
                
        Extraction Strategy:
            1. Extract food items first (needed for dish name fallback)
            2. Extract dish name using multiple patterns
            3. Fallback to LLM call if regex extraction fails
            
        Regex Patterns:
            - Pattern 1: Numbered/bulleted lists (e.g., "1. Chicken breast")
            - Pattern 2: Bold text (e.g., "**Chicken**: ...")
            - Pattern 3: Capitalized words followed by colon/dash
            
        Note:
            - Used for structured meal logging
            - Removes duplicates and common words
            - Falls back to LLM call if regex fails
        """
        import re
        
        dish_name = None  # Extracted dish name
        food_items = []  # List of extracted food items
        
        # Step 1: Extract food items first (needed for dish name fallback)
        # Check if food items already extracted in nutrition_analysis
        if nutrition_analysis.get("foods") and len(nutrition_analysis["foods"]) > 0:
            food_items = nutrition_analysis["foods"]
        else:
            # Try to extract food items from response text using regex patterns
            # Multiple patterns handle different response formats
            food_patterns = [
                r'(?:^|\n)\s*(?:\d+\.|[-•])\s*\*?\*?([A-Z][^:\n*]+?)\*?\*?(?::|,|\n|$)',  # Numbered/bulleted lists
                r'\*\*([A-Z][^:]+?)\*\*:\s*[^:\n]+',  # Bold text format
                r'([A-Z][a-z]+(?:\s+[a-z]+)*?)(?:\s*\([^)]+\))?(?:\s*:|\s*-\s*|\s*,\s*|\n)',  # Capitalized words
            ]
            for pattern in food_patterns:
                matches = re.findall(pattern, response_text, re.MULTILINE | re.IGNORECASE)
                if matches:
                    # Clean and filter matches
                    food_items = [m.strip() for m in matches if m.strip() and len(m.strip()) > 2]
                    # Remove duplicates and common words
                    # Filters out generic words that aren't actual food items
                    food_items = list(dict.fromkeys([f for f in food_items if f.lower() not in ['food', 'items', 'item', 'dish', 'meal', 'total', 'calories', 'protein', 'carbs', 'fats']]))
                    if food_items:
                        break  # Found food items, exit loop
        
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
        Main method to handle user queries - supports both text and image input together.
        
        This is the primary entry point for nutrition agent interactions. It handles
        both text-only queries and image-based queries (with optional text context).
        
        Query Types:
            - Image + Text: Analyzes image with text context (e.g., "Make this healthier")
            - Text Only: Handles meal planning, nutrition advice, general queries
            - Simple Questions: Quick answers (calories, macros) with minimal context
            - Complex Queries: Detailed responses with full user context
            
        Args:
            user_input: User's text message (can be empty if only image provided)
                       Examples: "Plan my meals", "What should I eat?", "How many calories?"
            image_base64: Optional base64-encoded food image
                         If provided, triggers image analysis with text as context
        
        Returns:
            Dict[str, Any]: Response dictionary:
                {
                    "response": str,  # Agent's response
                    "nutrition_analysis": Dict or None,  # Extracted nutrition data (if image)
                    "warnings": List[str] or None,  # Dietary conflict warnings
                    "log_result": str or None,  # Meal logging result (if image)
                    "degraded": bool,  # True if fallback model was used
                    "fallback_info": Dict or None  # Fallback model information
                }
                
        Processing Flow:
            1. If image provided: Analyze image with text context
            2. If text only: Detect query complexity (simple vs complex)
            3. Build prompt (minimal context for simple, full context for complex)
            4. Call Gemini API with retry logic and timeout
            5. Return response with optional nutrition analysis
            
        Context Strategy:
            - Simple questions: Minimal context (reduces tokens)
            - Complex queries: Full context (reduces tool calls)
            - Image analysis: Includes user context for personalized advice
            
        Note:
            - Supports both image and text input simultaneously
            - Uses Gemini SDK directly (not LangChain wrapper)
            - Includes retry logic with model fallback
            - Handles timeout errors gracefully
        """
        try:
            # If image is provided, analyze it with user message context
            # Image analysis handles both image-only and image+text queries
            if image_base64:
                # Use user_input as context even if it's not a direct question
                # This allows users to ask questions like "Can I make this healthier?" with an image
                # Image analysis handles intent detection and personalized responses
                return await self.analyze_food_image(image_base64, user_input if user_input else "")
            
            # Otherwise, handle as regular text query using direct Gemini SDK
            # Text-only queries: meal planning, nutrition advice, general questions
            # Detect if this is a simple question (calories, macros, etc.) - don't include context for these
            # Simple questions get minimal context to reduce token usage
            simple_question_keywords = ['calories', 'calorie', 'cal', 'protein', 'carbs', 'fat', 'macro', 'how many', 'what is', 'nutrition facts']
            is_simple_question = any(keyword in user_input.lower() for keyword in simple_question_keywords) and len(user_input.split()) < 15
            
            # Load recent conversation history for context
            # This allows agents to recall previous messages in the conversation
            conversation_context = ""
            try:
                # Get recent conversation history for this agent type (last 10 messages)
                # This provides context for follow-up questions and maintains conversation flow
                agent_type = "nutrition"
                history_query = self.db.query(ConversationMessage).filter(
                    ConversationMessage.user_id == self.user_id,
                    ConversationMessage.agent_type == agent_type
                ).order_by(ConversationMessage.created_at.desc()).limit(10).all()
                
                # Reverse to get chronological order (oldest first)
                history_query.reverse()
                
                # Format conversation history as context
                if history_query:
                    conversation_parts = []
                    for msg in history_query:
                        role_label = "User" if msg.role == 'user' else "Assistant"
                        conversation_parts.append(f"{role_label}: {msg.content}")
                    conversation_context = "\n\nPrevious conversation:\n" + "\n".join(conversation_parts) + "\n"
            except Exception as e:
                # If loading history fails, log but continue without it
                # Don't block agent execution if history loading fails
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to load conversation history: {e}")
            
            # Build enhanced prompt with full context for complex queries, minimal for simple ones
            # Context strategy: Balance token usage vs tool call reduction
            if is_simple_question:
                # Simple questions: minimal context to keep tokens low
                # Simple questions don't need full user context (e.g., "How many calories in an apple?")
                # But still include conversation history for follow-up questions
                enhanced_prompt = f"{self.system_message}{conversation_context}\n\nUser query: {user_input}"
            else:
                # Complex queries: full context in system prompt to reduce tool calls
                # Complex queries benefit from full context (e.g., "Plan my meals for the week")
                # Full context reduces need for tool calls (get_medical_history, get_user_preferences)
                enhanced_system_prompt = self._build_enhanced_system_prompt()
                enhanced_prompt = f"{enhanced_system_prompt}{conversation_context}\n\nUser query: {user_input}"
            
            # Detect if user is asking for links/products and perform web search proactively
            # Keywords that indicate need for web search: links, buy, purchase, where to find, etc.
            link_keywords = ['link', 'links', 'buy', 'purchase', 'where to', 'where can', 'find', 'available', 'retailer', 'store', 'website']
            needs_web_search = any(keyword in user_input.lower() for keyword in link_keywords)
            
            # Also check conversation context for product mentions
            if conversation_context and not needs_web_search:
                needs_web_search = any(keyword in conversation_context.lower() for keyword in ['protein powder', 'supplement', 'product'])
            
            web_search_results = ""
            if needs_web_search:
                try:
                    # Extract search query from user input
                    # If user mentions specific products, search for those
                    search_query = user_input
                    if "protein powder" in user_input.lower() or "protein" in user_input.lower():
                        search_query = f"best protein powders {user_input}"
                    
                    # Perform web search
                    web_search_result = self.tools["web_search"]._run(query=search_query)
                    web_search_results = f"\n\n## Web Search Results\n{web_search_result}\n\nUse the information above to provide actual links and product information. Do not use placeholder text - use the real URLs from the search results."
                    
                    # Log tool call if tracer available
                    if self.tracer:
                        self.tracer.log_tool_call(
                            tool_name="web_search",
                            tool_input={"query": search_query},
                            tool_output=web_search_result[:500] if len(web_search_result) > 500 else web_search_result
                        )
                except Exception as e:
                    # If web search fails, continue without it
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Web search failed: {e}")
            
            # Add web search results to prompt
            enhanced_prompt = f"{enhanced_prompt}{web_search_results}"
            
            # Get response from Gemini (direct SDK, no LangChain) with retry logic
            # Gemini SDK is synchronous, so we run it in executor for async compatibility
            import asyncio
            loop = asyncio.get_event_loop()
            
            # P0.3: Track original model name to detect fallback usage
            # Used to detect if model fallback occurred during execution
            original_model_name = self.model_name
            self._used_fallback_model = False  # Flag indicating if fallback was used
            self._fallback_info = None  # Fallback information (original model, fallback model, reason)
            
            def sync_generate_text():
                """
                Synchronous Gemini API call for text generation.
                
                This function calls Gemini API synchronously for text-only queries.
                It's run in an executor to make it compatible with async/await pattern.
                
                Returns:
                    Gemini API response
                """
                return self.model.generate_content(enhanced_prompt)
            
            async def async_generate_text():
                """
                Async wrapper for Gemini API call with timeout protection.
                
                This function wraps the synchronous Gemini call in an executor and
                adds timeout protection to prevent hanging on slow API responses.
                
                Returns:
                    Gemini API response
                    
                Raises:
                    TimeoutError: If API call exceeds timeout
                """
                # P1.1: Add timeout to Gemini call
                # Prevents hanging on slow API responses
                try:
                    return await asyncio.wait_for(
                        loop.run_in_executor(None, sync_generate_text),  # Run sync call in executor
                        timeout=self.llm_timeout  # Timeout in seconds
                    )
                except asyncio.TimeoutError:
                    timeout_msg = f"Gemini LLM call timed out after {self.llm_timeout} seconds"
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(timeout_msg)
                    if self.tracer:
                        self.tracer.log_timeout(self.llm_timeout, "Gemini LLM call")
                    raise TimeoutError(f"Request timed out after {self.llm_timeout} seconds. Please try again with a simpler query.")
            
            def update_gemini_model(new_model: str):
                """
                Update Gemini model if fallback is needed.
                
                This function updates the Gemini model instance to use a fallback model
                when the primary model fails. Used by retry logic for model fallback.
                
                Args:
                    new_model: Fallback model name (e.g., "gemini-2.0-flash-lite")
                """
                import google.generativeai as genai
                # Get API key (should be validated at startup)
                api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
                if not api_key:
                    raise ValueError(
                        "GOOGLE_GEMINI_API_KEY is not set. This should have been validated at startup. "
                        "Please restart the application with the key set in your environment variables."
                    )
                # Reconfigure Gemini API with fallback model
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(new_model)
                self.model_name = new_model
                # P0.3: Track fallback usage
                self._used_fallback_model = True
                self._fallback_info = {
                    "original_model": original_model_name,
                    "fallback_model": new_model,
                    "reason": "Model fallback due to errors"
                }
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Fell back to Gemini model: {new_model}")
            
            # Call Gemini API with retry logic and timeout protection
            # Retry logic handles transient errors with exponential backoff
            # Model fallback handles persistent errors by switching to cheaper model
            response = await retry_llm_call(
                func=async_generate_text,  # Async Gemini invocation function
                max_retries=3,  # Maximum retry attempts
                initial_delay=1.0,  # Initial delay before retry (seconds)
                max_delay=60.0,  # Maximum delay cap (seconds)
                tracer=self.tracer,  # Tracer for logging retries and token usage
                model_name=self.model_name,  # Current model name (for fallback)
                update_model_fn=update_gemini_model if self.model_name else None,  # Model update function
                service_name="gemini",  # Service name for circuit breaker
            )
            
            # Extract response text from Gemini API response
            # Gemini response has .text attribute containing the generated text
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            # Build result dictionary
            # Text-only queries don't include nutrition_analysis (only image analysis does)
            result = {
                "response": response_text,  # Agent's response
                "nutrition_analysis": None,  # No nutrition analysis for text-only queries
                "warnings": []  # No warnings for text-only queries (no dietary conflict checking)
            }
            # P0.3: Include degraded flag and fallback info if fallback model was used
            # Degraded mode indicates fallback model was used (service degradation)
            if hasattr(self, '_used_fallback_model') and self._used_fallback_model:
                result["degraded"] = True  # Fallback model was used
                result["fallback_info"] = getattr(self, '_fallback_info', None)  # Fallback model information
            else:
                result["degraded"] = False  # Primary model was used
            return result
            
        except Exception as e:
            return {
                "response": f"Error processing request: {str(e)}",
                "nutrition_analysis": None,
                "warnings": [f"Agent error: {str(e)}"],
                "degraded": False
            }

