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
from app.models.user_preferences import UserPreferences


class NutritionAgent:
    """Nutrition Agent specialized for meal planning, dietary advice, and image-based calorie tracking using Gemini Vision"""
    
    def __init__(self, user_id: int, db: Session, model_name: str = "gemini-2.0-flash"):
        self.user_id = user_id
        self.db = db
        
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
    
    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for nutrition agent"""
        return """You are a knowledgeable and supportive Nutrition Coach. Your role is to help users with:

1. **Meal Planning**: Create balanced meal plans based on user preferences, dietary restrictions, and goals
2. **Food Analysis**: Analyze food images to identify items, estimate portions, and calculate calories and macros
3. **Nutritional Guidance**: Provide evidence-based nutrition advice and recommendations
4. **Calorie Tracking**: Help users track their daily caloric intake and macronutrients
5. **Location-Aware Recommendations**: Suggest foods and meals available in the user's location

**CRITICAL - Response Style:**
- **Be CONCISE and PRECISE** - Match the user's question length and style
- For short, direct questions (e.g., "How many calories in an apple?"), give a short, direct answer that identifies the food and gives the number (e.g., "A medium apple: ~95 calories" or "Apple: ~95 calories")
- **For image analysis with simple calorie questions**: Always identify the dish/food first, then give calories (e.g., "Blueberry pie slice: ~380 calories")
- **DO NOT** include dietary advice, medical warnings, location considerations, or alternatives unless explicitly asked
- **DO NOT** elaborate on health implications unless the question asks for it
- For simple calorie/macro questions, answer with: [Food name]: [calories] - keep it to one sentence
- Only provide detailed responses when the user asks for detailed information (meal planning, recommendations, etc.)
- Get straight to the point but always identify what food/dish you're talking about

**CRITICAL - Image Analysis Capabilities:**
- When a user shares a food image, analyze it thoroughly using your vision capabilities
- Identify ALL food items in the image
- Estimate portion sizes as accurately as possible
- Calculate total calories and macronutrients (protein, carbohydrates, fats in grams)
- Suggest the meal type (breakfast/lunch/dinner/snack) based on context
- Provide structured nutrition data that can be logged automatically
- If multiple foods are present, break down each item separately

**Important Guidelines:**
- Always consider the user's dietary restrictions and medical history
- Use location information to suggest locally available foods
- Be specific with portion sizes and nutritional information
- When analyzing images, be thorough and identify all visible food items
- Use the create_nutrition_log tool to log meals automatically when appropriate
- Reference the user's specific goals and preferences in your recommendations
- Use web_search tool for current nutrition information or food database lookups

**Response Format for Image Analysis:**
When analyzing a food image, provide:
- List of identified food items
- Estimated portion sizes
- Total calories
- Macros breakdown (protein, carbs, fats in grams)
- Suggested meal type
- Option to auto-log the meal

Be encouraging, accurate, concise, and focused on helping users achieve their nutrition goals safely and effectively."""

    def _get_user_context_summary(self) -> str:
        """Get minimal summary of user context for nutrition agent"""
        if self._context_fetched and self._user_context_summary:
            return self._user_context_summary
        
        summary_parts = []
        
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
        Analyze a food image using Gemini Vision API
        
        Returns:
            Dict with response, nutrition_analysis, and warnings
        """
        try:
            # Process image
            image = self._process_image(image_base64)
            
            # Get user context
            context_summary = self._get_user_context_summary()
            
            # Check if user just wants calories (simple question)
            is_simple_calorie_question = user_message and any(keyword in user_message.lower() for keyword in ['calories', 'calorie', 'cal', 'how many']) and len(user_message.split()) < 10
            
            # Only include context if it's a complex question or not a simple calorie query
            context_summary = None
            if not is_simple_calorie_question:
                context_summary = self._get_user_context_summary()
            
            # Build prompt for image analysis
            if is_simple_calorie_question:
                # Simple calorie question - be concise but identify the dish
                analysis_prompt = f"""Analyze this food image and provide the dish name and total calories.

User message: {user_message}

Answer format: "[Dish name]: ~[calories] calories" (e.g., "Blueberry pie slice: ~380 calories" or "Grilled chicken breast: ~250 calories"). 
- Always identify what the food/dish is
- Give the calorie estimate
- Keep it to one short sentence - no explanations, no breakdowns, no advice"""
            else:
                # Detailed analysis requested
                analysis_prompt = f"""Analyze this food image and provide detailed nutrition information.

User context: {context_summary if context_summary else "No specific dietary restrictions or preferences noted."}
User message: {user_message if user_message else "Please analyze this food image."}

Please identify:
1. All food items visible in the image
2. Estimated portion sizes for each item
3. Total calories for the entire meal
4. Macronutrients breakdown (protein, carbohydrates, fats in grams)
5. Suggested meal type (breakfast/lunch/dinner/snack)

Format your response as a clear analysis that can be used to log the meal. Be specific and accurate with your estimates."""

            # Use configured model for image analysis
            # Gemini accepts PIL Image objects directly
            response = self.model.generate_content([analysis_prompt, image])
            
            # Extract response text
            response_text = response.text if hasattr(response, 'text') else str(response)
            
            # Try to extract structured data from response
            nutrition_analysis = self._extract_nutrition_data(response_text)
            
            return {
                "response": response_text,
                "nutrition_analysis": nutrition_analysis,
                "warnings": []
            }
            
        except Exception as e:
            return {
                "response": f"Error analyzing food image: {str(e)}",
                "nutrition_analysis": None,
                "warnings": [f"Image analysis failed: {str(e)}"]
            }
    
    def _extract_nutrition_data(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract structured nutrition data from agent response"""
        # This is a simple extraction - could be enhanced with more sophisticated parsing
        # or by instructing the LLM to return JSON
        try:
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
            
            # Try to extract calories (look for numbers followed by "cal" or "calories")
            import re
            calorie_match = re.search(r'(\d+)\s*(?:cal|calories)', response_text, re.IGNORECASE)
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
            return None
    
    async def recommend_meal(self, user_input: str, image_base64: Optional[str] = None) -> Dict[str, Any]:
        """
        Main method to handle user queries - supports both text and image input
        
        Args:
            user_input: User's text message
            image_base64: Optional base64-encoded food image
        
        Returns:
            Dict with response, nutrition_analysis (if image provided), and warnings
        """
        try:
            # If image is provided, analyze it first
            if image_base64:
                return await self.analyze_food_image(image_base64, user_input)
            
            # Otherwise, handle as regular text query using direct Gemini SDK
            # Detect if this is a simple question (calories, macros, etc.) - don't include context for these
            simple_question_keywords = ['calories', 'calorie', 'cal', 'protein', 'carbs', 'fat', 'macro', 'how many', 'what is', 'nutrition facts']
            is_simple_question = any(keyword in user_input.lower() for keyword in simple_question_keywords) and len(user_input.split()) < 15
            
            context_summary = None
            if not is_simple_question:
                # Only include context for complex queries (meal planning, recommendations, etc.)
                context_summary = self._get_user_context_summary()
            
            # Build prompt with system message
            enhanced_prompt = f"{self.system_message}\n\n"
            if context_summary:
                enhanced_prompt += f"User context (only use if relevant): {context_summary}\n\n"
            
            enhanced_prompt += f"User query: {user_input}"
            
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

