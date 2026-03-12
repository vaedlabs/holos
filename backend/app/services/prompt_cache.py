"""
System Prompt Cache - caches system prompts to reduce token usage.

This module provides the PromptCache class, which implements an in-memory cache
for system prompts used by AI agents. Caching prompts significantly reduces token
usage by avoiding repeated prompt construction and transmission to LLM APIs.

Key Features:
- Static base prompt caching (infinite TTL, version-based invalidation)
- Enhanced prompt caching with user context (5-minute TTL, auto-expiration)
- Cache invalidation strategies (version-based for static, TTL-based for enhanced)
- Cache statistics and monitoring

Cache Strategy:
- Static prompts: Cached indefinitely until manually invalidated (when prompt files change)
- Enhanced prompts: Cached for 5 minutes (matches user context cache TTL)
- Reduces token costs by avoiding redundant prompt construction
- Improves performance by avoiding prompt building overhead

Token Savings:
- Static prompts: Saved on every agent call after first call
- Enhanced prompts: Saved when same user queries same agent within 5 minutes
- Significant cost reduction for high-traffic applications
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib
import json
import logging

# Logger instance for this module
# Used for logging cache hits, misses, and operations
logger = logging.getLogger(__name__)


class PromptCache:
    """
    In-memory cache for system prompts with TTL-based expiration.
    
    This class provides caching for system prompts to reduce token usage and
    improve performance. It supports two types of prompts:
    
    1. Static base prompts: Agent-specific base prompts that don't change
       - Cached indefinitely until manually invalidated
       - Invalidated when prompt files are updated (version-based)
       - Cache key format: "prompt_base_{agent_type}"
       
    2. Enhanced prompts: Base prompts enhanced with user context
       - Cached for 5 minutes (auto-expires)
       - Invalidated when user context changes
       - Cache key format: "prompt_enhanced_{agent_type}_{user_id}"
    
    Cache Structure:
        _cache: Dictionary mapping cache keys to cached data
        {
            "prompt_base_physical_fitness": {
                "prompt": "...",
                "timestamp": datetime,
                "version": "1.0"
            },
            "prompt_enhanced_nutrition_123": {
                "prompt": "...",
                "timestamp": datetime
            }
        }
        
    Attributes:
        _cache: Dictionary storing cached prompts (key -> cache data)
        _enhanced_prompt_ttl: Time-to-live for enhanced prompts (5 minutes)
        _prompt_version: Version string for static prompt invalidation
        
    Note:
        - Singleton pattern: Use the global prompt_cache instance
        - Thread-safe for read operations (Python GIL)
        - Cache is in-memory (lost on server restart)
        - Version-based invalidation allows bulk cache clearing
    """
    
    def __init__(self):
        """
        Initialize PromptCache with empty cache and default configuration.
        
        Creates a new cache instance with:
        - Empty cache dictionary
        - 5-minute TTL for enhanced prompts
        - Version 1.0 for static prompt tracking
        """
        # In-memory cache dictionary
        # Key: Cache key string (e.g., "prompt_base_physical_fitness")
        # Value: Dictionary with prompt, timestamp, and optional version
        self._cache: Dict[str, Dict] = {}
        
        # TTL for enhanced prompts (user-specific, includes context)
        # Enhanced prompts expire after 5 minutes to ensure fresh user context
        # Matches user context cache TTL for consistency
        # Auto-expires to prevent stale user data in prompts
        self._enhanced_prompt_ttl = timedelta(minutes=5)  # Same as user context cache
        
        # Version tracking for static prompts (for invalidation)
        # When prompt files are updated, increment version to invalidate all static caches
        # Format: "1.0", "1.1", "1.2", etc.
        # Allows bulk invalidation without iterating through cache
        self._prompt_version = "1.0"
    
    def _get_static_cache_key(self, agent_type: str) -> str:
        """
        Generate cache key for static base prompt.
        
        This method creates a cache key for static base prompts that don't include
        user-specific context. Static prompts are shared across all users for a given agent type.
        
        Args:
            agent_type: Type of agent (e.g., 'physical_fitness', 'nutrition', 'mental_fitness', 'coordinator')
        
        Returns:
            str: Cache key in format "prompt_base_{agent_type}"
            
        Example:
            agent_type="nutrition" -> "prompt_base_nutrition"
            
        Note:
            - Static prompts are shared across all users
            - Cache key doesn't include user_id
            - Used for base prompts that don't change per user
        """
        return f"prompt_base_{agent_type}"
    
    def _get_enhanced_cache_key(self, agent_type: str, user_id: int) -> str:
        """
        Generate cache key for enhanced prompt with user context.
        
        This method creates a cache key for enhanced prompts that include user-specific
        context (medical history, preferences, etc.). Enhanced prompts are unique per user.
        
        Args:
            agent_type: Type of agent (e.g., 'physical_fitness', 'nutrition', 'mental_fitness', 'coordinator')
            user_id: User ID for user-specific caching
        
        Returns:
            str: Cache key in format "prompt_enhanced_{agent_type}_{user_id}"
            
        Example:
            agent_type="nutrition", user_id=123 -> "prompt_enhanced_nutrition_123"
            
        Note:
            - Enhanced prompts are user-specific
            - Cache key includes user_id for per-user caching
            - Used for prompts that include user context
        """
        return f"prompt_enhanced_{agent_type}_{user_id}"
    
    def get_static_prompt(self, agent_type: str) -> Optional[str]:
        """
        Get cached static base prompt.
        
        This method retrieves a cached static base prompt if available and valid.
        Static prompts are checked against the current version to ensure they're up-to-date.
        
        Args:
            agent_type: Type of agent (e.g., 'physical_fitness', 'nutrition')
        
        Returns:
            Optional[str]: Cached prompt if available and valid, None otherwise
            
        Cache Validation:
            - Checks if cache entry exists
            - Validates version matches current _prompt_version
            - Removes cache entry if version mismatch (stale cache)
            
        Note:
            - Returns None on cache miss or version mismatch
            - Version checking allows bulk invalidation of all static prompts
            - Static prompts don't expire based on time (only version)
        """
        cache_key = self._get_static_cache_key(agent_type)
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # Check if version matches (for invalidation)
            # Version mismatch indicates prompt files were updated
            if cached.get("version") == self._prompt_version:
                logger.info(f"✅ Cache HIT for static prompt: {agent_type}")
                return cached["prompt"]
            else:
                # Version mismatch, remove old cache
                # This happens when prompt files are updated and version is incremented
                logger.info(f"🔄 Cache EXPIRED (version mismatch) for static prompt: {agent_type}")
                del self._cache[cache_key]
        
        logger.info(f"❌ Cache MISS for static prompt: {agent_type}")
        return None
    
    def set_static_prompt(self, agent_type: str, prompt: str):
        """
        Cache static base prompt.
        
        This method stores a static base prompt in the cache with the current version.
        Static prompts are cached indefinitely until manually invalidated via version increment.
        
        Args:
            agent_type: Type of agent (e.g., 'physical_fitness', 'nutrition')
            prompt: Static base prompt string to cache
            
        Cache Entry Structure:
            {
                "prompt": "...",  # The actual prompt string
                "timestamp": datetime.now(),  # When cached (for monitoring)
                "version": "1.0"  # Current version (for invalidation)
            }
            
        Note:
            - Overwrites existing cache entry if present
            - Version is set to current _prompt_version
            - Timestamp is stored for monitoring/debugging
            - Static prompts don't expire (only invalidated by version change)
        """
        cache_key = self._get_static_cache_key(agent_type)
        
        # Store prompt in cache with version tracking
        # Version allows bulk invalidation when prompt files are updated
        self._cache[cache_key] = {
            "prompt": prompt,  # The actual prompt string
            "timestamp": datetime.now(),  # Cache timestamp (for monitoring)
            "version": self._prompt_version  # Current version (for invalidation)
        }
        
        logger.info(f"💾 Cache SET for static prompt: {agent_type} ({len(prompt)} chars)")
    
    def get_enhanced_prompt(self, agent_type: str, user_id: int) -> Optional[str]:
        """
        Get cached enhanced prompt with user context.
        
        This method retrieves a cached enhanced prompt if available and not expired.
        Enhanced prompts include user-specific context and expire after 5 minutes.
        
        Args:
            agent_type: Type of agent (e.g., 'physical_fitness', 'nutrition')
            user_id: User ID for user-specific caching
        
        Returns:
            Optional[str]: Cached enhanced prompt if available and not expired, None otherwise
            
        Cache Validation:
            - Checks if cache entry exists
            - Validates TTL (checks if cache is still within 5-minute window)
            - Removes cache entry if expired (stale user context)
            
        TTL Logic:
            - Enhanced prompts expire after 5 minutes
            - Ensures user context (medical history, preferences) is fresh
            - Matches user context cache TTL for consistency
            
        Note:
            - Returns None on cache miss or expiration
            - Expired entries are automatically removed
            - TTL ensures user context doesn't become stale
        """
        cache_key = self._get_enhanced_cache_key(agent_type, user_id)
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            ttl = self._enhanced_prompt_ttl
            
            # Check if cache is still valid (within TTL window)
            # Calculate time elapsed since cache was created
            if datetime.now() - cached["timestamp"] < ttl:
                logger.info(f"✅ Cache HIT for enhanced prompt: {agent_type} (user_id={user_id})")
                return cached["prompt"]
            else:
                # Cache expired, remove it
                # Enhanced prompts expire after 5 minutes to ensure fresh user context
                logger.info(f"⏰ Cache EXPIRED for enhanced prompt: {agent_type} (user_id={user_id})")
                del self._cache[cache_key]
        
        logger.info(f"❌ Cache MISS for enhanced prompt: {agent_type} (user_id={user_id})")
        return None
    
    def set_enhanced_prompt(self, agent_type: str, user_id: int, prompt: str):
        """
        Cache enhanced prompt with user context.
        
        This method stores an enhanced prompt (base prompt + user context) in the cache.
        Enhanced prompts expire after 5 minutes to ensure user context stays fresh.
        
        Args:
            agent_type: Type of agent (e.g., 'physical_fitness', 'nutrition')
            user_id: User ID for user-specific caching
            prompt: Enhanced prompt string with user context to cache
            
        Cache Entry Structure:
            {
                "prompt": "...",  # The enhanced prompt string (includes user context)
                "timestamp": datetime.now()  # When cached (for TTL calculation)
            }
            
        TTL:
            - Enhanced prompts expire after 5 minutes (auto-expiration)
            - Timestamp is used to calculate expiration on retrieval
            - Ensures user context (medical history, preferences) is fresh
            
        Note:
            - Overwrites existing cache entry if present
            - No version tracking (expires based on TTL only)
            - User-specific (each user has their own cached enhanced prompt)
        """
        cache_key = self._get_enhanced_cache_key(agent_type, user_id)
        
        # Store enhanced prompt in cache with timestamp
        # Timestamp is used to calculate expiration (5-minute TTL)
        self._cache[cache_key] = {
            "prompt": prompt,  # The enhanced prompt string (includes user context)
            "timestamp": datetime.now()  # Cache timestamp (for TTL calculation)
        }
        
        logger.info(f"💾 Cache SET for enhanced prompt: {agent_type} (user_id={user_id}, {len(prompt)} chars)")
    
    def invalidate_static_prompt(self, agent_type: Optional[str] = None):
        """
        Invalidate static prompt cache (e.g., when prompt files are updated).
        
        This method invalidates cached static prompts. Can invalidate a specific
        agent's prompt or all static prompts at once using version-based invalidation.
        
        Args:
            agent_type: Specific agent type to invalidate (e.g., 'nutrition'), or None to invalidate all
            
        Invalidation Strategies:
            1. Specific agent: Deletes cache entry for that agent type
            2. All agents: Increments version number, causing all static prompts to be invalidated
               on next access (version mismatch check)
               
        Version-Based Invalidation:
            - When agent_type is None, increments _prompt_version
            - Existing cache entries remain but become invalid (version mismatch)
            - Invalid entries are removed on next access (lazy deletion)
            - More efficient than iterating through all cache entries
            
        Note:
            - Use None to invalidate all static prompts (e.g., when prompt files are updated)
            - Use specific agent_type to invalidate one agent's prompt
            - Version increment is efficient for bulk invalidation
        """
        if agent_type:
            # Invalidate specific agent's static prompt
            # Delete cache entry directly
            cache_key = self._get_static_cache_key(agent_type)
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.info(f"🗑️ Invalidated static prompt cache: {agent_type}")
        else:
            # Invalidate all static prompts by incrementing version
            # This causes all static prompts to become invalid (version mismatch)
            # Invalid entries are removed lazily on next access
            # More efficient than iterating through all cache entries
            self._prompt_version = str(float(self._prompt_version) + 0.1)
            logger.info(f"🗑️ Invalidated all static prompt caches (version: {self._prompt_version})")
    
    def invalidate_enhanced_prompt(self, agent_type: Optional[str] = None, user_id: Optional[int] = None):
        """
        Invalidate enhanced prompt cache (e.g., when user context changes).
        
        This method invalidates cached enhanced prompts. Can invalidate by agent type,
        user ID, or both. Used when user context (medical history, preferences) changes.
        
        Args:
            agent_type: Specific agent type to invalidate (e.g., 'nutrition'), or None for all
            user_id: Specific user ID to invalidate, or None for all users of this agent type
            
        Invalidation Scenarios:
            1. agent_type=None, user_id=None: Invalidates all enhanced prompts
            2. agent_type="nutrition", user_id=None: Invalidates all nutrition agent enhanced prompts
            3. agent_type=None, user_id=123: Invalidates all enhanced prompts for user 123
            4. agent_type="nutrition", user_id=123: Invalidates nutrition enhanced prompt for user 123
            
        Cache Key Parsing:
            Enhanced prompt cache keys have format: "prompt_enhanced_{agent_type}_{user_id}"
            This method parses the cache key to extract agent_type and user_id for matching.
            
        Note:
            - Used when user preferences or medical history changes
            - Ensures enhanced prompts reflect latest user context
            - More efficient than waiting for TTL expiration
        """
        keys_to_remove = []
        
        # Iterate through all cache entries
        # Filter for enhanced prompt entries (start with "prompt_enhanced_")
        for cache_key in list(self._cache.keys()):
            if cache_key.startswith("prompt_enhanced_"):
                # Parse cache key to extract agent_type and user_id
                # Format: "prompt_enhanced_{agent_type}_{user_id}"
                # Split into: ["prompt", "enhanced", "{agent_type}_{user_id}"]
                parts = cache_key.split("_", 2)
                if len(parts) >= 3:
                    remaining = parts[2]  # "{agent_type}_{user_id}"
                    # Find last underscore to split agent_type and user_id
                    # Last underscore separates agent_type from user_id
                    last_underscore = remaining.rfind("_")
                    if last_underscore > 0:
                        cached_agent_type = remaining[:last_underscore]  # Extract agent_type
                        cached_user_id = int(remaining[last_underscore + 1:])  # Extract user_id
                        
                        # Check if this entry matches our invalidation criteria
                        # Match if agent_type is None or matches, AND user_id is None or matches
                        if agent_type is None or cached_agent_type == agent_type:
                            if user_id is None or cached_user_id == user_id:
                                keys_to_remove.append(cache_key)
        
        # Remove matching cache entries
        for key in keys_to_remove:
            del self._cache[key]
        
        if keys_to_remove:
            logger.info(f"🗑️ Invalidated {len(keys_to_remove)} enhanced prompt cache entries "
                       f"(agent_type={agent_type}, user_id={user_id})")
    
    def clear(self):
        """
        Clear all cached prompts.
        
        This method removes all cached prompts from memory. Useful for testing
        or when a complete cache reset is needed.
        
        Note:
            - Clears both static and enhanced prompts
            - Does not reset version number
            - Logs the number of entries cleared for monitoring
        """
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cleared {count} prompt cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring and debugging.
        
        This method provides detailed statistics about the cache state, including
        total entries, breakdown by prompt type, and statistics per agent type.
        
        Returns:
            Dict[str, Any]: Dictionary with cache statistics:
                {
                    "total_entries": int,  # Total cache entries
                    "static_prompts": int,  # Number of static prompts cached
                    "enhanced_prompts": int,  # Number of enhanced prompts cached
                    "prompt_version": str,  # Current version for static prompts
                    "by_agent_type": {  # Statistics per agent type
                        "nutrition": {"static": 1, "enhanced": 5},
                        "physical_fitness": {"static": 1, "enhanced": 3}
                    }
                }
                
        Statistics Breakdown:
            - total_entries: Total number of cache entries (static + enhanced)
            - static_prompts: Number of static base prompts cached
            - enhanced_prompts: Number of enhanced prompts cached (across all users)
            - prompt_version: Current version string for static prompt invalidation
            - by_agent_type: Per-agent statistics showing static and enhanced prompt counts
            
        Note:
            - Used for monitoring cache effectiveness
            - Helps identify cache hit/miss patterns
            - Useful for debugging cache issues
        """
        # Initialize statistics dictionary
        stats = {
            "total_entries": len(self._cache),  # Total cache entries
            "static_prompts": 0,  # Count of static prompts
            "enhanced_prompts": 0,  # Count of enhanced prompts
            "prompt_version": self._prompt_version,  # Current version
            "by_agent_type": {}  # Per-agent statistics
        }
        
        # Iterate through cache entries and categorize
        for cache_key in self._cache.keys():
            if cache_key.startswith("prompt_base_"):
                # Static prompt entry
                stats["static_prompts"] += 1
                # Extract agent type from cache key
                agent_type = cache_key.replace("prompt_base_", "")
                # Initialize agent type stats if needed
                if agent_type not in stats["by_agent_type"]:
                    stats["by_agent_type"][agent_type] = {"static": 0, "enhanced": 0}
                stats["by_agent_type"][agent_type]["static"] += 1
            elif cache_key.startswith("prompt_enhanced_"):
                # Enhanced prompt entry
                stats["enhanced_prompts"] += 1
                # Parse agent type from cache key
                # Format: "prompt_enhanced_{agent_type}_{user_id}"
                parts = cache_key.split("_", 2)
                if len(parts) >= 3:
                    remaining = parts[2]  # "{agent_type}_{user_id}"
                    # Find last underscore to extract agent_type
                    last_underscore = remaining.rfind("_")
                    if last_underscore > 0:
                        agent_type = remaining[:last_underscore]
                        # Initialize agent type stats if needed
                        if agent_type not in stats["by_agent_type"]:
                            stats["by_agent_type"][agent_type] = {"static": 0, "enhanced": 0}
                        stats["by_agent_type"][agent_type]["enhanced"] += 1
        
        return stats


# Singleton instance
# Global instance used throughout the application
# All agents share the same cache instance for consistency
prompt_cache = PromptCache()

