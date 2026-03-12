"""
Rate limiting middleware for FastAPI application.

This module provides rate limiting middleware to prevent API abuse and DoS attacks
by limiting the number of requests per client IP address within a time window.
Supports different rate limits for different endpoint types.

Key Features:
- Per-client IP rate limiting: Tracks requests per client IP address
- Endpoint-specific limits: Different limits for agents, auth, and general endpoints
- Sliding window: Time-based window for rate limit calculation
- Rate limit headers: Standard headers (X-RateLimit-*) for client awareness
- Bypass logic: Health checks and docs endpoints bypass rate limiting

Rate Limit Tiers:
- Agent endpoints (/agents/*): Most restrictive (default: 20 requests/minute)
- Auth endpoints (/auth/*): Very restrictive (default: 10 requests/minute)
- General endpoints: Default limit (default: 60 requests/minute)

Rate Limit Headers:
- X-RateLimit-Limit: Total requests allowed per window
- X-RateLimit-Remaining: Remaining requests in current window
- X-RateLimit-Reset: Unix timestamp when rate limit resets
- Retry-After: Seconds to wait before retrying (when rate limited)

Client Identification:
- Uses client IP address from request
- Supports X-Forwarded-For header (for proxy/load balancer scenarios)
- Falls back to request.client.host if no forwarded header

Security:
- Prevents API abuse and DoS attacks
- Protects expensive endpoints (agents, auth) with stricter limits
- Rate limit violations logged for monitoring

Usage:
    from app.middleware.rate_limit import RateLimitMiddleware, get_rate_limit_config
    
    config = get_rate_limit_config()
    app.add_middleware(RateLimitMiddleware, **config)
"""

import logging
import time
from collections import defaultdict
from typing import Dict, Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Logger for rate limiting
# Logs rate limit violations and warnings
logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware that tracks requests per client IP.
    
    This middleware implements rate limiting using a sliding window approach.
    It tracks request timestamps per client IP and enforces rate limits based
    on endpoint type. Supports different rate limits for different endpoint categories.
    
    Rate Limit Strategy:
        - Sliding window: Tracks requests within a time window (default: 60 seconds)
        - Per-client IP: Each client IP has its own request counter
        - Endpoint-specific: Different limits for agents, auth, and general endpoints
        - Automatic cleanup: Old request timestamps removed outside window
    
    Attributes:
        default_requests_per_minute: int - Default rate limit for general endpoints
        agent_requests_per_minute: int - Rate limit for agent endpoints (more restrictive)
        auth_requests_per_minute: int - Rate limit for auth endpoints (most restrictive)
        window_seconds: int - Time window for rate limiting (default: 60 seconds)
        requests: Dict[str, list] - Request timestamps per client IP
        _lock: Optional - Lock for thread safety (future use)
    """
    
    def __init__(
        self,
        app,
        default_requests_per_minute: int = 60,
        agent_requests_per_minute: int = 20,
        auth_requests_per_minute: int = 10,
        window_seconds: int = 60
    ):
        """
        Initialize rate limiting middleware.
        
        Args:
            app: FastAPI application instance
                  Middleware wraps this app instance
            default_requests_per_minute: Default rate limit for general endpoints
                                       Default: 60 requests per minute
            agent_requests_per_minute: Rate limit for agent endpoints (more restrictive)
                                     Agent endpoints are expensive (LLM calls)
                                     Default: 20 requests per minute
            auth_requests_per_minute: Rate limit for auth endpoints (most restrictive)
                                    Auth endpoints are security-sensitive
                                    Default: 10 requests per minute
            window_seconds: Time window for rate limiting
                          Requests counted within this window
                          Default: 60 seconds (1 minute)
        """
        super().__init__(app)
        # Rate limit configuration
        # Different limits for different endpoint types
        self.default_requests_per_minute = default_requests_per_minute  # General endpoints: 60/min
        self.agent_requests_per_minute = agent_requests_per_minute  # Agent endpoints: 20/min (more restrictive)
        self.auth_requests_per_minute = auth_requests_per_minute  # Auth endpoints: 10/min (most restrictive)
        self.window_seconds = window_seconds  # Time window: 60 seconds
        
        # Store request timestamps per client IP
        # Format: {client_ip: [timestamp1, timestamp2, ...]}
        # Timestamps are Unix timestamps (time.time())
        # Old timestamps are cleaned up automatically
        self.requests: Dict[str, list] = defaultdict(list)  # Request timestamps per client IP
        
        # Lock for thread safety (if needed in future)
        # Currently not used (FastAPI is async, but could add for thread safety)
        self._lock = None
    
    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier from request.
        
        This method extracts the client IP address from the request, handling
        proxy/load balancer scenarios via X-Forwarded-For header.
        
        Client Identification Strategy:
            1. Check X-Forwarded-For header (for proxy/load balancer scenarios)
            2. Take first IP in chain (original client IP)
            3. Fallback to request.client.host (direct connection)
            4. Fallback to "unknown" if no client info available
        
        Args:
            request: FastAPI request object
                    Contains headers and client information
        
        Returns:
            str: Client identifier (IP address)
                 Format: "192.168.1.1" or "unknown" if unavailable
                 
        Note:
            - X-Forwarded-For can contain multiple IPs (proxy chain)
            - First IP is the original client IP
            - Used as key for rate limit tracking
        """
        # Check for forwarded IP (when behind proxy/load balancer)
        # X-Forwarded-For header contains original client IP when behind proxy
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            # Format: "client_ip, proxy1_ip, proxy2_ip"
            # First IP is the original client IP
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            # Direct connection (no proxy)
            # Use request.client.host for client IP
            client_ip = request.client.host if request.client else "unknown"
        
        return client_ip  # Return client IP for rate limit tracking
    
    def _get_rate_limit(self, path: str) -> int:
        """
        Get rate limit for a specific endpoint path.
        
        This method determines the rate limit based on the endpoint path.
        Different endpoint types have different rate limits based on their
        resource intensity and security sensitivity.
        
        Rate Limit Tiers:
            - Agent endpoints (/agents/*): Most restrictive (20/min)
              Reason: Expensive LLM calls, high resource usage
            - Auth endpoints (/auth/*): Very restrictive (10/min)
              Reason: Security-sensitive, prevents brute force attacks
            - General endpoints: Default limit (60/min)
              Reason: Standard API endpoints, moderate resource usage
        
        Args:
            path: str - Request path (e.g., "/agents/physical-fitness/chat")
        
        Returns:
            int: Requests per minute allowed for this endpoint
                 
        Note:
            - Path matching is simple substring matching
            - More specific paths checked first
            - Default limit applies to all other endpoints
        """
        # Agent endpoints - most restrictive
        # Agent endpoints are expensive (LLM calls, tool execution)
        # Stricter limit prevents resource exhaustion
        if "/agents/" in path:
            return self.agent_requests_per_minute  # 20 requests per minute
        
        # Auth endpoints - very restrictive
        # Auth endpoints are security-sensitive (login, registration)
        # Stricter limit prevents brute force attacks
        if "/auth/" in path:
            return self.auth_requests_per_minute  # 10 requests per minute
        
        # Default for all other endpoints
        # General endpoints (preferences, medical, logs, etc.)
        # Standard rate limit for normal API usage
        return self.default_requests_per_minute  # 60 requests per minute
    
    def _clean_old_requests(self, client_id: str, now: float):
        """
        Remove request timestamps older than the time window.
        
        This method cleans up old request timestamps that fall outside the
        sliding window. Only requests within the window are counted for
        rate limiting. This prevents unbounded memory growth.
        
        Cleanup Strategy:
            - Calculate cutoff time: now - window_seconds
            - Keep only timestamps newer than cutoff time
            - Old timestamps automatically removed
        
        Args:
            client_id: str - Client identifier (IP address)
            now: float - Current timestamp (Unix timestamp from time.time())
            
        Note:
            - Called before checking rate limit
            - Prevents memory leaks from accumulating old timestamps
            - Sliding window approach (not fixed window)
        """
        # Calculate cutoff time
        # Requests older than this are outside the window
        cutoff_time = now - self.window_seconds
        
        # Keep only timestamps within the window
        # Filter out old timestamps that are outside the sliding window
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if req_time > cutoff_time  # Keep only timestamps within window
        ]
    
    def _check_rate_limit(self, client_id: str, path: str, now: float) -> tuple:
        """
        Check if client has exceeded rate limit.
        
        This method checks if the client has exceeded the rate limit for the
        requested endpoint. It cleans old requests, counts current requests,
        and determines if the request should be allowed.
        
        Rate Limit Check Flow:
            1. Get rate limit for endpoint path
            2. Clean old requests outside window
            3. Count current requests in window
            4. Check if limit exceeded
            5. Calculate remaining requests
        
        Args:
            client_id: str - Client identifier (IP address)
            path: str - Request path (for endpoint-specific limits)
            now: float - Current timestamp (Unix timestamp)
        
        Returns:
            tuple: (is_allowed, remaining_requests, limit)
                - is_allowed: bool (True if request allowed, False if rate limited)
                - remaining_requests: int (remaining requests in current window)
                - limit: int (total requests allowed per window)
                
        Note:
            - Remaining requests calculated as limit - current - 1
            - -1 accounts for the current request being processed
            - Returns 0 for remaining if limit exceeded
        """
        # Get rate limit for this endpoint
        # Different endpoints have different limits (agents, auth, general)
        limit = self._get_rate_limit(path)
        
        # Clean old requests
        # Remove timestamps outside the sliding window
        self._clean_old_requests(client_id, now)
        
        # Count current requests in window
        # Number of requests within the time window
        current_requests = len(self.requests[client_id])
        
        # Check if limit exceeded
        # Request allowed if current requests < limit
        is_allowed = current_requests < limit
        # Calculate remaining requests
        # -1 accounts for the current request being processed
        remaining = max(0, limit - current_requests - 1)
        
        return is_allowed, remaining, limit
    
    def _add_rate_limit_headers(self, response: JSONResponse, remaining: int, limit: int, reset_time: int):
        """
        Add rate limit headers to response.
        
        This method adds standard rate limit headers to the response, allowing
        clients to be aware of their rate limit status and plan requests accordingly.
        
        Rate Limit Headers:
            - X-RateLimit-Limit: Total requests allowed per window
            - X-RateLimit-Remaining: Remaining requests in current window
            - X-RateLimit-Reset: Unix timestamp when rate limit resets
        
        Args:
            response: JSONResponse - FastAPI response object
                     Headers are added to this response
            remaining: int - Remaining requests in current window
                      Decrements with each request
            limit: int - Total requests allowed per window
                  Endpoint-specific limit (agents, auth, general)
            reset_time: int - Unix timestamp when rate limit resets
                       Calculated as now + window_seconds
        
        Note:
            - Headers follow standard rate limit header conventions
            - Clients can use headers to implement rate limit awareness
            - Reset time helps clients know when to retry
        """
        # Add standard rate limit headers
        # Headers follow common rate limit header conventions
        response.headers["X-RateLimit-Limit"] = str(limit)  # Total requests allowed
        response.headers["X-RateLimit-Remaining"] = str(remaining)  # Remaining requests
        response.headers["X-RateLimit-Reset"] = str(reset_time)  # Reset timestamp
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and apply rate limiting.
        
        This is the main middleware method that processes each request. It:
        1. Checks if endpoint should bypass rate limiting
        2. Identifies client and checks rate limit
        3. Allows or blocks request based on rate limit
        4. Records request timestamp if allowed
        5. Adds rate limit headers to response
        
        Bypass Logic:
            - Health check endpoints bypass rate limiting
            - Documentation endpoints bypass rate limiting
            - Prevents rate limiting from blocking monitoring/docs
        
        Rate Limit Enforcement:
            - If limit exceeded: Returns 429 Too Many Requests
            - If limit not exceeded: Records request and processes normally
            - Rate limit headers added to all responses
        
        Args:
            request: Request - FastAPI request object
                    Contains method, path, headers, client info
            call_next: Callable - Next middleware/endpoint in chain
                      Called if request is allowed
        
        Returns:
            Response: FastAPI response with rate limit headers
                     - 429 response if rate limited
                     - Normal response if allowed (with rate limit headers)
                     
        Rate Limit Headers:
            - Added to all responses (successful and rate limited)
            - Includes limit, remaining, reset time
            - Retry-After header added when rate limited
        """
        # Skip rate limiting for health check and root endpoints
        # These endpoints should not be rate limited (monitoring, docs)
        if request.url.path in ["/health", "/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)  # Bypass rate limiting
        
        # Get client identifier
        # Extracts client IP from request (handles proxy scenarios)
        client_id = self._get_client_id(request)
        now = time.time()  # Current timestamp for rate limit window
        
        # Check rate limit
        # Determines if request should be allowed based on rate limit
        is_allowed, remaining, limit = self._check_rate_limit(client_id, request.url.path, now)
        
        if not is_allowed:
            # Rate limit exceeded - block request
            # Calculate reset time (current time + window)
            reset_time = int(now + self.window_seconds)
            
            # Log rate limit violation
            # Helps monitor abuse and DoS attempts
            logger.warning(
                f"Rate limit exceeded for {client_id} on {request.method} {request.url.path}. "
                f"Limit: {limit} requests per {self.window_seconds} seconds"
            )
            
            # Return 429 Too Many Requests
            # Standard HTTP status code for rate limiting
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,  # 429 Too Many Requests
                content={
                    "error": "Rate limit exceeded. Please try again later.",  # Error message
                    "status_code": status.HTTP_429_TOO_MANY_REQUESTS,  # Status code
                    "retry_after": self.window_seconds,  # Seconds to wait before retry
                    "limit": limit,  # Rate limit that was exceeded
                    "window_seconds": self.window_seconds  # Time window
                }
            )
            
            # Add rate limit headers
            # Headers help clients understand rate limit status
            self._add_rate_limit_headers(response, 0, limit, reset_time)  # 0 remaining (rate limited)
            response.headers["Retry-After"] = str(self.window_seconds)  # Retry-After header
            
            return response
        
        # Record this request
        # Request is allowed - record timestamp for rate limit tracking
        self.requests[client_id].append(now)
        
        # Process request
        # Call next middleware/endpoint in chain
        response = await call_next(request)
        
        # Calculate reset time
        # When rate limit window resets
        reset_time = int(now + self.window_seconds)
        
        # Add rate limit headers to successful responses
        # Headers inform clients about rate limit status
        if hasattr(response, 'headers'):
            self._add_rate_limit_headers(response, remaining, limit, reset_time)
        
        return response


def get_rate_limit_config() -> Dict[str, int]:
    """
    Get rate limit configuration from environment variables.
    
    This function reads rate limit configuration from environment variables,
    providing defaults if not set. Allows runtime configuration without code changes.
    
    Environment Variables:
        - RATE_LIMIT_DEFAULT: Default rate limit for general endpoints (default: 60)
        - RATE_LIMIT_AGENT: Rate limit for agent endpoints (default: 20)
        - RATE_LIMIT_AUTH: Rate limit for auth endpoints (default: 10)
        - RATE_LIMIT_WINDOW: Time window in seconds (default: 60)
    
    Returns:
        Dict[str, int]: Dictionary with rate limit settings:
            - default_requests_per_minute: int (general endpoints)
            - agent_requests_per_minute: int (agent endpoints)
            - auth_requests_per_minute: int (auth endpoints)
            - window_seconds: int (time window)
            
    Usage:
        config = get_rate_limit_config()
        app.add_middleware(RateLimitMiddleware, **config)
        
    Note:
        - Values are converted to integers
        - Defaults provided if environment variables not set
        - Allows configuration via .env file or environment variables
    """
    import os
    
    # Read rate limit configuration from environment variables
    # Defaults provided if environment variables not set
    return {
        "default_requests_per_minute": int(os.getenv("RATE_LIMIT_DEFAULT", "60")),  # General endpoints: 60/min
        "agent_requests_per_minute": int(os.getenv("RATE_LIMIT_AGENT", "20")),  # Agent endpoints: 20/min
        "auth_requests_per_minute": int(os.getenv("RATE_LIMIT_AUTH", "10")),  # Auth endpoints: 10/min
        "window_seconds": int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # Time window: 60 seconds
    }

