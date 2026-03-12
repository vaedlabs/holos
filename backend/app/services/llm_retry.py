"""
Retry logic for LLM API calls with exponential backoff and model fallback.

This module provides robust retry mechanisms for LLM API calls, handling transient
errors, rate limits, and service degradation. It implements exponential backoff,
model fallback chains, and circuit breaker integration.

Key Features:
- Exponential backoff retry strategy
- Model fallback chains for degraded service handling
- Error classification (retryable vs non-retryable)
- Circuit breaker integration for service protection
- Token usage tracking
- Comprehensive error handling and logging

Retry Strategy:
- Exponential backoff: Delays increase exponentially (1s, 2s, 4s, ...)
- Maximum delay cap: Prevents excessive delays (default: 60 seconds)
- Retryable errors: Rate limits, timeouts, server errors, network issues
- Non-retryable errors: Authentication errors, invalid requests (fail immediately)

Model Fallback:
- Automatic fallback to cheaper/faster models when primary model fails
- Fallback chains defined in MODEL_FALLBACKS dictionary
- Used for rate limits (429) and other retryable errors
- Helps maintain service availability during API issues
"""

import asyncio
import logging
import os
from typing import Callable, Any, Optional, Dict
from functools import wraps
import time

from app.services.circuit_breaker import get_circuit_breaker, CircuitBreakerOpenError

# Logger instance for this module
# Used for logging retry attempts, fallbacks, and errors
logger = logging.getLogger(__name__)

# Model fallback mappings for automatic model downgrade
# Maps primary models to fallback models when errors occur
# Used for 429 errors (rate limits) and general model fallback chain
# Format: {primary_model: fallback_model}
# None indicates end of fallback chain (no further fallback available)
MODEL_FALLBACKS = {
    # Gemini models - fallback to lighter/faster models
    "gemini-2.0-flash": "gemini-2.0-flash-lite",  # Fallback to lite version
    "gemini-2.5-flash-lite": "gemini-2.0-flash-lite",  # If already on lite, stay on lite
    # OpenAI models - fallback to cheaper/faster models
    "gpt-5-mini": "gpt-5-nano",  # Fallback to nano version
    "gpt-4.1": "gpt-3.5-turbo",  # Fallback for current default model
    "gpt-4o": "gpt-3.5-turbo",  # Fallback to cheaper model
    "gpt-4": "gpt-3.5-turbo",  # Fallback to cheaper model
    "gpt-3.5-turbo": None,  # End of chain - no further fallback available
}


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error is retryable.
    
    This function classifies errors as retryable (transient) or non-retryable
    (permanent). Retryable errors are transient issues that may resolve on retry,
    while non-retryable errors are permanent failures that won't succeed on retry.
    
    Args:
        error: The exception that occurred
        
    Returns:
        bool: True if the error should be retried, False otherwise
        
    Retryable Errors (transient, may succeed on retry):
        - Rate limits (429): Temporary rate limit exceeded
        - Server errors (500, 502, 503, 504): Server-side issues
        - Timeout errors: Request took too long (may succeed on retry)
        - Network errors: Connection issues, network unreachable
        
    Non-Retryable Errors (permanent, won't succeed on retry):
        - Authentication errors (401): Invalid API key
        - Bad requests (400): Invalid request format
        - Validation errors (422): Invalid data
        
    Error Detection:
        - Checks error message string for error codes and keywords
        - Checks exception type for specific error classes
        - Handles both string-based and exception-type-based detection
        
    Note:
        - Retryable errors trigger retry logic with exponential backoff
        - Non-retryable errors fail immediately (no retries)
        - Error classification is conservative (errs on side of retrying)
    """
    error_str = str(error).lower()
    error_type = type(error).__name__
    
    # Check for rate limit (429) - temporary, should retry
    # Rate limits are transient and may resolve after delay
    if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
        return True
    
    # Check for server errors (500, 502, 503, 504) - transient server issues
    # Server errors are often transient and may resolve on retry
    if any(code in error_str for code in ["500", "502", "503", "504"]):
        return True
    
    # Check for timeout errors (including asyncio.TimeoutError and TimeoutError)
    # Timeouts may succeed on retry with exponential backoff
    if "timeout" in error_str or "timed out" in error_str:
        return True
    
    # Check for TimeoutError exception type
    # Handles both standard TimeoutError and asyncio.TimeoutError
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return True
    
    # Check for network errors - connection issues may resolve
    # Network errors are often transient (network hiccups, temporary outages)
    if any(term in error_str for term in ["connection", "network", "unreachable"]):
        return True
    
    # Don't retry on permanent failures
    # These errors won't succeed on retry - fail immediately
    if any(code in error_str for code in ["401", "400", "422"]):
        return False
    
    # Check for specific exception types from OpenAI SDK
    # APIConnectionError and APITimeoutError are retryable
    if "APIConnectionError" in error_type or "APITimeoutError" in error_type:
        return True
    
    return False


def is_429_error(error: Exception) -> bool:
    """
    Check if error is a 429 (rate limit) error.
    
    This function specifically identifies rate limit errors, which trigger
    special handling (model fallback after retries).
    
    Args:
        error: The exception that occurred
        
    Returns:
        bool: True if it's a 429 rate limit error
        
    Rate Limit Indicators:
        - HTTP status code 429
        - Error message containing "rate limit"
        - Error message containing "quota"
        
    Note:
        - 429 errors trigger model fallback after retries
        - Rate limits are temporary and may resolve with fallback model
        - Used to determine when to attempt model fallback
    """
    error_str = str(error).lower()
    return "429" in error_str or "rate limit" in error_str or "quota" in error_str


def get_fallback_model(model_name: str) -> Optional[str]:
    """
    Get fallback model for a given model name.
    
    This function looks up the fallback model for a given primary model.
    Fallback models are typically cheaper or faster alternatives used when
    the primary model fails or hits rate limits.
    
    Args:
        model_name: Current model name (e.g., "gpt-4.1", "gemini-2.0-flash")
        
    Returns:
        Optional[str]: Fallback model name if available, None if no fallback
        
    Fallback Chain:
        - Maps primary models to fallback models
        - Returns None if model has no fallback (end of chain)
        - Fallback models are typically cheaper/faster alternatives
        
    Example:
        get_fallback_model("gpt-4.1") -> "gpt-3.5-turbo"
        get_fallback_model("gpt-3.5-turbo") -> None (end of chain)
        
    Note:
        - Used when primary model fails after retries
        - Fallback models help maintain service availability
        - None return indicates no fallback available (will raise error)
    """
    return MODEL_FALLBACKS.get(model_name)


async def retry_llm_call(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    tracer: Optional[Any] = None,
    model_name: Optional[str] = None,
    update_model_fn: Optional[Callable[[str], None]] = None,
    service_name: Optional[str] = None,
    enable_model_fallback: bool = True,  # P0.3: Enable model fallback for all errors
) -> Any:
    """
    Retry an LLM API call with exponential backoff and model fallback.
    
    This function implements a robust retry mechanism for LLM API calls, handling
    transient errors, rate limits, and service degradation. It uses exponential
    backoff for retries and model fallback when retries are exhausted.
    
    Retry Flow:
        1. Attempt function call
        2. On retryable error: Wait with exponential backoff, retry
        3. On non-retryable error: Fail immediately
        4. After max_retries: Attempt model fallback (if available)
        5. If fallback succeeds: Return result
        6. If fallback fails: Raise exception
        
    Exponential Backoff:
        - Delay starts at initial_delay (default: 1 second)
        - Each retry doubles the delay: 1s, 2s, 4s, 8s, ...
        - Delay is capped at max_delay (default: 60 seconds)
        - Formula: delay = min(initial_delay * 2^attempt, max_delay)
        
    Model Fallback:
        - Triggered after max_retries exhausted
        - Always attempted for 429 errors (rate limits)
        - Optionally attempted for other retryable errors (if enable_model_fallback=True)
        - Falls back to cheaper/faster model from MODEL_FALLBACKS
        - Single attempt with fallback model (no retries)
        
    Circuit Breaker Integration:
        - If service_name provided, wraps retry logic with circuit breaker
        - Circuit breaker prevents calls when service is down
        - Returns user-friendly error if circuit is open
        
    Token Usage Tracking:
        - Extracts token usage from LLM response (if available)
        - Logs token usage to tracer for cost tracking
        - Supports both OpenAI and Gemini response formats
        
    Args:
        func: Async function to retry (must be awaitable)
        max_retries: Maximum number of retry attempts (default: 3)
                    Total attempts = max_retries + 1 (initial + retries)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 60.0)
                  Prevents excessive delays on repeated failures
        tracer: AgentTracer instance for logging retries and token usage (optional)
        model_name: Current model name for fallback logic (optional)
                   Used to determine fallback model when retries exhausted
        update_model_fn: Function to update model if fallback is needed (optional)
                        Called with fallback model name to switch models
        service_name: Service name for circuit breaker (optional)
                     Examples: "openai", "gemini"
        enable_model_fallback: Enable model fallback for all retryable errors (default: True)
                              If False, only 429 errors trigger fallback
                              If True, all retryable errors trigger fallback after retries
        
    Returns:
        Any: Result from the function call (LLM response)
        
    Raises:
        Exception: If all retries and fallback attempts fail
                  Original exception or fallback exception is raised
        
    Example:
        result = await retry_llm_call(
            func=lambda: llm.ainvoke(messages),
            max_retries=3,
            model_name="gpt-4.1",
            update_model_fn=lambda m: setattr(self, 'model', m),
            service_name="openai"
        )
    """
    # Get circuit breaker if service name provided
    # Circuit breaker prevents calls when service is consistently failing
    circuit_breaker = None
    if service_name:
        circuit_breaker = get_circuit_breaker(service_name, tracer)
    
    # Wrap the retry logic with circuit breaker if available
    # Inner function contains the actual retry logic
    async def retry_logic():
        """
        Inner function containing retry logic.
        
        This function implements the retry loop with exponential backoff and
        model fallback. It's wrapped by circuit breaker if available.
        """
        # Track last error for final exception if all retries fail
        last_error = None
        
        # Exponential backoff delay (starts at initial_delay)
        delay = initial_delay
        
        # Retry counter (for logging)
        retry_count = 0
        
        # Flag to track if fallback model was used
        used_fallback = False
        
        # Retry loop: max_retries + 1 total attempts (initial + retries)
        for attempt in range(max_retries + 1):
            try:
                # Execute the LLM API call
                # This is the actual function passed in (e.g., llm.ainvoke())
                result = await func()
                
                # If we used fallback model, log success with fallback
                # This helps track when fallback models are used successfully
                if used_fallback and tracer:
                    tracer.log_warning(f"Request succeeded with fallback model after {retry_count} retries")
                
                # Extract and log token usage if available
                # Token usage tracking helps with cost analysis
                # OpenAI format: response_metadata.token_usage
                if tracer and hasattr(result, 'response_metadata'):
                    usage = result.response_metadata.get('token_usage', {})
                    if usage:
                        total_tokens = usage.get('total_tokens', 0)
                        if total_tokens > 0:
                            tracer.log_tokens(total_tokens)
                # Gemini format: usage_metadata.total_token_count
                elif tracer and hasattr(result, 'usage_metadata'):
                    usage = result.usage_metadata
                    if hasattr(usage, 'total_token_count'):
                        tracer.log_tokens(usage.total_token_count)
                
                # Success - return result
                return result
            
            except Exception as e:
                # Store error for final exception if all retries fail
                last_error = e
                
                # Check if error is retryable (transient vs permanent)
                # Non-retryable errors fail immediately (no retries)
                if not is_retryable_error(e):
                    logger.warning(f"Non-retryable error: {e}")
                    raise
                
                # Record failure in circuit breaker if available
                # Circuit breaker tracks failure rate to determine if service is down
                if circuit_breaker:
                    # The circuit breaker will record the failure when we re-raise
                    pass
                
                # If this is the last attempt, try fallback model
                # Fallback is attempted after all retries are exhausted
                # P0.3: For 429 errors, always try fallback. For other retryable errors, try fallback if enabled.
                if attempt == max_retries and model_name and update_model_fn:
                    # Determine if we should try fallback model
                    should_try_fallback = False
                    fallback_reason = ""
                    
                    if is_429_error(e):
                        # Always try fallback for 429 errors (rate limits)
                        # Rate limits often resolve with cheaper/faster models
                        should_try_fallback = True
                        fallback_reason = "Rate limit exceeded"
                    elif enable_model_fallback:
                        # P0.3: Try fallback for all retryable errors if enabled
                        # Helps maintain service availability during API issues
                        should_try_fallback = True
                        fallback_reason = f"Error after {max_retries} retries"
                    
                    # Attempt model fallback if conditions are met
                    if should_try_fallback:
                        # Get fallback model from fallback chain
                        fallback_model = get_fallback_model(model_name)
                        if fallback_model:
                            logger.info(f"{fallback_reason}. Attempting fallback to {fallback_model}")
                            if tracer:
                                tracer.log_warning(f"{fallback_reason}. Falling back to {fallback_model}")
                            
                            # Update model to fallback model
                            # This switches the LLM instance to use the fallback model
                            update_model_fn(fallback_model)
                            used_fallback = True
                            
                            # Try one more time with fallback model
                            # Single attempt (no retries) with fallback model
                            try:
                                result = await func()
                                if tracer:
                                    tracer.log_warning(f"Request succeeded with fallback model {fallback_model}")
                                
                                # Extract token usage from fallback model response
                                # Token usage tracking for cost analysis
                                if tracer and hasattr(result, 'response_metadata'):
                                    usage = result.response_metadata.get('token_usage', {})
                                    if usage:
                                        total_tokens = usage.get('total_tokens', 0)
                                        if total_tokens > 0:
                                            tracer.log_tokens(total_tokens)
                                elif tracer and hasattr(result, 'usage_metadata'):
                                    usage = result.usage_metadata
                                    if hasattr(usage, 'total_token_count'):
                                        tracer.log_tokens(usage.total_token_count)
                                
                                # Fallback succeeded - return result
                                return result
                            except Exception as fallback_error:
                                # Fallback model also failed
                                # Log error and raise (no more fallback options)
                                logger.error(f"Fallback model also failed: {fallback_error}")
                                if tracer:
                                    tracer.log_warning(f"Fallback model {fallback_model} also failed")
                                raise fallback_error
                
                # If not last attempt, retry with exponential backoff
                # Last attempt already handled fallback logic above
                if attempt < max_retries:
                    retry_count = attempt + 1
                    logger.warning(f"LLM call failed (attempt {retry_count}/{max_retries + 1}): {e}. Retrying in {delay}s...")
                    
                    if tracer:
                        tracer.log_warning(f"LLM call failed, retrying (attempt {retry_count}/{max_retries + 1})")
                    
                    # Wait before retrying (exponential backoff)
                    # Delay increases exponentially: 1s, 2s, 4s, 8s, ...
                    await asyncio.sleep(delay)
                    
                    # Calculate next delay (exponential backoff with max limit)
                    # Formula: delay = min(delay * 2, max_delay)
                    # Prevents excessive delays while still backing off
                    delay = min(delay * 2, max_delay)  # Exponential backoff with max limit
        
        # All retries exhausted (and fallback failed if attempted)
        # Log final failure and raise exception
        logger.error(f"LLM call failed after {max_retries + 1} attempts: {last_error}")
        if tracer:
            tracer.log_warning(f"LLM call failed after {max_retries + 1} attempts")
        raise last_error
    
    # Execute retry logic with or without circuit breaker
    # Circuit breaker prevents calls when service is consistently failing
    if circuit_breaker:
        try:
            # Execute retry logic wrapped in circuit breaker
            # Circuit breaker tracks failures and opens circuit if threshold exceeded
            return await circuit_breaker.call(retry_logic)
        except CircuitBreakerOpenError as e:
            # Circuit is open - service is down, return user-friendly error immediately
            # Circuit breaker prevents calls when failure rate is too high
            logger.warning(f"Circuit breaker open for {service_name}: {e}")
            if tracer:
                tracer.log_warning(f"Circuit breaker prevented call to {service_name} - service unavailable")
            # Raise user-friendly error instead of technical exception
            raise Exception(
                f"Service temporarily unavailable. The {service_name} service is experiencing issues. "
                f"Please try again in a few moments."
            )
    else:
        # No circuit breaker - execute retry logic directly
        # Used when circuit breaker is not configured for this service
        return await retry_logic()


def with_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    model_name: Optional[str] = None,
    get_model_name_fn: Optional[Callable] = None,
    update_model_fn: Optional[Callable[[str], None]] = None,
):
    """
    Decorator for retrying LLM API calls with exponential backoff.
    
    This decorator provides an easy way to add retry logic to LLM API call methods.
    It automatically extracts model information, tracer, and creates update functions
    based on the method's context (OpenAI vs Gemini).
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 60.0)
        model_name: Current model name - can be:
                   - String: Direct model name (e.g., "gpt-4.1")
                   - Callable: Function that returns model name
                   - None: Auto-detect from method context
        get_model_name_fn: Function to get current model name (optional)
        update_model_fn: Function to update model if fallback is needed (optional)
                        If None, auto-detects based on method context (OpenAI/Gemini)
        
    Usage:
        # Simple usage with auto-detection
        @with_retry(max_retries=3)
        async def my_llm_call(self):
            return await self.llm.ainvoke(...)
        
        # Explicit model name and update function
        @with_retry(
            max_retries=3,
            model_name="gpt-4.1",
            update_model_fn=lambda m: setattr(self, 'model', m)
        )
        async def my_llm_call(self):
            return await self.llm.ainvoke(...)
    
    Auto-Detection:
        The decorator automatically detects:
        - Tracer: From self.tracer if available
        - Model name: From self.model_name or self.llm.model_name
        - Update function: Creates based on self.model (Gemini) or self.llm (OpenAI)
        
    Note:
        - Preserves function signature and metadata (@wraps)
        - Works with both OpenAI and Gemini agents
        - Automatically handles model fallback if update function is available
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get tracer from self if available
            # Tracer is used for logging retries and token usage
            tracer = None
            if args and hasattr(args[0], 'tracer'):
                tracer = args[0].tracer
            
            # Get model name from various sources (in priority order)
            # 1. Direct model_name parameter (string or callable)
            # 2. get_model_name_fn function
            # 3. self.model_name attribute
            # 4. self.llm.model_name attribute (for OpenAI)
            current_model = model_name
            if callable(model_name):
                # If model_name is callable, call it to get current model
                current_model = model_name()
            elif get_model_name_fn:
                # Use provided function to get model name
                current_model = get_model_name_fn()
            elif args and hasattr(args[0], 'model_name'):
                # Extract from self.model_name (common pattern)
                current_model = args[0].model_name
            elif args and hasattr(args[0], 'llm') and hasattr(args[0].llm, 'model_name'):
                # Extract from self.llm.model_name (OpenAI pattern)
                current_model = args[0].llm.model_name
            
            # Get update function for model fallback
            # If not provided, try to create one based on context
            update_fn = update_model_fn
            if not update_fn and args:
                # Try to create update function based on context
                # Detects if agent uses Gemini (self.model) or OpenAI (self.llm)
                obj = args[0]
                if hasattr(obj, 'model'):
                    # For Gemini agents (has self.model)
                    # Creates function to update Gemini model
                    def update_gemini_model(new_model: str):
                        import google.generativeai as genai
                        api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
                        if not api_key:
                            raise ValueError(
                                "GOOGLE_GEMINI_API_KEY is not set. This should have been validated at startup. "
                                "Please restart the application with the key set in your environment variables."
                            )
                        genai.configure(api_key=api_key)
                        obj.model = genai.GenerativeModel(new_model)
                        obj.model_name = new_model
                    update_fn = update_gemini_model
                elif hasattr(obj, 'llm'):
                    # For OpenAI agents (has self.llm)
                    # Creates function to update OpenAI model
                    def update_openai_model(new_model: str):
                        from langchain_openai import ChatOpenAI
                        import os
                        obj.llm = ChatOpenAI(
                            model=new_model,
                            temperature=obj.llm.temperature if hasattr(obj.llm, 'temperature') else 0.7,
                            openai_api_key=os.getenv("OPENAI_API_KEY")
                        )
                        obj.model_name = new_model
                    update_fn = update_openai_model
            
            # Call retry_llm_call with extracted/auto-detected parameters
            # Wraps original function call in lambda for retry logic
            return await retry_llm_call(
                func=lambda: func(*args, **kwargs),  # Wrap original function call
                max_retries=max_retries,
                initial_delay=initial_delay,
                max_delay=max_delay,
                tracer=tracer,  # Auto-detected or None
                model_name=current_model,  # Auto-detected or provided
                update_model_fn=update_fn,  # Auto-created or provided
            )
        return wrapper
    return decorator

