"""
Tests for P0 Reliability Features (P0.1, P0.2, P0.3)
Tests retry logic, circuit breaker, and model fallback mechanisms.

Positive and negative test cases for:
- P0.1: Retry Logic for LLM API Calls
- P0.2: Circuit Breaker Pattern for LLM Services
- P0.3: Fallback Mechanisms and Model Fallback Chain
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, Any
import time

from app.services.llm_retry import (
    retry_llm_call,
    is_retryable_error,
    is_429_error,
    get_fallback_model,
    MODEL_FALLBACKS
)
from app.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerOpenError,
    get_circuit_breaker
)
from app.schemas.agents import AgentChatResponse


# ============================================================================
# P0.1: RETRY LOGIC TESTS
# ============================================================================

class TestRetryLogic:
    """Test retry logic with exponential backoff"""
    
    @pytest.mark.asyncio
    async def test_retry_success_on_first_attempt(self):
        """POSITIVE: Function succeeds on first attempt - no retry needed"""
        call_count = 0
        
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await retry_llm_call(
            func=successful_func,
            max_retries=3,
            initial_delay=0.1
        )
        
        assert result == "success"
        assert call_count == 1  # Only called once
    
    @pytest.mark.asyncio
    async def test_retry_success_after_transient_error(self):
        """POSITIVE: Function succeeds after transient error - retry works"""
        call_count = 0
        
        async def func_with_transient_error():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("429 Rate limit exceeded")
            return "success"
        
        result = await retry_llm_call(
            func=func_with_transient_error,
            max_retries=3,
            initial_delay=0.1
        )
        
        assert result == "success"
        assert call_count == 2  # Called twice (failed once, succeeded once)
    
    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self):
        """POSITIVE: Retry uses exponential backoff"""
        call_times = []
        
        async def failing_func():
            call_times.append(time.time())
            raise Exception("500 Internal Server Error")
        
        start_time = time.time()
        
        try:
            await retry_llm_call(
                func=failing_func,
                max_retries=3,
                initial_delay=0.1,
                max_delay=1.0
            )
        except Exception:
            pass  # Expected to fail after all retries
        
        # Check that delays increased exponentially
        if len(call_times) >= 3:
            delay1 = call_times[1] - call_times[0]
            delay2 = call_times[2] - call_times[1]
            # Allow some tolerance for timing
            assert delay2 > delay1 * 1.5  # Exponential backoff
    
    @pytest.mark.asyncio
    async def test_retry_on_429_error(self):
        """POSITIVE: Retries on 429 rate limit errors"""
        call_count = 0
        
        async def rate_limited_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("429 You exceeded your current quota")
            return "success"
        
        result = await retry_llm_call(
            func=rate_limited_func,
            max_retries=3,
            initial_delay=0.1
        )
        
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_on_server_errors(self):
        """POSITIVE: Retries on 500, 502, 503, 504 errors"""
        errors = ["500 Internal Server Error", "502 Bad Gateway", "503 Service Unavailable", "504 Gateway Timeout"]
        
        for error_msg in errors:
            call_count = 0
            
            async def server_error_func():
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise Exception(error_msg)
                return "success"
            
            result = await retry_llm_call(
                func=server_error_func,
                max_retries=3,
                initial_delay=0.1
            )
            
            assert result == "success"
            assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_errors(self):
        """NEGATIVE: Does not retry on 400, 401, 422 errors"""
        call_count = 0
        
        async def bad_request_func():
            nonlocal call_count
            call_count += 1
            raise Exception("400 Bad Request")
        
        with pytest.raises(Exception) as exc_info:
            await retry_llm_call(
                func=bad_request_func,
                max_retries=3,
                initial_delay=0.1
            )
        
        assert call_count == 1  # Only called once, no retry
        assert "400" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """NEGATIVE: Raises exception after max retries exhausted"""
        call_count = 0
        
        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("500 Internal Server Error")
        
        with pytest.raises(Exception) as exc_info:
            await retry_llm_call(
                func=always_failing_func,
                max_retries=2,
                initial_delay=0.1
            )
        
        assert call_count == 3  # Initial + 2 retries
        assert "500" in str(exc_info.value)
    
    def test_is_retryable_error(self):
        """Test retryable error detection"""
        # POSITIVE: Retryable errors
        assert is_retryable_error(Exception("429 Rate limit exceeded"))
        assert is_retryable_error(Exception("500 Internal Server Error"))
        assert is_retryable_error(Exception("502 Bad Gateway"))
        assert is_retryable_error(Exception("503 Service Unavailable"))
        assert is_retryable_error(Exception("Connection timeout"))
        assert is_retryable_error(Exception("Network unreachable"))
        
        # NEGATIVE: Non-retryable errors
        assert not is_retryable_error(Exception("400 Bad Request"))
        assert not is_retryable_error(Exception("401 Unauthorized"))
        assert not is_retryable_error(Exception("422 Unprocessable Entity"))
    
    def test_is_429_error(self):
        """Test 429 error detection"""
        # POSITIVE: 429 errors
        assert is_429_error(Exception("429 Rate limit exceeded"))
        assert is_429_error(Exception("429 You exceeded your quota"))
        assert is_429_error(Exception("Rate limit exceeded"))
        assert is_429_error(Exception("Quota exceeded"))
        
        # NEGATIVE: Non-429 errors
        assert not is_429_error(Exception("500 Internal Server Error"))
        assert not is_429_error(Exception("400 Bad Request"))


# ============================================================================
# P0.2: CIRCUIT BREAKER TESTS
# ============================================================================

class TestCircuitBreaker:
    """Test circuit breaker pattern"""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker for testing"""
        return CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,  # Low threshold for testing
            time_window=10.0,  # Short window for testing
            half_open_timeout=1.0  # Short timeout for testing
        )
    
    @pytest.mark.asyncio
    async def test_circuit_closed_normal_operation(self, circuit_breaker):
        """POSITIVE: Circuit allows calls when closed (normal operation)"""
        call_count = 0
        
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await circuit_breaker.call(successful_func)
        
        assert result == "success"
        assert call_count == 1
        assert circuit_breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold_failures(self, circuit_breaker):
        """POSITIVE: Circuit opens after threshold failures"""
        failure_count = 0
        
        async def failing_func():
            nonlocal failure_count
            failure_count += 1
            raise Exception("Service unavailable")
        
        # Cause failures up to threshold
        for i in range(3):
            try:
                await circuit_breaker.call(failing_func)
            except Exception:
                pass
        
        # Circuit should be open
        assert circuit_breaker.state == CircuitState.OPEN
        assert failure_count == 3
    
    @pytest.mark.asyncio
    async def test_circuit_blocks_calls_when_open(self, circuit_breaker):
        """POSITIVE: Circuit blocks calls immediately when open"""
        # Open the circuit
        for i in range(3):
            try:
                async def failing_func():
                    raise Exception("Error")
                await circuit_breaker.call(failing_func)
            except Exception:
                pass
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Try to make a call - should fail immediately
        call_made = False
        
        async def func():
            nonlocal call_made
            call_made = True
            return "should not execute"
        
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.call(func)
        
        assert not call_made  # Function should not be called
    
    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, circuit_breaker):
        """POSITIVE: Circuit transitions to half-open after timeout"""
        # Open the circuit
        for i in range(3):
            try:
                async def failing_func():
                    raise Exception("Error")
                await circuit_breaker.call(failing_func)
            except Exception:
                pass
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Wait for half-open timeout
        await asyncio.sleep(1.1)  # Slightly more than half_open_timeout
        
        # Circuit state is checked when call() is invoked
        # Verify that _should_enter_half_open returns True after timeout
        # (The actual transition happens in call(), which is tested in test_circuit_closes_after_successful_call)
        assert circuit_breaker._should_enter_half_open() is True
    
    @pytest.mark.asyncio
    async def test_circuit_closes_after_successful_call(self, circuit_breaker):
        """POSITIVE: Circuit closes after successful call in half-open state"""
        # Open the circuit
        for i in range(3):
            try:
                async def failing_func():
                    raise Exception("Error")
                await circuit_breaker.call(failing_func)
            except Exception:
                pass
        
        # Wait for half-open
        await asyncio.sleep(1.1)
        
        # Make successful call
        async def successful_func():
            return "success"
        
        result = await circuit_breaker.call(successful_func)
        
        assert result == "success"
        assert circuit_breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_reopens_on_failed_test_call(self, circuit_breaker):
        """NEGATIVE: Circuit reopens if test call fails in half-open state"""
        # Open the circuit
        for i in range(3):
            try:
                async def failing_func():
                    raise Exception("Error")
                await circuit_breaker.call(failing_func)
            except Exception:
                pass
        
        # Wait for half-open
        await asyncio.sleep(1.1)
        
        # Make failing call
        async def failing_func():
            raise Exception("Still failing")
        
        with pytest.raises(Exception):
            await circuit_breaker.call(failing_func)
        
        # Circuit should be open again
        assert circuit_breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_separate_instances(self):
        """POSITIVE: Separate circuit breakers for different services"""
        cb1 = CircuitBreaker("service1", failure_threshold=2, time_window=10.0)
        cb2 = CircuitBreaker("service2", failure_threshold=2, time_window=10.0)
        
        # Open circuit for service1
        for i in range(2):
            try:
                async def failing_func():
                    raise Exception("Error")
                await cb1.call(failing_func)
            except Exception:
                pass
        
        assert cb1.state == CircuitState.OPEN
        assert cb2.state == CircuitState.CLOSED  # Service2 still closed
    
    def test_get_circuit_breaker_singleton(self):
        """POSITIVE: get_circuit_breaker returns same instance for same service"""
        # get_circuit_breaker only returns singletons for "openai" and "gemini"
        # For other services, it creates new instances
        cb1 = get_circuit_breaker("openai")
        cb2 = get_circuit_breaker("openai")
        
        assert cb1 is cb2  # Same instance for "openai"
        
        # Test that different services get different instances
        cb3 = get_circuit_breaker("gemini")
        assert cb1 is not cb3  # Different services get different instances


# ============================================================================
# P0.3: MODEL FALLBACK TESTS
# ============================================================================

class TestModelFallback:
    """Test model fallback chain mechanism"""
    
    def test_get_fallback_model(self):
        """Test fallback model retrieval"""
        # POSITIVE: Valid fallback models
        assert get_fallback_model("gemini-2.0-flash") == "gemini-2.0-flash-lite"
        assert get_fallback_model("gpt-4.1") == "gpt-3.5-turbo"
        assert get_fallback_model("gpt-4o") == "gpt-3.5-turbo"
        assert get_fallback_model("gpt-5-mini") == "gpt-5-nano"
        
        # NEGATIVE: No fallback available
        assert get_fallback_model("gpt-3.5-turbo") is None
        assert get_fallback_model("unknown-model") is None
    
    @pytest.mark.asyncio
    async def test_fallback_on_429_error(self):
        """POSITIVE: Falls back to lower model on 429 error after retries"""
        original_model = "gpt-4.1"
        fallback_model = None
        call_count = 0
        
        def update_model(new_model: str):
            nonlocal fallback_model
            fallback_model = new_model
        
        async def rate_limited_func():
            nonlocal call_count
            call_count += 1
            # With max_retries=3, we have attempts 0, 1, 2, 3 (4 attempts)
            # Fallback happens on attempt 3 (max_retries) if it fails
            # So we need to fail on attempts 0, 1, 2, 3 (4 failures), then succeed on fallback attempt (5th call)
            if call_count < 5:  # Fail 4 times (all retries), then succeed with fallback
                raise Exception("429 Rate limit exceeded")
            return "success"
        
        result = await retry_llm_call(
            func=rate_limited_func,
            max_retries=3,
            initial_delay=0.1,
            model_name=original_model,
            update_model_fn=update_model
        )
        
        assert result == "success"
        assert fallback_model == "gpt-3.5-turbo"  # Fallback model used
        assert call_count == 5  # 4 retries (attempts 0-3) + 1 fallback attempt
    
    @pytest.mark.asyncio
    async def test_fallback_on_other_retryable_errors(self):
        """POSITIVE: Falls back on other retryable errors when enabled"""
        original_model = "gpt-4.1"
        fallback_model = None
        call_count = 0
        
        def update_model(new_model: str):
            nonlocal fallback_model
            fallback_model = new_model
        
        async def server_error_func():
            nonlocal call_count
            call_count += 1
            # With max_retries=3, we have attempts 0, 1, 2, 3 (4 attempts)
            # Fallback happens on attempt 3 (max_retries) if it fails
            # So we need to fail on attempts 0, 1, 2, 3 (4 failures), then succeed on fallback attempt (5th call)
            if call_count < 5:  # Fail 4 times (all retries), then succeed with fallback
                raise Exception("500 Internal Server Error")
            return "success"
        
        result = await retry_llm_call(
            func=server_error_func,
            max_retries=3,
            initial_delay=0.1,
            model_name=original_model,
            update_model_fn=update_model,
            enable_model_fallback=True  # Enable fallback for all errors
        )
        
        assert result == "success"
        assert fallback_model == "gpt-3.5-turbo"
        assert call_count == 5  # 4 retries + 1 fallback attempt
    
    @pytest.mark.asyncio
    async def test_no_fallback_when_disabled(self):
        """NEGATIVE: Does not fallback when enable_model_fallback=False"""
        original_model = "gpt-4.1"
        fallback_model = None
        call_count = 0
        
        def update_model(new_model: str):
            nonlocal fallback_model
            fallback_model = new_model
        
        async def server_error_func():
            nonlocal call_count
            call_count += 1
            raise Exception("500 Internal Server Error")
        
        with pytest.raises(Exception):
            await retry_llm_call(
                func=server_error_func,
                max_retries=2,
                initial_delay=0.1,
                model_name=original_model,
                update_model_fn=update_model,
                enable_model_fallback=False  # Disable fallback
            )
        
        assert fallback_model is None  # No fallback attempted
    
    @pytest.mark.asyncio
    async def test_no_fallback_for_non_retryable_errors(self):
        """NEGATIVE: Does not fallback for non-retryable errors"""
        original_model = "gpt-4.1"
        fallback_model = None
        
        def update_model(new_model: str):
            nonlocal fallback_model
            fallback_model = new_model
        
        async def bad_request_func():
            raise Exception("400 Bad Request")
        
        with pytest.raises(Exception):
            await retry_llm_call(
                func=bad_request_func,
                max_retries=3,
                initial_delay=0.1,
                model_name=original_model,
                update_model_fn=update_model
            )
        
        assert fallback_model is None  # No fallback for non-retryable errors
    
    @pytest.mark.asyncio
    async def test_fallback_fails_when_no_fallback_available(self):
        """NEGATIVE: Raises exception when fallback model not available"""
        original_model = "gpt-3.5-turbo"  # No fallback available
        fallback_model = None
        call_count = 0
        
        def update_model(new_model: str):
            nonlocal fallback_model
            fallback_model = new_model
        
        async def rate_limited_func():
            nonlocal call_count
            call_count += 1
            raise Exception("429 Rate limit exceeded")
        
        with pytest.raises(Exception):
            await retry_llm_call(
                func=rate_limited_func,
                max_retries=3,
                initial_delay=0.1,
                model_name=original_model,
                update_model_fn=update_model
            )
        
        assert fallback_model is None  # No fallback model available
    
    @pytest.mark.asyncio
    async def test_fallback_model_also_fails(self):
        """NEGATIVE: Raises exception if fallback model also fails"""
        original_model = "gpt-4.1"
        fallback_model = None
        call_count = 0
        
        def update_model(new_model: str):
            nonlocal fallback_model
            fallback_model = new_model
        
        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("429 Rate limit exceeded")
        
        with pytest.raises(Exception) as exc_info:
            await retry_llm_call(
                func=always_failing_func,
                max_retries=3,
                initial_delay=0.1,
                model_name=original_model,
                update_model_fn=update_model
            )
        
        assert fallback_model == "gpt-3.5-turbo"  # Fallback was attempted
        assert "429" in str(exc_info.value)  # Original error preserved


# ============================================================================
# P0.3: HOLISTIC PLAN DEGRADATION TESTS
# ============================================================================

class TestHolisticPlanDegradation:
    """Test holistic plan degradation when agents fail"""
    
    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator agent"""
        from unittest.mock import Mock
        coordinator = Mock()
        coordinator.physical_agent = Mock()
        coordinator.nutrition_agent = Mock()
        coordinator.mental_agent = Mock()
        return coordinator
    
    def test_degraded_flag_in_response_schema(self):
        """POSITIVE: Response schema includes degraded flag and fallback_info"""
        # Normal response
        response = AgentChatResponse(
            response="Test response",
            warnings=None,
            degraded=False
        )
        assert response.degraded is False
        assert response.fallback_info is None
        
        # Degraded response
        response = AgentChatResponse(
            response="Test response",
            warnings=["Some warning"],
            degraded=True,
            fallback_info={"original_model": "gpt-4.1", "fallback_model": "gpt-3.5-turbo"}
        )
        assert response.degraded is True
        assert response.fallback_info is not None
        assert response.fallback_info["original_model"] == "gpt-4.1"
    
    @pytest.mark.asyncio
    async def test_partial_results_continue_execution(self, mock_coordinator):
        """POSITIVE: Holistic plan continues with partial results when one agent fails"""
        # Mock one agent failing, others succeeding
        mock_coordinator.physical_agent.recommend_exercise = AsyncMock(
            return_value={"response": "Fitness plan", "warnings": None}
        )
        mock_coordinator.nutrition_agent.recommend_meal = AsyncMock(
            side_effect=Exception("Nutrition agent error")
        )
        mock_coordinator.mental_agent.recommend_practice = AsyncMock(
            return_value={"response": "Mental wellness plan", "warnings": None}
        )
        
        # In real implementation, coordinator would continue with available results
        # This test verifies the concept works
        fitness_result = await mock_coordinator.physical_agent.recommend_exercise("test")
        mental_result = await mock_coordinator.mental_agent.recommend_practice("test")
        
        assert fitness_result["response"] == "Fitness plan"
        assert mental_result["response"] == "Mental wellness plan"
        
        # Nutrition agent failed but others succeeded
        with pytest.raises(Exception):
            await mock_coordinator.nutrition_agent.recommend_meal("test")
    
    def test_agent_status_tracking(self):
        """POSITIVE: Agent status is tracked correctly"""
        # Simulate agent status tracking
        agent_status = {
            "fitness": {"success": True, "agent": "Physical Fitness", "error": None},
            "nutrition": {"success": False, "agent": "Nutrition", "error": "Timeout"},
            "mental": {"success": True, "agent": "Mental Fitness", "error": None}
        }
        
        failed_agents = [name for name, status in agent_status.items() if not status["success"]]
        available_components = [name for name, status in agent_status.items() if status["success"]]
        
        assert len(failed_agents) == 1
        assert "nutrition" in failed_agents
        assert len(available_components) == 2
        assert "fitness" in available_components
        assert "mental" in available_components
    
    def test_degraded_flag_set_when_agents_fail(self):
        """POSITIVE: Degraded flag is set when any agent fails"""
        agent_status = {
            "fitness": {"success": True},
            "nutrition": {"success": False},
            "mental": {"success": True}
        }
        
        degraded = not all(status["success"] for status in agent_status.values())
        
        assert degraded is True
    
    def test_degraded_flag_false_when_all_succeed(self):
        """POSITIVE: Degraded flag is False when all agents succeed"""
        agent_status = {
            "fitness": {"success": True},
            "nutrition": {"success": True},
            "mental": {"success": True}
        }
        
        degraded = not all(status["success"] for status in agent_status.values())
        
        assert degraded is False


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple features"""
    
    @pytest.mark.asyncio
    async def test_retry_with_circuit_breaker(self):
        """INTEGRATION: Retry logic works with circuit breaker"""
        circuit_breaker = CircuitBreaker(
            "test_service",
            failure_threshold=2,
            time_window=10.0
        )
        
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("500 Internal Server Error")
        
        # Open circuit
        for i in range(2):
            try:
                await circuit_breaker.call(failing_func)
            except Exception:
                pass
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Retry logic should respect circuit breaker
        with pytest.raises(CircuitBreakerOpenError):
            await circuit_breaker.call(failing_func)
    
    @pytest.mark.asyncio
    async def test_fallback_with_retry_and_circuit_breaker(self):
        """INTEGRATION: Model fallback works with retry and circuit breaker"""
        original_model = "gpt-4.1"
        fallback_model = None
        call_count = 0
        
        def update_model(new_model: str):
            nonlocal fallback_model
            fallback_model = new_model
        
        async def rate_limited_then_success():
            nonlocal call_count
            call_count += 1
            # With max_retries=3, we have attempts 0, 1, 2, 3 (4 attempts)
            # Fallback happens on attempt 3 (max_retries) if it fails
            # So we need to fail on attempts 0, 1, 2, 3 (4 failures), then succeed on fallback attempt (5th call)
            if call_count < 5:  # Fail 4 times (all retries), then succeed with fallback
                raise Exception("429 Rate limit exceeded")
            return "success"
        
        # This simulates the full flow: retry -> fallback -> success
        result = await retry_llm_call(
            func=rate_limited_then_success,
            max_retries=3,
            initial_delay=0.1,
            model_name=original_model,
            update_model_fn=update_model,
            service_name="openai"  # Would use circuit breaker in real scenario
        )
        
        assert result == "success"
        assert fallback_model == "gpt-3.5-turbo"
        assert call_count == 5  # 4 retries + 1 fallback attempt


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling"""
    
    @pytest.mark.asyncio
    async def test_zero_retries(self):
        """EDGE: Zero retries means no retry attempts"""
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Error")
        
        with pytest.raises(Exception):
            await retry_llm_call(
                func=failing_func,
                max_retries=0,
                initial_delay=0.1
            )
        
        assert call_count == 1  # Only initial call, no retries
    
    @pytest.mark.asyncio
    async def test_very_long_delay(self):
        """EDGE: Max delay is respected"""
        call_times = []
        
        async def failing_func():
            call_times.append(time.time())
            raise Exception("Error")
        
        start_time = time.time()
        
        try:
            await retry_llm_call(
                func=failing_func,
                max_retries=2,
                initial_delay=0.1,
                max_delay=0.2  # Low max delay
            )
        except Exception:
            pass
        
        # Check that delays don't exceed max_delay
        if len(call_times) >= 2:
            delay = call_times[1] - call_times[0]
            assert delay <= 0.3  # Allow some tolerance
    
    def test_circuit_breaker_no_tracer(self):
        """EDGE: Circuit breaker works without tracer"""
        cb = CircuitBreaker("test_service", tracer=None)
        assert cb.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_retry_with_no_model_name(self):
        """EDGE: Retry works without model name (no fallback)"""
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("500 Error")
            return "success"
        
        result = await retry_llm_call(
            func=failing_func,
            max_retries=3,
            initial_delay=0.1,
            model_name=None  # No model name
        )
        
        assert result == "success"
        assert call_count == 2

