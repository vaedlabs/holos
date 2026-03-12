"""
Tool Cache - caches tool results to reduce redundant calls.

This module provides the ToolCache class, which implements an in-memory cache
for tool execution results. Caching tool results reduces redundant database
queries and API calls, improving performance and reducing load.

Key Features:
- Tool-specific TTL (Time-To-Live) configuration
- User-specific caching for user-scoped tools
- Cache key generation with MD5 hashing
- Cache invalidation by tool, user, or all
- Cache statistics and monitoring

Cache Strategy:
- Different tools have different TTLs based on data volatility
- User-specific tools cache per user (e.g., medical history)
- Global tools cache across all users (e.g., web search)
- Cache keys include tool name and parameters for precise matching

Performance Benefits:
- Reduces database queries for frequently accessed data
- Reduces API calls for external services (e.g., web search)
- Improves response time for repeated queries
- Reduces server load and costs
"""

from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import json
import logging

# Logger instance for this module
# Used for logging cache hits, misses, and operations
logger = logging.getLogger(__name__)


class ToolCache:
    """
    In-memory cache for tool results with TTL-based expiration.
    
    This class provides caching for tool execution results to reduce redundant
    database queries and API calls. Each tool can have a custom TTL based on
    how frequently its data changes.
    
    Cache Structure:
        _cache: Dictionary mapping cache keys to cached data
        {
            "tool_get_medical_history_a1b2c3d4": {
                "result": "...",
                "timestamp": datetime
            }
        }
        
    TTL Configuration:
        Different tools have different TTLs:
        - get_medical_history: 5 minutes (changes infrequently)
        - get_user_preferences: 5 minutes (changes infrequently)
        - get_conversation_history: 1 minute (changes frequently)
        - web_search: 1 hour (results don't change, can cache longer)
        
    Cache Key Generation:
        Cache keys are generated using MD5 hash of tool name and parameters:
        Format: "tool_{tool_name}_{md5_hash}"
        Hash includes: tool_name, user_id (if applicable), and tool parameters
        
    Attributes:
        _cache: Dictionary storing cached tool results (key -> cache data)
        _ttl_map: Dictionary mapping tool names to TTL durations
        
    Note:
        - Singleton pattern: Use the global tool_cache instance
        - Thread-safe for read operations (Python GIL)
        - Cache is in-memory (lost on server restart)
        - User-specific tools cache per user (user_id in cache key)
    """
    
    def __init__(self):
        """
        Initialize ToolCache with empty cache and TTL configuration.
        
        Creates a new cache instance with:
        - Empty cache dictionary
        - Tool-specific TTL configuration
        """
        # In-memory cache dictionary
        # Key: Cache key string (e.g., "tool_get_medical_history_a1b2c3d4")
        # Value: Dictionary with result and timestamp
        self._cache: Dict[str, Dict] = {}
        
        # TTL map for different tools (how long to cache results)
        # Each tool has a custom TTL based on data volatility
        # Tools with frequently changing data have shorter TTLs
        self._ttl_map = {
            "get_medical_history": timedelta(minutes=5),  # Medical history changes infrequently
            "get_user_preferences": timedelta(minutes=5),  # Preferences change infrequently
            "get_conversation_history": timedelta(minutes=1),  # Conversation history changes frequently
            "web_search": timedelta(hours=1),  # Web search results can be cached longer
        }
    
    def _get_cache_key(self, tool_name: str, user_id: Optional[int] = None, **kwargs) -> str:
        """
        Generate a cache key for a tool call.
        
        This method creates a unique cache key based on the tool name, user ID
        (if applicable), and tool parameters. Uses MD5 hashing to create compact,
        consistent keys.
        
        Args:
            tool_name: Name of the tool (e.g., "get_medical_history")
            user_id: User ID for user-specific tools (optional)
            **kwargs: Tool-specific parameters (e.g., query string, agent_type)
        
        Returns:
            str: Cache key in format "tool_{tool_name}_{md5_hash}"
            
        Cache Key Generation:
            1. Build key data dictionary with user_id (if provided) and kwargs
            2. Convert to JSON string with sorted keys (for consistency)
            3. Create MD5 hash of "{tool_name}:{json_string}"
            4. Return formatted key: "tool_{tool_name}_{hash}"
            
        Example:
            tool_name="get_medical_history", user_id=123, query=""
            -> "tool_get_medical_history_a1b2c3d4e5f6..."
            
        Note:
            - Keys are deterministic (same inputs = same key)
            - MD5 hash ensures keys are compact and unique
            - Sorted keys ensure consistent hashing regardless of parameter order
            - User-specific tools include user_id in hash for per-user caching
        """
        # Include user_id in cache key for user-specific tools
        # User-specific tools (like get_medical_history) need user_id in key
        # Global tools (like web_search) don't include user_id
        key_data = {"user_id": user_id} if user_id is not None else {}
        # Add tool-specific parameters to key data
        key_data.update(kwargs)
        
        # Sort keys for consistent hashing
        # JSON with sorted keys ensures same parameters always produce same hash
        # regardless of parameter order
        key_json = json.dumps(key_data, sort_keys=True, default=str)
        # Create MD5 hash of tool name and parameters
        # MD5 provides good distribution and compact keys
        key_hash = hashlib.md5(f"{tool_name}:{key_json}".encode()).hexdigest()
        
        # Return formatted cache key
        return f"tool_{tool_name}_{key_hash}"
    
    def get(self, tool_name: str, user_id: Optional[int] = None, **kwargs) -> Optional[Any]:
        """
        Get cached result for a tool call.
        
        This method retrieves a cached tool result if available and not expired.
        Returns None if cache miss or expired, triggering tool execution.
        
        Args:
            tool_name: Name of the tool (e.g., "get_medical_history")
            user_id: User ID for user-specific tools (optional)
            **kwargs: Tool-specific parameters (e.g., query, agent_type)
        
        Returns:
            Optional[Any]: Cached result if available and not expired, None otherwise
            
        Cache Validation:
            1. Generate cache key from tool name, user_id, and parameters
            2. Check if cache entry exists
            3. Get TTL for this tool (default: 5 minutes if not configured)
            4. Validate cache hasn't expired (check timestamp against TTL)
            5. Return cached result if valid, or None if expired/missing
            
        TTL Logic:
            - Each tool has a custom TTL from _ttl_map
            - Default TTL is 5 minutes if tool not in TTL map
            - Expired entries are automatically removed (lazy deletion)
            
        Note:
            - Returns None on cache miss or expiration (triggers tool execution)
            - Expired entries are removed to prevent memory leaks
            - Cache key includes all parameters for precise matching
        """
        # Generate cache key from tool name, user_id, and parameters
        cache_key = self._get_cache_key(tool_name, user_id=user_id, **kwargs)
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # Get TTL for this tool (default: 5 minutes if not configured)
            ttl = self._ttl_map.get(tool_name, timedelta(minutes=5))  # Default 5 minutes
            
            # Check if cache is still valid (within TTL window)
            # Calculate time elapsed since cache was created
            if datetime.now() - cached["timestamp"] < ttl:
                logger.info(f"✅ Cache HIT for {tool_name} (user_id={user_id}, key: {cache_key[:20]}...)")
                return cached["result"]
            else:
                # Cache expired, remove it
                # Expired entries are removed to prevent memory leaks
                logger.info(f"⏰ Cache EXPIRED for {tool_name} (key: {cache_key[:20]}...)")
                del self._cache[cache_key]
        
        logger.info(f"❌ Cache MISS for {tool_name} (user_id={user_id})")
        return None
    
    def set(self, tool_name: str, result: Any, user_id: Optional[int] = None, **kwargs):
        """
        Cache a tool result.
        
        This method stores a tool execution result in the cache. The result will
        be available until it expires based on the tool's TTL configuration.
        
        Args:
            tool_name: Name of the tool (e.g., "get_medical_history")
            result: Result value to cache (any serializable type)
            user_id: User ID for user-specific tools (optional)
            **kwargs: Tool-specific parameters (e.g., query, agent_type)
            
        Cache Entry Structure:
            {
                "result": result,  # The cached tool result
                "timestamp": datetime.now()  # When cached (for TTL calculation)
            }
            
        TTL:
            - TTL is determined by tool_name from _ttl_map
            - Default TTL is 5 minutes if tool not configured
            - Timestamp is used to calculate expiration on retrieval
            
        Note:
            - Overwrites existing cache entry if present
            - Cache key includes all parameters for precise matching
            - Results are cached as-is (no serialization required for in-memory cache)
        """
        # Generate cache key from tool name, user_id, and parameters
        cache_key = self._get_cache_key(tool_name, user_id=user_id, **kwargs)
        
        # Store result in cache with timestamp
        # Timestamp is used to calculate expiration (TTL-based)
        self._cache[cache_key] = {
            "result": result,  # The cached tool result
            "timestamp": datetime.now()  # Cache timestamp (for TTL calculation)
        }
        
        logger.info(f"💾 Cache SET for {tool_name} (user_id={user_id}, key: {cache_key[:20]}...)")
    
    def invalidate(self, tool_name: str, user_id: Optional[int] = None, **kwargs):
        """
        Invalidate cached result for a specific tool call.
        
        This method removes a specific cached tool result from the cache.
        Used when data changes and cached result becomes stale.
        
        Args:
            tool_name: Name of the tool (e.g., "get_medical_history")
            user_id: User ID for user-specific tools (optional)
            **kwargs: Tool-specific parameters (must match original cache key)
            
        Usage:
            - Call when user data changes (e.g., medical history updated)
            - Ensures next tool call gets fresh data
            - More efficient than waiting for TTL expiration
            
        Note:
            - Cache key must match exactly (same parameters as original cache)
            - If cache entry doesn't exist, operation is no-op
            - Used for immediate cache invalidation when data changes
        """
        # Generate cache key (must match original cache key exactly)
        cache_key = self._get_cache_key(tool_name, user_id=user_id, **kwargs)
        
        # Remove cache entry if it exists
        if cache_key in self._cache:
            del self._cache[cache_key]
            logger.debug(f"Invalidated cache for {tool_name} (key: {cache_key[:20]}...)")
    
    def invalidate_user(self, user_id: int, tool_name: Optional[str] = None):
        """
        Invalidate all cached results for a user (optionally for a specific tool).
        
        This method invalidates cached tool results for a specific user. Can
        invalidate all tools for the user or just a specific tool. Used when
        user data changes (e.g., preferences updated, medical history changed).
        
        Args:
            user_id: User ID whose cache entries should be invalidated
            tool_name: Optional tool name to invalidate only that tool for the user
                      If None, invalidates all tools for the user
            
        Invalidation Logic:
            - Parses cache keys to extract tool names
            - Matches tool names if tool_name is specified
            - Note: Since cache keys use MD5 hashes, we can't directly extract user_id
            - Current implementation invalidates by tool name pattern
            - More precise invalidation would require storing user_id mapping
            
        Limitations:
            - Cannot directly match user_id from hash (MD5 is one-way)
            - Invalidates by tool name pattern (may invalidate more than intended)
            - For precise invalidation, use invalidate() with exact parameters
            
        Note:
            - Used when user data changes and all cached data for user becomes stale
            - More efficient than waiting for TTL expiration
            - If tool_name is None, invalidates all tools (may be broad)
        """
        keys_to_remove = []
        
        # Iterate through all cache entries
        # Filter for tool cache entries (start with "tool_")
        for cache_key in self._cache.keys():
            # Parse cache key: tool_{tool_name}_{hash}
            if cache_key.startswith("tool_"):
                # Split cache key to extract tool name
                # Format: "tool_{tool_name}_{md5_hash}"
                parts = cache_key.split("_", 2)
                if len(parts) >= 3:
                    cached_tool_name = parts[1]  # Extract tool name
                    # Check if this cache entry matches our criteria
                    # Match if tool_name is None (all tools) or matches cached tool name
                    # Note: Cannot directly check user_id from hash (MD5 is one-way)
                    # Current implementation invalidates by tool name pattern
                    if tool_name is None or cached_tool_name == tool_name:
                        # For now, invalidate all entries for the tool if tool_name matches
                        # More precise invalidation would require storing user_id mapping
                        if tool_name is None or cached_tool_name == tool_name:
                            keys_to_remove.append(cache_key)
        
        # Remove matching cache entries
        for key in keys_to_remove:
            del self._cache[key]
        
        if keys_to_remove:
            logger.debug(f"Invalidated {len(keys_to_remove)} cache entries for user {user_id}" + 
                        (f", tool {tool_name}" if tool_name else ""))
    
    def clear(self):
        """
        Clear all cached results.
        
        This method removes all cached tool results from memory. Useful for
        testing or when a complete cache reset is needed.
        
        Note:
            - Clears all tool caches (both user-specific and global)
            - Does not reset TTL configuration
            - Logs the number of entries cleared for monitoring
        """
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cleared {count} cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring and debugging.
        
        This method provides detailed statistics about the cache state, including
        total entries and breakdown by tool name.
        
        Returns:
            Dict[str, Any]: Dictionary with cache statistics:
                {
                    "total_entries": int,  # Total cache entries
                    "tools": {  # Statistics per tool
                        "get_medical_history": 5,
                        "get_user_preferences": 3,
                        "web_search": 2
                    }
                }
                
        Statistics Breakdown:
            - total_entries: Total number of cache entries
            - tools: Dictionary mapping tool names to entry counts
            
        Cache Key Parsing:
            Cache keys have format: "tool_{tool_name}_{md5_hash}"
            Tool name is extracted by joining parts between "tool" prefix and hash suffix.
            This handles multi-word tool names (e.g., "get_medical_history").
            
        Note:
            - Used for monitoring cache effectiveness
            - Helps identify cache hit/miss patterns
            - Useful for debugging cache issues
        """
        # Initialize statistics dictionary
        stats = {
            "total_entries": len(self._cache),  # Total cache entries
            "tools": {}  # Per-tool statistics
        }
        
        # Iterate through cache entries and count by tool
        for cache_key in self._cache.keys():
            if cache_key.startswith("tool_"):
                # Parse cache key to extract tool name
                # Format: "tool_{tool_name}_{md5_hash}"
                # Split on "_" but keep tool_name together (handle multi-word tool names)
                parts = cache_key.split("_")
                if len(parts) >= 3:
                    # Reconstruct tool_name (everything between "tool" and the hash)
                    # Hash is the last part, tool_name is everything in between
                    # Example: "tool_get_medical_history_a1b2c3d4" -> "get_medical_history"
                    tool_name = "_".join(parts[1:-1])  # Skip "tool" prefix and hash suffix
                    # Initialize tool count if needed
                    if tool_name not in stats["tools"]:
                        stats["tools"][tool_name] = 0
                    stats["tools"][tool_name] += 1
        
        return stats


# Singleton instance
# Global instance used throughout the application
# All tools share the same cache instance for consistency
tool_cache = ToolCache()


def cached_tool(tool_name: str, include_user_id: bool = True):
    """
    Decorator to automatically cache tool results.
    
    This decorator wraps tool methods to automatically cache their results.
    On first call, executes the tool and caches the result. On subsequent
    calls with same parameters, returns cached result if available and not expired.
    
    Args:
        tool_name: Name of the tool (e.g., "get_medical_history")
        include_user_id: Whether to include user_id in cache key (default: True)
                        Set to False for global tools that don't vary by user
    
    Usage:
        @cached_tool("get_medical_history")
        def _run(self, query: str = ""):
            # Tool implementation
            return result
            
        @cached_tool("web_search", include_user_id=False)
        def _run(self, query: str):
            # Global tool implementation (not user-specific)
            return result
    
    Cache Flow:
        1. Generate cache key from tool_name, user_id (if include_user_id=True), and parameters
        2. Check cache for existing result
        3. If cache hit and not expired, return cached result
        4. If cache miss or expired, execute tool function
        5. Cache the result for future calls
        6. Return the result
        
    Parameter Handling:
        - user_id: Extracted from self.user_id if include_user_id=True
        - self and db: Removed from kwargs (not serializable, not needed for cache key)
        - Other kwargs: Included in cache key for precise matching
        
    Note:
        - Decorator preserves function signature and metadata (@wraps)
        - Cache key includes all function parameters (except self and db)
        - User-specific tools should use include_user_id=True (default)
        - Global tools should use include_user_id=False
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Extract user_id from self if available
            # User-specific tools need user_id in cache key
            # Global tools (like web_search) don't need user_id
            user_id = getattr(self, 'user_id', None) if include_user_id else None
            
            # Remove self and db from kwargs for cache key (they're not serializable)
            # self and db are instance/dependency objects, not cache parameters
            cache_kwargs = {k: v for k, v in kwargs.items() if k not in ["self", "db"]}
            
            # Try to get from cache
            # Returns None if cache miss or expired
            cached_result = tool_cache.get(tool_name, user_id=user_id, **cache_kwargs)
            if cached_result is not None:
                return cached_result
            
            # Execute tool and cache result
            # Cache miss or expired - execute tool function
            result = func(self, *args, **kwargs)
            # Cache the result for future calls
            tool_cache.set(tool_name, result, user_id=user_id, **cache_kwargs)
            
            return result
        
        return wrapper
    return decorator

