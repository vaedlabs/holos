"""
Cache statistics and management endpoints for cache monitoring and control.

This module provides FastAPI router endpoints for cache management:
- Get cache stats: Retrieve cache statistics (size, hit rate, tool-specific stats)
- Clear cache: Clear all cache entries
- Invalidate tool cache: Invalidate cache for specific tool (optionally user-specific)

Key Features:
- Cache statistics: Monitor cache performance and usage
- Cache clearing: Clear all cached entries
- Tool-specific invalidation: Invalidate cache for specific tools
- User-specific invalidation: Invalidate cache for specific user and tool

Cache Types:
- Tool cache: Caches tool results (web search, medical history, preferences, etc.)
- Cache reduces redundant API calls and database queries
- TTL-based expiration for automatic cache invalidation

Security:
- All endpoints require authentication (get_current_user dependency)
- Cache management restricted to authenticated users

Usage:
    GET /cache/stats - Get cache statistics
    POST /cache/clear - Clear all cache entries
    POST /cache/invalidate/{tool_name} - Invalidate cache for specific tool
"""

from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.models.user import User
from app.services.tool_cache import tool_cache
from typing import Dict, Any

# FastAPI router for cache management endpoints
# Prefix: /cache (all routes will be prefixed with /cache)
# Tags: ["cache"] (for API documentation grouping)
router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get cache statistics.
    
    This endpoint retrieves cache statistics including cache size, hit rate,
    and tool-specific statistics. Useful for monitoring cache performance
    and debugging cache-related issues.
    
    Cache Statistics Include:
        - Total cache entries
        - Cache hit rate
        - Tool-specific statistics (entries per tool)
        - Cache size and memory usage
        - Other performance metrics
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Required for authentication (stats are global, not user-specific)
    
    Returns:
        Dict[str, Any]: Dictionary containing:
            - cache_stats: Dict (cache statistics from tool_cache)
            - message: str (success message)
            
    Security:
        - Requires authentication (get_current_user dependency)
        - Cache statistics are global (not user-specific)
        
    Usage:
        - Monitor cache performance
        - Debug cache-related issues
        - Optimize cache configuration
        
    Example:
        GET /cache/stats
        
        Returns cache statistics including size, hit rate, and tool-specific stats
    """
    # Get cache statistics from tool_cache service
    # Statistics include cache size, hit rate, tool-specific stats
    stats = tool_cache.get_stats()
    
    # Return statistics with success message
    return {
        "cache_stats": stats,  # Cache statistics dictionary
        "message": "Cache statistics retrieved successfully"
    }


@router.post("/clear")
async def clear_cache(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Clear all cache entries.
    
    This endpoint clears all entries from the tool cache. This action is
    irreversible and will cause all cached tool results to be regenerated
    on next access. Use with caution as it may impact performance.
    
    Cache Clearing Impact:
        - All cached tool results are removed
        - Next tool calls will execute fresh (no cache hits)
        - May temporarily increase API calls and database queries
        - Cache will rebuild as tools are called
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Required for authentication
    
    Returns:
        Dict[str, Any]: Dictionary containing:
            - message: str (success message)
            
    Security:
        - Requires authentication (get_current_user dependency)
        - Cache clearing affects all users (global cache)
        
    Note:
        - This action is irreversible
        - Use for debugging or cache reset scenarios
        - Consider using tool-specific invalidation for targeted clearing
        
    Example:
        POST /cache/clear
        
        Clears all cache entries
    """
    # Clear all cache entries
    # Removes all cached tool results from memory
    tool_cache.clear()
    
    # Return success message
    return {
        "message": "Cache cleared successfully"
    }


@router.post("/invalidate/{tool_name}")
async def invalidate_tool_cache(
    tool_name: str,
    user_id: int = None,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Invalidate cache for a specific tool.
    
    This endpoint invalidates cache entries for a specific tool. Supports
    both user-specific invalidation (if user_id provided) and tool-wide
    invalidation (if user_id not provided).
    
    Invalidation Modes:
        - User-specific: If user_id provided, invalidates cache for that user and tool
        - Tool-wide: If user_id not provided, clears all cache entries for the tool
                    (currently clears all cache - could be improved for selective clearing)
    
    Tool Names:
        - "web_search": Web search tool cache
        - "get_medical_history": Medical history tool cache
        - "get_user_preferences": User preferences tool cache
        - Other tool names as defined in tool_cache
    
    Args:
        tool_name: str - Name of the tool to invalidate cache for
        user_id: Optional[int] - User ID for user-specific invalidation
                If provided, only invalidates cache for that user and tool
                If None, invalidates all cache entries for the tool
        current_user: Authenticated user (injected dependency)
                     Required for authentication
    
    Returns:
        Dict[str, Any]: Dictionary containing:
            - message: str (success message with invalidation details)
            
    Security:
        - Requires authentication (get_current_user dependency)
        - User-specific invalidation requires user_id parameter
        
    Note:
        - Tool-wide invalidation currently clears all cache (simplified implementation)
        - Could be improved to selectively clear only entries for specific tool
        - User-specific invalidation is more targeted and efficient
        
    Example:
        POST /cache/invalidate/web_search?user_id=123
        
        Invalidates web_search cache for user 123
        
        POST /cache/invalidate/get_medical_history
        
        Clears all get_medical_history cache entries (currently clears all cache)
    """
    if user_id:
        # User-specific cache invalidation
        # Invalidates cache for specific user and tool
        tool_cache.invalidate_user(user_id, tool_name)
        return {
            "message": f"Cache invalidated for {tool_name} (user_id={user_id})"
        }
    else:
        # Invalidate all entries for this tool
        # This is a simplified version - in production, you might want more control
        # Currently clears all cache (could be improved to selectively clear tool-specific entries)
        stats = tool_cache.get_stats()
        count = stats["tools"].get(tool_name, 0)  # Get count of entries for this tool
        tool_cache.clear()  # For now, clear all (could be improved)
        return {
            "message": f"Cache cleared (was {count} entries for {tool_name})"
        }

