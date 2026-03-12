"""
Circuit breaker pattern for LLM services to prevent cascading failures.

This module implements a three-state circuit breaker pattern to protect LLM
services from cascading failures. When a service is consistently failing, the
circuit breaker opens to prevent further calls, allowing the service to recover.

Key Features:
- Three-state circuit breaker (CLOSED, OPEN, HALF_OPEN)
- Automatic failure tracking and threshold detection
- Automatic recovery testing in half-open state
- Thread-safe state management
- Per-service circuit breakers (OpenAI, Gemini)

Circuit Breaker Pattern:
    The circuit breaker prevents cascading failures by:
    1. Tracking failures in a time window
    2. Opening circuit when failure threshold exceeded
    3. Blocking calls when circuit is open (fast failure)
    4. Testing recovery in half-open state
    5. Automatically closing when service recovers

States:
    - CLOSED: Normal operation, allowing all calls
    - OPEN: Service failing, blocking all calls immediately
    - HALF_OPEN: Testing recovery, allowing one call to test service

Benefits:
    - Prevents overwhelming failing services with requests
    - Provides fast failure (no waiting for timeouts)
    - Allows services to recover automatically
    - Reduces load on failing services
"""

import asyncio
import logging
import time
from typing import Optional, Callable, Any
from enum import Enum
from collections import deque
from threading import Lock

# Logger instance for this module
# Used for logging circuit state changes and operations
logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """
    Circuit breaker states enumeration.
    
    The circuit breaker operates in three states to manage service availability:
    
    States:
        CLOSED: Normal operation - all calls are allowed through
        OPEN: Service is failing - all calls are blocked immediately
        HALF_OPEN: Testing recovery - one call allowed to test if service recovered
        
    State Transitions:
        CLOSED -> OPEN: When failure threshold exceeded
        OPEN -> HALF_OPEN: After half_open_timeout seconds
        HALF_OPEN -> CLOSED: On successful call (service recovered)
        HALF_OPEN -> OPEN: On failed call (service still failing)
    """
    CLOSED = "CLOSED"  # Normal operation, allowing calls
    OPEN = "OPEN"  # Failing, blocking calls immediately
    HALF_OPEN = "HALF_OPEN"  # Testing recovery, allowing one call


class CircuitBreaker:
    """
    Circuit breaker implementation for LLM services.
    
    This class implements a three-state circuit breaker pattern to prevent
    cascading failures when LLM services are experiencing issues. It tracks
    failures, opens the circuit when threshold is exceeded, and automatically
    tests recovery.
    
    How It Works:
        1. Tracks failures in a sliding time window
        2. Opens circuit when failure threshold exceeded (e.g., 5 failures in 60s)
        3. Blocks all calls when circuit is OPEN (fast failure, no waiting)
        4. After timeout, enters HALF_OPEN state to test recovery
        5. Closes circuit if test call succeeds, reopens if it fails
        
    Prevents Cascading Failures:
        - Stops overwhelming failing services with requests
        - Provides immediate failure (no timeout waiting)
        - Allows services time to recover
        - Reduces load on failing infrastructure
        
    Thread Safety:
        - Uses Lock for thread-safe state management
        - Safe for concurrent access from multiple requests
        
    Attributes:
        service_name: Name of the service (e.g., "openai", "gemini")
        failure_threshold: Number of failures to open circuit (default: 5)
        time_window: Time window in seconds for failure counting (default: 60)
        half_open_timeout: Time in seconds before testing recovery (default: 30)
        tracer: AgentTracer instance for logging (optional)
        state: Current circuit state (CLOSED, OPEN, HALF_OPEN)
        failure_times: Deque of failure timestamps (sliding window)
        total_failures: Total failures tracked (for statistics)
        total_calls_blocked: Total calls blocked when circuit open (for statistics)
    """
    
    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        time_window: float = 60.0,
        half_open_timeout: float = 30.0,
        tracer: Optional[Any] = None
    ):
        """
        Initialize circuit breaker with configuration.
        
        Args:
            service_name: Name of the service (e.g., "openai", "gemini")
                        Used for logging and identification
            failure_threshold: Number of failures to open circuit (default: 5)
                             Circuit opens when this many failures occur in time_window
            time_window: Time window in seconds for failure counting (default: 60)
                        Failures outside this window are not counted
            half_open_timeout: Time in seconds before testing recovery (default: 30)
                             After circuit opens, waits this long before entering HALF_OPEN
            tracer: AgentTracer instance for logging circuit state changes (optional)
            
        Configuration Defaults:
            - failure_threshold=5: Opens after 5 failures
            - time_window=60s: Counts failures in last 60 seconds
            - half_open_timeout=30s: Tests recovery after 30 seconds
            
        Note:
            - Starts in CLOSED state (normal operation)
            - Thread-safe initialization
            - Statistics initialized to zero
        """
        # Service identification
        self.service_name = service_name
        
        # Circuit breaker configuration
        self.failure_threshold = failure_threshold  # Failures needed to open circuit
        self.time_window = time_window  # Time window for failure counting (seconds)
        self.half_open_timeout = half_open_timeout  # Time before testing recovery (seconds)
        self.tracer = tracer  # Tracer for logging state changes
        
        # Circuit state
        # Starts in CLOSED state (normal operation)
        self.state = CircuitState.CLOSED
        # Thread-safe lock for state management
        # Protects state changes from race conditions in concurrent requests
        self.state_lock = Lock()  # Thread-safe state management
        
        # Failure tracking
        # Deque stores timestamps of recent failures (sliding window)
        # Old failures are automatically removed when outside time_window
        self.failure_times = deque()  # Timestamps of recent failures
        self.last_failure_time = None  # Timestamp of most recent failure
        self.half_open_entered_at = None  # Timestamp when entered HALF_OPEN state
        
        # Statistics (for monitoring and debugging)
        self.total_failures = 0  # Total failures tracked (cumulative)
        self.total_calls_blocked = 0  # Total calls blocked when circuit open
        self.last_state_change = time.time()  # Timestamp of last state change
    
    def _log_state_change(self, old_state: CircuitState, new_state: CircuitState, reason: str = ""):
        """
        Log circuit state change for monitoring and debugging.
        
        This method logs when the circuit breaker changes state, which is important
        for understanding service health and debugging issues.
        
        Args:
            old_state: Previous circuit state
            new_state: New circuit state
            reason: Optional reason for state change (e.g., "5 failures in 60s")
            
        Logging:
            - Updates last_state_change timestamp
            - Logs state transition with service name
            - Includes reason if provided
            - Also logs to tracer if available
            
        Note:
            - State changes are logged as warnings (important events)
            - Helps operators understand service health
        """
        self.last_state_change = time.time()
        message = f"Circuit breaker [{self.service_name}]: {old_state.value} → {new_state.value}"
        if reason:
            message += f" ({reason})"
        
        logger.warning(message)
        
        if self.tracer:
            self.tracer.log_warning(message)
    
    def _should_open_circuit(self) -> bool:
        """
        Check if circuit should be opened based on failure threshold.
        
        This method determines if the circuit should be opened by checking if
        the number of failures in the time window exceeds the failure threshold.
        
        Returns:
            bool: True if circuit should be opened (threshold exceeded)
            
        Logic:
            1. Remove failures outside time window (sliding window)
            2. Count remaining failures
            3. Check if count >= failure_threshold
            
        Sliding Window:
            - Only counts failures within time_window seconds
            - Old failures are automatically removed
            - Ensures recent failure rate is what matters
            
        Example:
            failure_threshold=5, time_window=60s
            - 5 failures in last 60 seconds -> OPEN circuit
            - 4 failures in last 60 seconds -> Keep CLOSED
            - Failures older than 60 seconds are ignored
        """
        now = time.time()
        
        # Remove failures outside time window (sliding window)
        # Keep only failures within the time_window
        while self.failure_times and (now - self.failure_times[0]) > self.time_window:
            self.failure_times.popleft()
        
        # Check if we've exceeded threshold
        # Circuit opens when failure count >= threshold
        return len(self.failure_times) >= self.failure_threshold
    
    def _should_enter_half_open(self) -> bool:
        """
        Check if circuit should enter half-open state.
        
        This method determines if enough time has passed since the circuit opened
        to test if the service has recovered.
        
        Returns:
            bool: True if circuit should enter HALF_OPEN state
            
        Conditions:
            - Circuit must be in OPEN state
            - last_failure_time must be set
            - Elapsed time since last failure >= half_open_timeout
            
        Half-Open Purpose:
            - Tests if service has recovered
            - Allows one call to check service health
            - Prevents immediately reopening circuit if service recovered
            
        Note:
            - Only transitions from OPEN to HALF_OPEN
            - Requires half_open_timeout seconds to pass
        """
        if self.state != CircuitState.OPEN:
            return False
        
        if self.last_failure_time is None:
            return False
        
        # Check if enough time has passed to test recovery
        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.half_open_timeout
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a call through the circuit breaker.
        
        This is the main method for executing calls through the circuit breaker.
        It checks circuit state, blocks calls if circuit is open, and tracks
        failures to determine when to open the circuit.
        
        Execution Flow:
            1. Check circuit state (with lock)
            2. Transition to HALF_OPEN if timeout elapsed
            3. Block call if circuit is OPEN (raise CircuitBreakerOpenError)
            4. Execute function call
            5. On success: Update state (close circuit if HALF_OPEN)
            6. On failure: Record failure, potentially open circuit
        
        State Handling:
            - CLOSED: Execute call normally, track failures
            - OPEN: Block call immediately (fast failure)
            - HALF_OPEN: Execute call to test recovery
            
        Args:
            func: Async function to call through circuit breaker
            *args: Arguments to pass to function
            **kwargs: Keyword arguments to pass to function
            
        Returns:
            Any: Result from function call
            
        Raises:
            CircuitBreakerOpenError: If circuit is OPEN (service unavailable)
            Exception: Original exception if call fails
            
        Thread Safety:
            - Uses state_lock to protect state changes
            - Thread-safe for concurrent calls
            
        Note:
            - Fast failure when circuit is OPEN (no waiting)
            - Automatically tests recovery in HALF_OPEN state
            - Tracks failures to determine when to open circuit
        """
        # Check circuit state and update if needed (thread-safe)
        with self.state_lock:
            # Check if we should transition to half-open
            # After half_open_timeout seconds, test if service recovered
            if self._should_enter_half_open():
                old_state = self.state
                self.state = CircuitState.HALF_OPEN
                self.half_open_entered_at = time.time()
                self._log_state_change(old_state, self.state, "Testing recovery")
            
            # If circuit is open, block the call immediately
            # Fast failure - don't wait for timeout or retry
            if self.state == CircuitState.OPEN:
                self.total_calls_blocked += 1
                raise CircuitBreakerOpenError(
                    f"Circuit breaker for {self.service_name} is OPEN. "
                    f"Service is currently unavailable. Last failure: {self.last_failure_time} seconds ago. "
                    f"Please try again later."
                )
        
        # Attempt the call (circuit is CLOSED or HALF_OPEN)
        try:
            result = await func(*args, **kwargs)
            
            # Success - update circuit state (thread-safe)
            with self.state_lock:
                if self.state == CircuitState.HALF_OPEN:
                    # Successful call in half-open - service recovered!
                    # Close the circuit and reset failure tracking
                    old_state = self.state
                    self.state = CircuitState.CLOSED
                    self.failure_times.clear()  # Reset failure tracking
                    self.last_failure_time = None
                    self.half_open_entered_at = None
                    self._log_state_change(old_state, self.state, "Service recovered")
                elif self.state == CircuitState.CLOSED:
                    # Normal operation - clean up old failures outside window
                    # Keep failure tracking up-to-date (sliding window)
                    now = time.time()
                    while self.failure_times and (now - self.failure_times[0]) > self.time_window:
                        self.failure_times.popleft()
            
            return result
            
        except Exception as e:
            # Failure - record and potentially open circuit (thread-safe)
            with self.state_lock:
                # Record failure
                self.total_failures += 1
                failure_time = time.time()
                self.failure_times.append(failure_time)  # Add to sliding window
                self.last_failure_time = failure_time
                
                # Check if we should open circuit
                # Opens if failure threshold exceeded in time window
                if self._should_open_circuit():
                    if self.state != CircuitState.OPEN:
                        old_state = self.state
                        self.state = CircuitState.OPEN
                        self.half_open_entered_at = None
                        self._log_state_change(
                            old_state, 
                            self.state, 
                            f"{len(self.failure_times)} failures in {self.time_window}s"
                        )
                elif self.state == CircuitState.HALF_OPEN:
                    # Failed in half-open - recovery test failed
                    # Service is still down, reopen circuit
                    old_state = self.state
                    self.state = CircuitState.OPEN
                    self.half_open_entered_at = None
                    self._log_state_change(old_state, self.state, "Recovery test failed")
            
            # Re-raise the exception
            # Let caller handle the error (retry logic, etc.)
            raise
    
    def get_state(self) -> CircuitState:
        """
        Get current circuit state.
        
        Returns the current state of the circuit breaker in a thread-safe manner.
        
        Returns:
            CircuitState: Current circuit state (CLOSED, OPEN, or HALF_OPEN)
            
        Note:
            - Thread-safe (uses lock)
            - Returns snapshot of current state
        """
        with self.state_lock:
            return self.state
    
    def get_stats(self) -> dict:
        """
        Get circuit breaker statistics for monitoring.
        
        Returns detailed statistics about the circuit breaker's operation,
        including state, failure counts, and timing information.
        
        Returns:
            dict: Dictionary with statistics:
                {
                    "service_name": str,  # Service name
                    "state": str,  # Current state (CLOSED, OPEN, HALF_OPEN)
                    "total_failures": int,  # Total failures tracked (cumulative)
                    "total_calls_blocked": int,  # Calls blocked when circuit open
                    "recent_failures": int,  # Failures in current time window
                    "last_failure_time": float,  # Timestamp of last failure
                    "last_state_change": float  # Timestamp of last state change
                }
                
        Statistics Usage:
            - Monitoring service health
            - Debugging circuit breaker behavior
            - Understanding failure patterns
            - Performance analysis
            
        Note:
            - Thread-safe (uses lock)
            - recent_failures shows failures in current time window
            - total_failures is cumulative (all failures ever tracked)
        """
        with self.state_lock:
            return {
                "service_name": self.service_name,
                "state": self.state.value,
                "total_failures": self.total_failures,
                "total_calls_blocked": self.total_calls_blocked,
                "recent_failures": len(self.failure_times),  # Failures in time window
                "last_failure_time": self.last_failure_time,
                "last_state_change": self.last_state_change,
            }
    
    def reset(self):
        """
        Manually reset circuit breaker to CLOSED state.
        
        This method manually resets the circuit breaker, clearing all failure
        tracking and returning to CLOSED state. Useful for testing or manual
        intervention when service is known to be healthy.
        
        Reset Actions:
            - Sets state to CLOSED
            - Clears failure_times deque
            - Resets last_failure_time
            - Resets half_open_entered_at
            - Logs state change
            
        Note:
            - Thread-safe (uses lock)
            - Use with caution - only reset if service is confirmed healthy
            - Logs manual reset for audit trail
        """
        with self.state_lock:
            old_state = self.state
            self.state = CircuitState.CLOSED
            self.failure_times.clear()
            self.last_failure_time = None
            self.half_open_entered_at = None
            self._log_state_change(old_state, self.state, "Manual reset")


class CircuitBreakerOpenError(Exception):
    """
    Exception raised when circuit breaker is open.
    
    This exception is raised when a call is attempted but the circuit breaker
    is in OPEN state. It provides a user-friendly error message indicating
    that the service is temporarily unavailable.
    
    Note:
        - Raised immediately (fast failure, no waiting)
        - Indicates service is down or experiencing issues
        - User should retry after some time
    """
    pass


# Global circuit breaker instances (one per service)
# Singleton pattern: One circuit breaker per service (OpenAI, Gemini)
# Shared across all requests for the same service
_openai_circuit_breaker: Optional[CircuitBreaker] = None
_gemini_circuit_breaker: Optional[CircuitBreaker] = None
_circuit_breaker_lock = Lock()  # Thread-safe lock for singleton creation


def get_circuit_breaker(service_name: str, tracer: Optional[Any] = None) -> CircuitBreaker:
    """
    Get or create circuit breaker for a service (singleton pattern).
    
    This function returns a singleton circuit breaker instance for the specified
    service. Each service (OpenAI, Gemini) has its own circuit breaker instance
    that is shared across all requests.
    
    Args:
        service_name: Service name ("openai" or "gemini")
                     Case-insensitive matching
        tracer: AgentTracer instance for logging circuit state changes (optional)
                Tracer is only used during initialization (first call)
        
    Returns:
        CircuitBreaker: Circuit breaker instance for the service
        
    Singleton Pattern:
        - One circuit breaker per service (shared across all requests)
        - Lazy initialization (created on first access)
        - Thread-safe creation (uses lock)
        - Unknown services get new instances (not singletons)
        
    Configuration:
        All circuit breakers use the same configuration:
        - failure_threshold: 5 failures
        - time_window: 60 seconds
        - half_open_timeout: 30 seconds
        
    Note:
        - Tracer is only used during initialization (first call)
        - Subsequent calls return existing instance (tracer not updated)
        - Unknown services get new instances (not stored as singletons)
    """
    global _openai_circuit_breaker, _gemini_circuit_breaker
    
    with _circuit_breaker_lock:
        if service_name.lower() == "openai":
            # Get or create OpenAI circuit breaker singleton
            if _openai_circuit_breaker is None:
                _openai_circuit_breaker = CircuitBreaker(
                    service_name="openai",
                    failure_threshold=5,
                    time_window=60.0,
                    half_open_timeout=30.0,
                    tracer=tracer
                )
            return _openai_circuit_breaker
        elif service_name.lower() == "gemini":
            # Get or create Gemini circuit breaker singleton
            if _gemini_circuit_breaker is None:
                _gemini_circuit_breaker = CircuitBreaker(
                    service_name="gemini",
                    failure_threshold=5,
                    time_window=60.0,
                    half_open_timeout=30.0,
                    tracer=tracer
                )
            return _gemini_circuit_breaker
        else:
            # Create a new breaker for unknown services
            # Not stored as singleton (new instance each time)
            return CircuitBreaker(
                service_name=service_name,
                failure_threshold=5,
                time_window=60.0,
                half_open_timeout=30.0,
                tracer=tracer
            )

