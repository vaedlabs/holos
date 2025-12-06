"""
System Prompt Cache - caches system prompts to reduce token usage
Caches both static base prompts and enhanced prompts with user context
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class PromptCache:
    """
    In-memory cache for system prompts with TTL-based expiration.
    Reduces token usage by caching static prompts and user-specific enhanced prompts.
    
    Cache Structure:
    - Static base prompts: `prompt_base_{agent_type}` (infinite TTL, invalidated manually)
    - Enhanced prompts: `prompt_enhanced_{agent_type}_{user_id}` (5 min TTL, auto-expires)
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        
        # TTL for enhanced prompts (user-specific, includes context)
        self._enhanced_prompt_ttl = timedelta(minutes=5)  # Same as user context cache
        
        # Version tracking for static prompts (for invalidation)
        self._prompt_version = "1.0"
    
    def _get_static_cache_key(self, agent_type: str) -> str:
        """
        Generate cache key for static base prompt.
        
        Args:
            agent_type: Type of agent (e.g., 'physical_fitness', 'nutrition', 'mental_fitness', 'coordinator')
        
        Returns:
            Cache key string
        """
        return f"prompt_base_{agent_type}"
    
    def _get_enhanced_cache_key(self, agent_type: str, user_id: int) -> str:
        """
        Generate cache key for enhanced prompt with user context.
        
        Args:
            agent_type: Type of agent
            user_id: User ID
        
        Returns:
            Cache key string
        """
        return f"prompt_enhanced_{agent_type}_{user_id}"
    
    def get_static_prompt(self, agent_type: str) -> Optional[str]:
        """
        Get cached static base prompt.
        
        Args:
            agent_type: Type of agent
        
        Returns:
            Cached prompt if available and valid, None otherwise
        """
        cache_key = self._get_static_cache_key(agent_type)
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # Check if version matches (for invalidation)
            if cached.get("version") == self._prompt_version:
                logger.info(f"✅ Cache HIT for static prompt: {agent_type}")
                return cached["prompt"]
            else:
                # Version mismatch, remove old cache
                logger.info(f"🔄 Cache EXPIRED (version mismatch) for static prompt: {agent_type}")
                del self._cache[cache_key]
        
        logger.info(f"❌ Cache MISS for static prompt: {agent_type}")
        return None
    
    def set_static_prompt(self, agent_type: str, prompt: str):
        """
        Cache static base prompt.
        
        Args:
            agent_type: Type of agent
            prompt: Static base prompt to cache
        """
        cache_key = self._get_static_cache_key(agent_type)
        
        self._cache[cache_key] = {
            "prompt": prompt,
            "timestamp": datetime.now(),
            "version": self._prompt_version
        }
        
        logger.info(f"💾 Cache SET for static prompt: {agent_type} ({len(prompt)} chars)")
    
    def get_enhanced_prompt(self, agent_type: str, user_id: int) -> Optional[str]:
        """
        Get cached enhanced prompt with user context.
        
        Args:
            agent_type: Type of agent
            user_id: User ID
        
        Returns:
            Cached enhanced prompt if available and not expired, None otherwise
        """
        cache_key = self._get_enhanced_cache_key(agent_type, user_id)
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            ttl = self._enhanced_prompt_ttl
            
            # Check if cache is still valid
            if datetime.now() - cached["timestamp"] < ttl:
                logger.info(f"✅ Cache HIT for enhanced prompt: {agent_type} (user_id={user_id})")
                return cached["prompt"]
            else:
                # Cache expired, remove it
                logger.info(f"⏰ Cache EXPIRED for enhanced prompt: {agent_type} (user_id={user_id})")
                del self._cache[cache_key]
        
        logger.info(f"❌ Cache MISS for enhanced prompt: {agent_type} (user_id={user_id})")
        return None
    
    def set_enhanced_prompt(self, agent_type: str, user_id: int, prompt: str):
        """
        Cache enhanced prompt with user context.
        
        Args:
            agent_type: Type of agent
            user_id: User ID
            prompt: Enhanced prompt with user context to cache
        """
        cache_key = self._get_enhanced_cache_key(agent_type, user_id)
        
        self._cache[cache_key] = {
            "prompt": prompt,
            "timestamp": datetime.now()
        }
        
        logger.info(f"💾 Cache SET for enhanced prompt: {agent_type} (user_id={user_id}, {len(prompt)} chars)")
    
    def invalidate_static_prompt(self, agent_type: Optional[str] = None):
        """
        Invalidate static prompt cache (e.g., when prompt files are updated).
        
        Args:
            agent_type: Specific agent type to invalidate, or None to invalidate all
        """
        if agent_type:
            cache_key = self._get_static_cache_key(agent_type)
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.info(f"🗑️ Invalidated static prompt cache: {agent_type}")
        else:
            # Invalidate all static prompts by incrementing version
            self._prompt_version = str(float(self._prompt_version) + 0.1)
            logger.info(f"🗑️ Invalidated all static prompt caches (version: {self._prompt_version})")
    
    def invalidate_enhanced_prompt(self, agent_type: Optional[str] = None, user_id: Optional[int] = None):
        """
        Invalidate enhanced prompt cache (e.g., when user context changes).
        
        Args:
            agent_type: Specific agent type to invalidate, or None for all
            user_id: Specific user ID to invalidate, or None for all users of this agent type
        """
        keys_to_remove = []
        
        for cache_key in list(self._cache.keys()):
            if cache_key.startswith("prompt_enhanced_"):
                # Parse: prompt_enhanced_{agent_type}_{user_id}
                parts = cache_key.split("_", 2)  # Split into ["prompt", "enhanced", "{agent_type}_{user_id}"]
                if len(parts) >= 3:
                    remaining = parts[2]  # "{agent_type}_{user_id}"
                    # Find last underscore to split agent_type and user_id
                    last_underscore = remaining.rfind("_")
                    if last_underscore > 0:
                        cached_agent_type = remaining[:last_underscore]
                        cached_user_id = int(remaining[last_underscore + 1:])
                        
                        # Check if this entry matches our criteria
                        if agent_type is None or cached_agent_type == agent_type:
                            if user_id is None or cached_user_id == user_id:
                                keys_to_remove.append(cache_key)
        
        for key in keys_to_remove:
            del self._cache[key]
        
        if keys_to_remove:
            logger.info(f"🗑️ Invalidated {len(keys_to_remove)} enhanced prompt cache entries "
                       f"(agent_type={agent_type}, user_id={user_id})")
    
    def clear(self):
        """Clear all cached prompts"""
        count = len(self._cache)
        self._cache.clear()
        logger.debug(f"Cleared {count} prompt cache entries")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats (total entries, static prompts, enhanced prompts)
        """
        stats = {
            "total_entries": len(self._cache),
            "static_prompts": 0,
            "enhanced_prompts": 0,
            "prompt_version": self._prompt_version,
            "by_agent_type": {}
        }
        
        for cache_key in self._cache.keys():
            if cache_key.startswith("prompt_base_"):
                stats["static_prompts"] += 1
                agent_type = cache_key.replace("prompt_base_", "")
                if agent_type not in stats["by_agent_type"]:
                    stats["by_agent_type"][agent_type] = {"static": 0, "enhanced": 0}
                stats["by_agent_type"][agent_type]["static"] += 1
            elif cache_key.startswith("prompt_enhanced_"):
                stats["enhanced_prompts"] += 1
                # Parse agent type from key
                parts = cache_key.split("_", 2)
                if len(parts) >= 3:
                    remaining = parts[2]
                    last_underscore = remaining.rfind("_")
                    if last_underscore > 0:
                        agent_type = remaining[:last_underscore]
                        if agent_type not in stats["by_agent_type"]:
                            stats["by_agent_type"][agent_type] = {"static": 0, "enhanced": 0}
                        stats["by_agent_type"][agent_type]["enhanced"] += 1
        
        return stats


# Singleton instance
prompt_cache = PromptCache()

