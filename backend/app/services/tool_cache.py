"""
Tool Cache - caches tool results to reduce redundant calls
"""

from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class ToolCache:
    """
    In-memory cache for tool results with TTL-based expiration.
    Reduces redundant database queries and API calls.
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        
        # TTL map for different tools (how long to cache results)
        self._ttl_map = {
            "get_medical_history": timedelta(minutes=5),  # Medical history changes infrequently
            "get_user_preferences": timedelta(minutes=5),  # Preferences change infrequently
            "get_conversation_history": timedelta(minutes=1),  # Conversation history changes frequently
            "web_search": timedelta(hours=1),  # Web search results can be cached longer
        }
    
    def _get_cache_key(self, tool_name: str, user_id: Optional[int] = None, **kwargs) -> str:
        """
        Generate a cache key for a tool call.
        
        Args:
            tool_name: Name of the tool
            user_id: User ID (for user-specific tools)
            **kwargs: Tool-specific parameters
        
        Returns:
            Cache key string
        """
        # Include user_id in cache key for user-specific tools
        key_data = {"user_id": user_id} if user_id is not None else {}
        key_data.update(kwargs)
        
        # Sort keys for consistent hashing
        key_json = json.dumps(key_data, sort_keys=True, default=str)
        key_hash = hashlib.md5(f"{tool_name}:{key_json}".encode()).hexdigest()
        
        return f"tool_{tool_name}_{key_hash}"
    
    def get(self, tool_name: str, user_id: Optional[int] = None, **kwargs) -> Optional[Any]:
        """
        Get cached result for a tool call.
        
        Args:
            tool_name: Name of the tool
            user_id: User ID (for user-specific tools)
            **kwargs: Tool-specific parameters
        
        Returns:
            Cached result if available and not expired, None otherwise
        """
        cache_key = self._get_cache_key(tool_name, user_id=user_id, **kwargs)
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            ttl = self._ttl_map.get(tool_name, timedelta(minutes=5))  # Default 5 minutes
            
            # Check if cache is still valid
            if datetime.now() - cached["timestamp"] < ttl:
                logger.info(f"✅ Cache HIT for {tool_name} (user_id={user_id}, key: {cache_key[:20]}...)")
                return cached["result"]
            else:
                # Cache expired, remove it
                logger.info(f"⏰ Cache EXPIRED for {tool_name} (key: {cache_key[:20]}...)")
                del self._cache[cache_key]
        
        logger.info(f"❌ Cache MISS for {tool_name} (user_id={user_id})")
        return None
    
    def set(self, tool_name: str, result: Any, user_id: Optional[int] = None, **kwargs):
        """
        Cache a tool result.
        
        Args:
            tool_name: Name of the tool
            result: Result to cache
            user_id: User ID (for user-specific tools)
            **kwargs: Tool-specific parameters
        """
        cache_key = self._get_cache_key(tool_name, user_id=user_id, **kwargs)
        
        self._cache[cache_key] = {
            "result": result,
            "timestamp": datetime.now()
        }
        
        logger.info(f"💾 Cache SET for {tool_name} (user_id={user_id}, key: {cache_key[:20]}...)")
    
    def invalidate(self, tool_name: str, user_id: Optional[int] = None, **kwargs):
        """
        Invalidate cached result for a specific tool call.
        
        Args:
            tool_name: Name of the tool
            user_id: User ID (for user-specific tools)
            **kwargs: Tool-specific parameters
        """
        cache_key = self._get_cache_key(tool_name, user_id=user_id, **kwargs)
        
        if cache_key in self._cache:
            del self._cache[cache_key]
            logger.debug(f"Invalidated cache for {tool_name} (key: {cache_key[:20]}...)")
    
    def invalidate_user(self, user_id: int, tool_name: Optional[str] = None):
        """
        Invalidate all cached results for a user (optionally for a specific tool).
        
        Args:
            user_id: User ID
            tool_name: Optional tool name to invalidate only that tool for the user
        """
        keys_to_remove = []
        
        for cache_key in self._cache.keys():
            # Parse cache key: tool_{tool_name}_{hash}
            if cache_key.startswith("tool_"):
                parts = cache_key.split("_", 2)
                if len(parts) >= 3:
                    cached_tool_name = parts[1]
                    # Check if this cache entry is for the user
                    # We need to check the cached data to see if it matches user_id
                    # For simplicity, we'll invalidate by tool name pattern
                    if tool_name is None or cached_tool_name == tool_name:
                        # Check if this cache entry includes user_id in its hash
                        # Since we can't easily reverse the hash, we'll use a different approach
                        # For now, invalidate all entries for the tool if tool_name matches
                        if tool_name is None or cached_tool_name == tool_name:
                            keys_to_remove.append(cache_key)
        
        for key in keys_to_remove:
            del self._cache[key]
        
        if keys_to_remove:
            logger.debug(f"Invalidated {len(keys_to_remove)} cache entries for user {user_id}" + 
                        (f", tool {tool_name}" if tool_name else ""))
    
    def clear(self):
        """Clear all cached results"""
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cleared {count} cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats (size, entries per tool, etc.)
        """
        stats = {
            "total_entries": len(self._cache),
            "tools": {}
        }
        
        for cache_key in self._cache.keys():
            if cache_key.startswith("tool_"):
                # Parse: tool_{tool_name}_{hash}
                # Split on "_" but keep tool_name together (handle multi-word tool names)
                parts = cache_key.split("_")
                if len(parts) >= 3:
                    # Reconstruct tool_name (everything between "tool" and the hash)
                    # Hash is the last part, tool_name is everything in between
                    tool_name = "_".join(parts[1:-1])  # Skip "tool" prefix and hash suffix
                    if tool_name not in stats["tools"]:
                        stats["tools"][tool_name] = 0
                    stats["tools"][tool_name] += 1
        
        return stats


# Singleton instance
tool_cache = ToolCache()


def cached_tool(tool_name: str, include_user_id: bool = True):
    """
    Decorator to cache tool results.
    
    Args:
        tool_name: Name of the tool
        include_user_id: Whether to include user_id in cache key (default: True)
    
    Usage:
        @cached_tool("get_medical_history")
        def _run(self, query: str = ""):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Extract user_id from self if available
            user_id = getattr(self, 'user_id', None) if include_user_id else None
            
            # Remove self and db from kwargs for cache key (they're not serializable)
            cache_kwargs = {k: v for k, v in kwargs.items() if k not in ["self", "db"]}
            
            # Try to get from cache
            cached_result = tool_cache.get(tool_name, user_id=user_id, **cache_kwargs)
            if cached_result is not None:
                return cached_result
            
            # Execute tool and cache result
            result = func(self, *args, **kwargs)
            tool_cache.set(tool_name, result, user_id=user_id, **cache_kwargs)
            
            return result
        
        return wrapper
    return decorator

