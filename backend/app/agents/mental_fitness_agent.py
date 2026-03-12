"""
Mental Fitness Agent - Specialized agent for mental wellness, mindfulness, and stress management.

This module provides the MentalFitnessAgent class, which specializes in mental wellness
guidance, mindfulness practices, stress management, and mental health support. Unlike
other agents, this agent doesn't extend BaseAgent but implements similar functionality
using OpenAI directly.

Key Features:
- Mental wellness recommendations (meditation, mindfulness, stress management)
- Activity recommendations (breathing exercises, journaling, yoga)
- Mental fitness logging
- Medical history integration (especially important for mental health)
- Context-aware recommendations
- Wellness plan creation

Focus Areas:
- Stress management
- Anxiety and mood support
- Sleep improvement
- Focus and concentration
- Mindfulness practices
- Mental wellness activities

Medical Integration:
- Considers medical history (especially mental health conditions)
- Considers medications (may affect mental wellness practices)
- Provides safe, appropriate recommendations

Technical Approach:
- Uses OpenAI (same as Physical Fitness Agent)
- Modern LangChain tool binding
- Manual tool calling pattern
- Retry logic with model fallback
- Timeout protection for API calls
"""

from typing import Dict, Any, Optional
import asyncio
import logging
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
import os

from app.agents.base_agent import (
    GetMedicalHistoryTool,
    GetUserPreferencesTool,
    CreateMentalFitnessLogTool,
    WebSearchTool
)
from app.services.medical_service import get_medical_history
from app.services.llm_retry import retry_llm_call
from app.models.user_preferences import UserPreferences
from app.models.conversation_message import ConversationMessage
from langchain_core.messages import AIMessage


class MentalFitnessAgent:
    """
    Mental Fitness Agent specialized for mindfulness, stress management, and mental wellness.
    
    This agent provides mental wellness guidance, mindfulness practices, and stress
    management recommendations. It uses OpenAI with modern LangChain tool binding.
    
    Key Capabilities:
        - Mental wellness recommendations (meditation, mindfulness, stress management)
        - Activity recommendations (breathing exercises, journaling, yoga)
        - Mental fitness logging
        - Wellness plan creation
        - Medical history integration (especially important for mental health)
        
    Medical Considerations:
        - Considers medical history (mental health conditions, medications)
        - Provides safe, appropriate recommendations
        - Avoids recommending practices that may conflict with conditions/medications
        
    Focus Areas:
        - Stress management
        - Anxiety and mood support
        - Sleep improvement
        - Focus and concentration
        - Mindfulness practices
        - Mental wellness activities
        
    Attributes:
        user_id: User ID for user-specific operations
        db: Database session for querying user data
        model_name: LLM model name (default: "gpt-4.1")
        _shared_context: Shared user context from ContextManager (optional)
        tracer: AgentTracer instance for observability (optional)
        llm_timeout: Timeout for LLM calls in seconds (default: 60s)
        llm: ChatOpenAI instance
        tools: List of tools available to the agent
        llm_with_tools: LLM with tools bound (for tool calling)
        system_message: System prompt for mental fitness agent
        _user_context_summary: Cached user context summary
        _context_fetched: Flag indicating if context has been fetched
    """
    
    def __init__(
        self, 
        user_id: int, 
        db: Session, 
        model_name: str = "gpt-4.1",
        shared_context: Optional[Dict[str, Optional[Dict]]] = None,
        tracer: Optional[Any] = None,
        llm_timeout: float = 60.0  # P1.1: Timeout for LLM calls in seconds (default: 60s)
    ):
        """
        Initialize MentalFitnessAgent with OpenAI configuration.
        
        Args:
            user_id: User ID for user-specific operations
            db: Database session for querying user data
            model_name: LLM model name (default: "gpt-4.1")
            shared_context: Shared user context from ContextManager (optional)
                          Includes medical history and preferences
            tracer: AgentTracer instance for observability (optional)
            llm_timeout: Timeout for LLM calls in seconds (default: 60s)
                        Prevents hanging on slow API responses
            
        Initialization Steps:
            1. Store user_id, db, and configuration
            2. Store shared context and tracer
            3. Validate and configure OpenAI API key
            4. Initialize OpenAI LLM
            5. Initialize tools (medical history, preferences, mental fitness log, web search)
            6. Bind tools to LLM (modern LangChain approach)
            7. Build and cache system prompt
            8. Initialize context caching
            
        Note:
            - Raises ValueError if OPENAI_API_KEY is not set
            - Uses OpenAI (same as Physical Fitness Agent)
            - Tools are bound to LLM for automatic tool calling
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
        
        # Get API key from environment
        # Required for OpenAI API access
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set in environment variables. "
                "Please set it in your .env file or environment."
            )
        
        # Initialize LLM with API key
        # Store model name for retry fallback logic
        self.model_name = model_name  # Store for retry fallback logic
        # Temperature: 0.7 (balanced creativity and consistency)
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.7,  # Balanced creativity and consistency
            openai_api_key=api_key
        )
        
        # Initialize tools available to the agent
        # Tools are initialized with user_id and db for user-specific operations
        self.tools = [
            GetMedicalHistoryTool(user_id=user_id, db=db),  # Get user's medical history
            GetUserPreferencesTool(user_id=user_id, db=db),  # Get user's preferences
            CreateMentalFitnessLogTool(user_id=user_id, db=db),  # Create mental fitness log entries
            WebSearchTool(),  # Web search for mental wellness resources (no user_id or db needed - global)
        ]
        
        # Bind tools to LLM for modern LangChain approach
        # This enables the LLM to call tools during conversation
        # Modern approach: tools bound directly to LLM (no deprecated AgentExecutor)
        self.llm_with_tools = self.llm.bind_tools(self.tools)
        
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
            str: Agent type identifier ("mental_fitness")
            
        Note:
            - Used for prompt caching (static and enhanced prompts)
            - Used for identification in logs and traces
        """
        return "mental_fitness"
    
    def _get_system_prompt(self) -> str:
        """
        Get specialized system prompt for mental fitness agent.
        
        This method retrieves the system prompt for the mental fitness agent,
        checking cache first, then building if not cached.
        
        Returns:
            str: System prompt for mental fitness agent
            
        Prompt Strategy:
            1. Check cache first (static prompt cache)
            2. If cached, return cached prompt
            3. If not cached, build prompt from mental_fitness_prompt module
            4. Cache the built prompt for future use
            
        Note:
            - Uses prompt caching to reduce token usage
            - Static prompts are cached indefinitely (version-based invalidation)
            - Prompt includes mental wellness guidelines and safety instructions
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
        from app.agents.prompts.mental_fitness_prompt import get_mental_fitness_prompt
        return get_mental_fitness_prompt()

    def _get_user_context_summary(self) -> str:
        """
        Get minimal summary of user context for mental fitness agent.
        
        This method creates a brief summary of user context (medical history,
        medications, goals) to minimize token usage. Used when full context
        is not available.
        
        Returns:
            str: Brief context summary (max 150 chars) or empty string
            
        Context Summary Includes:
            - Medical conditions (truncated to 50 chars)
            - Medications (truncated to 40 chars)
            - Goals (truncated to 40 chars)
            
        Format:
            "Medical: ... | Meds: ... | Goals: ..."
            
        Note:
            - Uses shared context if available (reduces database queries)
            - Falls back to database queries if shared context not available
            - Summary is cached per agent instance
            - Minimal token usage (max 150 chars total)
        """
        if self._context_fetched and self._user_context_summary:
            return self._user_context_summary
        
        summary_parts = []
        
        # Use shared context if provided (from ContextManager)
        if self._shared_context:
            # Get medical history from shared context - especially important for mental health
            medical_history = self._shared_context.get("medical_history")
            if medical_history:
                if medical_history.get("conditions"):
                    conditions = medical_history["conditions"].strip()
                    if conditions:
                        if len(conditions) > 50:
                            conditions = conditions[:47] + "..."
                        summary_parts.append(f"Medical: {conditions}")
                
                if medical_history.get("medications"):
                    medications = medical_history["medications"].strip()
                    if medications:
                        if len(medications) > 40:
                            medications = medications[:37] + "..."
                        summary_parts.append(f"Meds: {medications}")
            
            # Get user preferences from shared context
            preferences = self._shared_context.get("preferences")
            if preferences:
                if preferences.get("goals"):
                    goals = preferences["goals"].strip()
                    if goals:
                        if len(goals) > 40:
                            goals = goals[:37] + "..."
                        summary_parts.append(f"Goals: {goals}")
            
            self._user_context_summary = " | ".join(summary_parts) if summary_parts else ""
            self._context_fetched = True
            return self._user_context_summary
        
        # Fallback: Fetch context independently (for backward compatibility)
        # Get medical history - especially important for mental health
        medical_history = get_medical_history(self.user_id, self.db)
        if medical_history:
            if medical_history.conditions:
                conditions = medical_history.conditions.strip()
                if len(conditions) > 50:
                    conditions = conditions[:47] + "..."
                summary_parts.append(f"Medical: {conditions}")
            
            if medical_history.medications:
                medications = medical_history.medications.strip()
                if len(medications) > 40:
                    medications = medications[:37] + "..."
                summary_parts.append(f"Meds: {medications}")
        
        # Get user preferences for activity level and goals
        preferences = self.db.query(UserPreferences).filter(
            UserPreferences.user_id == self.user_id
        ).first()
        
        if preferences:
            if preferences.goals:
                goals = preferences.goals.strip()
                if len(goals) > 40:
                    goals = goals[:37] + "..."
                summary_parts.append(f"Goals: {goals}")
        
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
            
            # Include full medical history if available (especially important for mental health)
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
            
            # Include full user preferences if available
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
                
                if pref_parts:
                    context_parts.append("## User Preferences\n" + "\n".join(pref_parts))
            
            # Add context section if we have any context
            if context_parts:
                context_section = "\n\n".join(context_parts)
                base_prompt += f"\n\n## User Context (Available Information)\n{context_section}"
                base_prompt += "\n\n**IMPORTANT**: You have full user context above. Only call tools (get_medical_history, get_user_preferences) if you need information NOT provided above or if the context seems outdated. For real-time information (web search, conversation history) or actions (creating logs), use tools as needed."
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
    
    def _append_web_search_links(self, response: str, web_search_urls: list) -> str:
        """
        Append formatted web search links at the end of the response.
        
        Formats URLs collected from web_search tool calls and appends them
        at the end of the agent's response in the specified format.
        
        Args:
            response: Agent's response text
            web_search_urls: List of (title, url) tuples from web_search calls
            
        Returns:
            Response with links section appended (if any URLs were found)
        """
        if not web_search_urls:
            return response
        
        # Format links section as specified: "1. <name of link URL>"
        links_section = "\n\n---\n\nLinks Referred\n\n"
        
        for idx, (title, url) in enumerate(web_search_urls, start=1):
            # Format: "1. Title URL" (name of link followed by URL)
            link_name = title if title else url
            links_section += f"{idx}. {link_name} {url}\n"
        
        links_section += "\n---"
        
        return response + links_section
    
    async def recommend_practice(self, user_query: str) -> Dict[str, Any]:
        """
        Main method to handle user queries for mental wellness recommendations.
        
        This method processes user queries for mental wellness guidance, mindfulness
        practices, stress management, and mental health support. It implements a
        tool-calling loop where the LLM can call tools, receive results, and continue
        the conversation until a final response is generated.
        
        Execution Flow:
            1. Build enhanced system prompt with full user context
            2. Initialize message history with system and user messages
            3. Loop (max 5 iterations):
               a. Get LLM response (with retry logic and timeout)
               b. Check if LLM wants to call tools
               c. Execute tools
               d. Add tool results to message history
               e. Continue loop or return final response
            4. Return final response
        
        Tool Calling:
            - LLM decides to call tool(s) based on user input
            - Tools are executed (medical history, preferences, mental fitness log, web search)
            - Tool results are added to message history
            - LLM processes tool results and generates response
            - Loop continues until no more tool calls or max iterations reached
        
        Args:
            user_query: User's query requesting mental wellness guidance
                       Examples: "Help me manage stress", "Suggest meditation practices",
                                "Create a mindfulness plan"
        
        Returns:
            Dict[str, Any]: Response dictionary:
                {
                    "response": str,  # Agent's mental wellness recommendation
                    "warnings": List[str] or None,  # Warnings (if any)
                    "degraded": bool,  # True if fallback model was used
                    "fallback_info": Dict or None  # Fallback model information
                }
                
        Error Handling:
            - API key errors: Returns informative error message
            - Timeout errors: Logs timeout and raises user-friendly error
            - Tool errors: Handled gracefully with error messages
            - Model fallback: Automatically falls back to cheaper model on errors
            
        Note:
            - Uses modern LangChain approach (tools bound to LLM)
            - Includes full context upfront to reduce tool calls
            - Implements retry logic with exponential backoff
            - Supports model fallback for degraded service handling
            - Maximum 5 iterations to prevent infinite loops
        """
        try:
            # Build enhanced system message with full context to reduce tool calls
            # Strategy: Include more context upfront to reduce tool calls, offsetting larger prompt cost
            # Enhanced prompt includes full medical history and preferences
            enhanced_system_message = self._build_enhanced_system_prompt()
            
            # Load recent conversation history for context
            # This allows agents to recall previous messages in the conversation
            conversation_messages = []
            try:
                # Get recent conversation history for this agent type (last 20 messages)
                # This provides context for follow-up questions and maintains conversation flow
                agent_type = "mental-fitness"
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
            # System message includes full user context
            # Conversation history provides context from previous messages
            # Human message contains user's current input
            messages = [
                SystemMessage(content=enhanced_system_message),  # Enhanced system prompt with context
            ]
            # Add conversation history before current message
            messages.extend(conversation_messages)
            # Add current user input
            messages.append(HumanMessage(content=user_query))  # User's current input query
            
            # Maximum iterations to prevent infinite loops
            # Prevents agent from getting stuck in tool-calling loops
            max_iterations = 5  # Prevent infinite loops
            iteration = 0
            
            # P0.3: Track original model name to detect fallback usage
            # Used to detect if model fallback occurred during execution
            original_model_name = getattr(self, 'model_name', None) or getattr(self.llm, 'model_name', None)
            self._used_fallback_model = False  # Flag indicating if fallback was used
            self._fallback_info = None  # Fallback information (original model, fallback model, reason)
            
            # Track URLs from web_search tool calls for formatting at end
            web_search_urls = []  # List of (title, url) tuples from web_search calls
            
            # Tool-calling loop: Continue until no more tool calls or max iterations reached
            while iteration < max_iterations:
                # Get LLM response with potential tool calls (with retry logic and timeout)
                # Wrapped in async function for retry logic
                async def invoke_llm():
                    """
                    Invoke LLM with timeout protection.
                    
                    This function wraps the LLM call with timeout protection to prevent
                    hanging on slow API responses.
                    """
                    # P1.1: Add timeout to LLM call
                    # Prevents hanging on slow API responses
                    try:
                        return await asyncio.wait_for(
                            self.llm_with_tools.ainvoke(messages),  # LLM call with tools bound
                            timeout=self.llm_timeout  # Timeout in seconds
                        )
                    except asyncio.TimeoutError:
                        # P1.1: Log timeout and raise user-friendly error
                        timeout_msg = f"LLM call timed out after {self.llm_timeout} seconds"
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(timeout_msg)
                        if self.tracer:
                            self.tracer.log_timeout(self.llm_timeout, "LLM call")
                        raise TimeoutError(f"Request timed out after {self.llm_timeout} seconds. Please try again with a simpler query.")
                
                def update_openai_model(new_model: str):
                    """
                    Update OpenAI model if fallback is needed.
                    
                    This function updates the LLM instance to use a fallback model
                    when the primary model fails. Used by retry logic for model fallback.
                    
                    Args:
                        new_model: Fallback model name (e.g., "gpt-3.5-turbo")
                    """
                    # Create new LLM instance with fallback model
                    self.llm = ChatOpenAI(
                        model=new_model,
                        temperature=0.7,  # Same temperature as original
                        openai_api_key=os.getenv("OPENAI_API_KEY")
                    )
                    # Re-bind tools to new LLM instance
                    self.llm_with_tools = self.llm.bind_tools(self.tools)
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
                    logger.info(f"Fell back to model: {new_model}")
                
                # Get model name from llm if available
                # Used for retry logic fallback
                model_name = getattr(self.llm, 'model_name', None) or getattr(self, 'model_name', None)
                
                # Call LLM with retry logic and timeout protection
                # Retry logic handles transient errors with exponential backoff
                # Model fallback handles persistent errors by switching to cheaper model
                response = await retry_llm_call(
                    func=invoke_llm,  # LLM invocation function
                    max_retries=3,  # Maximum retry attempts
                    initial_delay=1.0,  # Initial delay before retry (seconds)
                    max_delay=60.0,  # Maximum delay cap (seconds)
                    tracer=self.tracer if hasattr(self, 'tracer') else None,  # Tracer for logging retries and token usage
                    model_name=model_name,  # Current model name (for fallback)
                    update_model_fn=update_openai_model if model_name else None,  # Model update function
                    service_name="openai",  # Service name for circuit breaker
                )
                messages.append(response)  # Add LLM response to message history
                
                # Check if LLM wants to call tools
                # Tool calls are indicated by response.tool_calls attribute
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    # Execute tool calls
                    # LLM can call multiple tools in parallel
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get('name', '')  # Tool name (e.g., "get_medical_history")
                        tool_args = tool_call.get('args', {})  # Tool input arguments
                        tool_call_id = tool_call.get('id', '')  # Tool call ID for matching results
                        
                        # Find and execute the tool
                        # Search through available tools to find matching tool
                        tool = next((t for t in self.tools if t.name == tool_name), None)
                        if tool:
                            try:
                                # Execute tool based on type
                                # All tools use same _run() method signature
                                if tool_name == "create_mental_fitness_log":
                                    result = tool._run(**tool_args)
                                elif tool_name == "web_search":
                                    result = tool._run(**tool_args)
                                    
                                    # Extract URLs from web_search tool results
                                    if result:
                                        import re
                                        title_url_pattern = r'Title:\s*([^\n]+)\nURL:\s*(https?://[^\s\n]+)'
                                        url_pattern = r'URL:\s*(https?://[^\s\n]+)'
                                        
                                        matches = re.findall(title_url_pattern, str(result))
                                        for title, url in matches:
                                            if url not in [u for _, u in web_search_urls]:
                                                web_search_urls.append((title.strip(), url))
                                        
                                        if not matches:
                                            urls = re.findall(url_pattern, str(result))
                                            for url in urls:
                                                if url not in [u for _, u in web_search_urls]:
                                                    web_search_urls.append(("", url))
                                elif tool_name == "get_medical_history":
                                    result = tool._run(**tool_args)
                                elif tool_name == "get_user_preferences":
                                    result = tool._run(**tool_args)
                                else:
                                    result = tool._run(**tool_args)
                                
                                # Add tool message to conversation
                                # ToolMessage links result to tool call via tool_call_id
                                messages.append(ToolMessage(
                                    content=result,  # Tool result as string
                                    tool_call_id=tool_call_id  # Link to original tool call
                                ))
                            except Exception as e:
                                # Handle tool execution errors gracefully
                                # Add error message to conversation instead of failing
                                messages.append(ToolMessage(
                                    content=f"Error executing {tool_name}: {str(e)}",
                                    tool_call_id=tool_call_id
                                ))
                    iteration += 1
                    continue  # Continue loop to process tool results
                else:
                    # No more tool calls, return final response
                    # LLM has generated final response without needing more tools
                    final_response = response.content if hasattr(response, 'content') else str(response)
                    # Append web search URLs at the end if any were collected
                    final_response = self._append_web_search_links(final_response, web_search_urls)
                    result = {
                        "response": final_response,  # Agent's mental wellness recommendation
                        "warnings": []  # No warnings for mental fitness agent (no conflict checking)
                    }
                    # P0.3: Include degraded flag and fallback info if fallback model was used
                    # Degraded mode indicates fallback model was used (service degradation)
                    if hasattr(self, '_used_fallback_model') and self._used_fallback_model:
                        result["degraded"] = True  # Fallback model was used
                        result["fallback_info"] = getattr(self, '_fallback_info', None)  # Fallback model information
                    else:
                        result["degraded"] = False  # Primary model was used
                    return result
            
            # Max iterations reached
            # Prevents infinite loops by returning last response after max iterations
            final_response = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
            # Append web search URLs at the end if any were collected
            final_response = self._append_web_search_links(final_response, web_search_urls)
            result = {
                "response": final_response,  # Last response from message history
                "warnings": []  # No warnings
            }
            # P0.3: Include degraded flag and fallback info if fallback model was used
            if hasattr(self, '_used_fallback_model') and self._used_fallback_model:
                result["degraded"] = True
                result["fallback_info"] = getattr(self, '_fallback_info', None)
            else:
                result["degraded"] = False
            return result
            
        except Exception as e:
            # Handle errors gracefully
            # Returns error message instead of raising exception
            return {
                "response": f"Error processing request: {str(e)}",
                "warnings": [f"Agent error: {str(e)}"],
                "degraded": False
            }
    
    async def create_wellness_plan(self, focus_area: str = None, duration_minutes: int = 10) -> str:
        """
        Create a structured mental wellness plan for the user.
        
        This method creates a structured mental wellness plan with specified duration
        and optional focus area. It uses recommend_practice() to generate the plan
        with medical history consideration.
        
        Args:
            focus_area: Optional focus area (e.g., "stress", "sleep", "anxiety", "focus")
                       If provided, plan focuses on this specific area
            duration_minutes: Duration for daily practice in minutes (default: 10)
                            Plan is tailored to fit this duration
        
        Returns:
            str: Structured mental wellness plan response
            
        Plan Creation:
            - Builds query requesting wellness plan
            - Includes duration and optional focus area
            - Explicitly requests medical history check for safety
            - Uses recommend_practice() for plan generation
            
        Safety Features:
            - Checks medical history before creating plan
            - Considers medications and mental health conditions
            - Provides safe, appropriate recommendations
            - Avoids practices that may conflict with conditions/medications
            
        Focus Areas:
            - Stress management
            - Sleep improvement
            - Anxiety support
            - Focus and concentration
            - General mental wellness
            
        Example:
            create_wellness_plan("stress", 15)
            -> Creates 15-minute stress management plan
            
        Note:
            - Uses recommend_practice() for comprehensive plan generation
            - Returns only response (warnings handled separately)
            - Plan is tailored to user's medical history and preferences
        """
        # Build query requesting wellness plan
        # Includes duration and optional focus area
        query = f"Create a {duration_minutes}-minute daily mental wellness plan"
        if focus_area:
            query += f" focused on {focus_area}"
        # Explicitly request medical history check for safety
        # Ensures plan is safe and appropriate for user's conditions/medications
        query += ". Make sure to check my medical history first and create a plan that's safe and appropriate for me."
        
        # Get wellness plan with medical history consideration
        # recommend_practice() includes full context and medical history checking
        result = await self.recommend_practice(query)
        return result["response"]  # Return only response (warnings handled separately)

