"""
Rate limiting middleware for FastAPI application.
Prevents API abuse and DoS attacks by limiting requests per client.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware that tracks requests per client IP.
    Supports different rate limits for different endpoint types.
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
            default_requests_per_minute: Default rate limit for general endpoints
            agent_requests_per_minute: Rate limit for agent endpoints (more restrictive)
            auth_requests_per_minute: Rate limit for auth endpoints (most restrictive)
            window_seconds: Time window for rate limiting (default: 60 seconds)
        """
        super().__init__(app)
        self.default_requests_per_minute = default_requests_per_minute
        self.agent_requests_per_minute = agent_requests_per_minute
        self.auth_requests_per_minute = auth_requests_per_minute
        self.window_seconds = window_seconds
        
        # Store request timestamps per client IP
        # Format: {client_ip: [timestamp1, timestamp2, ...]}
        self.requests: Dict[str, list] = defaultdict(list)
        
        # Lock for thread safety (if needed in future)
        self._lock = None
    
    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier from request.
        Uses IP address, with fallback for forwarded requests.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Client identifier (IP address)
        """
        # Check for forwarded IP (when behind proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        return client_ip
    
    def _get_rate_limit(self, path: str) -> int:
        """
        Get rate limit for a specific endpoint path.
        
        Args:
            path: Request path
            
        Returns:
            Requests per minute allowed for this endpoint
        """
        # Agent endpoints - most restrictive
        if "/agents/" in path:
            return self.agent_requests_per_minute
        
        # Auth endpoints - very restrictive
        if "/auth/" in path:
            return self.auth_requests_per_minute
        
        # Default for all other endpoints
        return self.default_requests_per_minute
    
    def _clean_old_requests(self, client_id: str, now: float):
        """
        Remove request timestamps older than the time window.
        
        Args:
            client_id: Client identifier
            now: Current timestamp
        """
        cutoff_time = now - self.window_seconds
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if req_time > cutoff_time
        ]
    
    def _check_rate_limit(self, client_id: str, path: str, now: float) -> tuple:
        """
        Check if client has exceeded rate limit.
        
        Args:
            client_id: Client identifier
            path: Request path
            now: Current timestamp
            
        Returns:
            Tuple of (is_allowed, remaining_requests, limit)
        """
        # Get rate limit for this endpoint
        limit = self._get_rate_limit(path)
        
        # Clean old requests
        self._clean_old_requests(client_id, now)
        
        # Count current requests in window
        current_requests = len(self.requests[client_id])
        
        # Check if limit exceeded
        is_allowed = current_requests < limit
        remaining = max(0, limit - current_requests - 1)  # -1 because we'll add this request
        
        return is_allowed, remaining, limit
    
    def _add_rate_limit_headers(self, response: JSONResponse, remaining: int, limit: int, reset_time: int):
        """
        Add rate limit headers to response.
        
        Args:
            response: FastAPI response object
            remaining: Remaining requests in current window
            limit: Total requests allowed per window
            reset_time: Unix timestamp when rate limit resets
        """
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and apply rate limiting.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/endpoint in chain
            
        Returns:
            Response with rate limit headers
        """
        # Skip rate limiting for health check and root endpoints
        if request.url.path in ["/health", "/", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_id(request)
        now = time.time()
        
        # Check rate limit
        is_allowed, remaining, limit = self._check_rate_limit(client_id, request.url.path, now)
        
        if not is_allowed:
            # Calculate reset time (current time + window)
            reset_time = int(now + self.window_seconds)
            
            logger.warning(
                f"Rate limit exceeded for {client_id} on {request.method} {request.url.path}. "
                f"Limit: {limit} requests per {self.window_seconds} seconds"
            )
            
            # Return 429 Too Many Requests
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded. Please try again later.",
                    "status_code": status.HTTP_429_TOO_MANY_REQUESTS,
                    "retry_after": self.window_seconds,
                    "limit": limit,
                    "window_seconds": self.window_seconds
                }
            )
            
            # Add rate limit headers
            self._add_rate_limit_headers(response, 0, limit, reset_time)
            response.headers["Retry-After"] = str(self.window_seconds)
            
            return response
        
        # Record this request
        self.requests[client_id].append(now)
        
        # Process request
        response = await call_next(request)
        
        # Calculate reset time
        reset_time = int(now + self.window_seconds)
        
        # Add rate limit headers to successful responses
        if hasattr(response, 'headers'):
            self._add_rate_limit_headers(response, remaining, limit, reset_time)
        
        return response


def get_rate_limit_config() -> Dict[str, int]:
    """
    Get rate limit configuration from environment variables.
    
    Returns:
        Dictionary with rate limit settings
    """
    import os
    
    return {
        "default_requests_per_minute": int(os.getenv("RATE_LIMIT_DEFAULT", "60")),
        "agent_requests_per_minute": int(os.getenv("RATE_LIMIT_AGENT", "20")),
        "auth_requests_per_minute": int(os.getenv("RATE_LIMIT_AUTH", "10")),
        "window_seconds": int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    }

