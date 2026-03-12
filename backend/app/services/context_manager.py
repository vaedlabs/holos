"""
Context Manager - Shared context service for agents.

This module provides the ContextManager class, which manages shared user context
(medical history and preferences) with in-memory caching. It eliminates redundant
database queries by fetching user context once per request and sharing it across
multiple agents.

Key Features:
- In-memory caching with TTL-based expiration (5 minutes)
- Shared context across multiple agents in the same request
- Automatic cache invalidation when user data changes
- Integration with prompt cache invalidation

Performance Benefits:
- Reduces database queries (fetch once, use many times)
- Improves response time for multi-agent requests
- Reduces database load
- Context is cached per user for 5 minutes

Context Structure:
    {
        "medical_history": {
            "conditions": str,
            "limitations": str,
            "medications": str,
            "notes": str
        },
        "preferences": {
            "goals": str,
            "activity_level": str,
            "dietary_restrictions": str,
            "location": str,
            "exercise_types": str,
            "age": int,
            "gender": str,
            "lifestyle": str
        }
    }
"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.services.medical_service import get_medical_history
from app.models.user_preferences import UserPreferences
import logging

# Logger instance for this module
# Used for logging cache hits, misses, and operations
logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manages shared user context with in-memory caching.
    
    This class provides a centralized way to fetch and cache user context
    (medical history and preferences) for use across multiple agents. It
    eliminates redundant database queries by caching context per user.
    
    Usage Pattern:
        1. Coordinator agent calls get_user_context() at start of request
        2. Context is cached for 5 minutes (TTL)
        3. All agents in the request share the same context
        4. Context is invalidated when user data changes
    
    Cache Strategy:
        - Per-user caching (each user has their own cache entry)
        - TTL-based expiration (5 minutes default)
        - Cache key format: "user_context_{user_id}"
        - Cache includes both medical_history and preferences
        
    Integration:
        - Works with prompt_cache to invalidate enhanced prompts
        - When context is invalidated, enhanced prompts are also invalidated
        - Ensures consistency between context and prompts
        
    Attributes:
        _cache: Dictionary storing cached user contexts (key -> cache data)
        _cache_ttl: Time-to-live for cache entries (default: 5 minutes)
        
    Note:
        - Singleton pattern: Use the global context_manager instance
        - In-memory cache (lost on server restart)
        - For production with multiple workers, consider Redis for shared cache
    """
    
    def __init__(self, cache_ttl_minutes: int = 5):
        """
        Initialize ContextManager with cache configuration.
        
        Args:
            cache_ttl_minutes: Time-to-live for cache entries in minutes (default: 5)
                             Context expires after this duration
                             Matches enhanced prompt cache TTL for consistency
        """
        # In-memory cache dictionary
        # Key: Cache key string (e.g., "user_context_123")
        # Value: Dictionary with data and timestamp
        self._cache: Dict[str, Dict] = {}
        
        # TTL for cache entries
        # Context expires after this duration to ensure fresh data
        # Default: 5 minutes (matches enhanced prompt cache TTL)
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
    
    def _get_cache_key(self, user_id: int) -> str:
        """
        Generate cache key for user context.
        
        This method creates a cache key for storing user context. The key
        is user-specific, allowing per-user caching.
        
        Args:
            user_id: User ID for cache key generation
        
        Returns:
            str: Cache key in format "user_context_{user_id}"
            
        Example:
            user_id=123 -> "user_context_123"
            
        Note:
            - Cache key is user-specific
            - Simple format for easy debugging
        """
        return f"user_context_{user_id}"
    
    def get_user_context(
        self, 
        user_id: int, 
        db: Session, 
        force_refresh: bool = False
    ) -> Dict[str, Optional[Dict]]:
        """
        Get user context (medical history + preferences) with caching.
        
        This method retrieves user context (medical history and preferences)
        with automatic caching. Context is fetched once and cached for 5 minutes
        to avoid redundant database queries.
        
        Args:
            user_id: User ID to fetch context for
            db: Database session for querying user data
            force_refresh: If True, bypass cache and fetch fresh data
                          Useful when data is known to have changed
        
        Returns:
            Dict[str, Optional[Dict]]: Dictionary with context:
                {
                    "medical_history": {
                        "conditions": str or None,
                        "limitations": str or None,
                        "medications": str or None,
                        "notes": str or None
                    } or None,
                    "preferences": {
                        "goals": str or None,
                        "activity_level": str or None,
                        "dietary_restrictions": str or None,
                        "location": str or None,
                        "exercise_types": str or None,
                        "age": int or None,
                        "gender": str or None,
                        "lifestyle": str or None
                    } or None
                }
                
        Cache Flow:
            1. Check cache if not forcing refresh
            2. If cache hit and not expired, return cached context
            3. If cache miss or expired, fetch from database
            4. Build context dictionary from database results
            5. Cache context with timestamp
            6. Return context
            
        Database Queries:
            - Fetches medical history via get_medical_history()
            - Fetches user preferences via database query
            - Both queries are executed only on cache miss
            
        Note:
            - Context is cached per user for 5 minutes
            - force_refresh bypasses cache (useful after data updates)
            - Returns None for missing data (no medical history or preferences)
        """
        cache_key = self._get_cache_key(user_id)
        
        # Check cache if not forcing refresh
        # Cache hit: Return cached context if not expired
        if not force_refresh and cache_key in self._cache:
            cached = self._cache[cache_key]
            # Check if cache is still valid (within TTL window)
            if datetime.now() - cached["timestamp"] < self._cache_ttl:
                logger.debug(f"Context cache hit for user {user_id}")
                return cached["data"]
            else:
                # Cache expired, remove it
                # Expired entries are removed to prevent memory leaks
                logger.debug(f"Context cache expired for user {user_id}")
                self._cache.pop(cache_key, None)
        
        # Fetch fresh context from database
        # Cache miss or expired - fetch from database
        logger.debug(f"Fetching fresh context for user {user_id}")
        
        # Fetch medical history
        medical_history = get_medical_history(user_id, db)
        
        # Fetch user preferences
        preferences = db.query(UserPreferences).filter(
            UserPreferences.user_id == user_id
        ).first()
        
        # Build context dictionary
        # Structure matches what agents expect for shared context
        context = {
            "medical_history": {
                "conditions": medical_history.conditions if medical_history else None,
                "limitations": medical_history.limitations if medical_history else None,
                "medications": medical_history.medications if medical_history else None,
                "notes": medical_history.notes if medical_history else None,
            } if medical_history else None,
            "preferences": {
                "goals": preferences.goals if preferences else None,
                "activity_level": preferences.activity_level if preferences else None,
                "dietary_restrictions": preferences.dietary_restrictions if preferences else None,
                "location": preferences.location if preferences else None,
                "exercise_types": preferences.exercise_types if preferences else None,
                "age": preferences.age if preferences else None,
                "gender": preferences.gender if preferences else None,
                "lifestyle": preferences.lifestyle if preferences else None,
            } if preferences else None,
        }
        
        # Cache the context with timestamp
        # Context will be available for 5 minutes (TTL)
        self._cache[cache_key] = {
            "data": context,  # The actual context data
            "timestamp": datetime.now()  # Cache timestamp (for TTL calculation)
        }
        
        return context
    
    def invalidate_cache(self, user_id: int):
        """
        Invalidate cached context for a user.
        
        This method removes cached context for a user and also invalidates
        enhanced prompt cache. Call this when user data (medical history or
        preferences) is updated to ensure fresh data on next request.
        
        Args:
            user_id: User ID whose cache should be invalidated
            
        Invalidation Actions:
            1. Removes context cache entry for user
            2. Invalidates enhanced prompt cache for user (all agent types)
            
        Integration:
            - Also invalidates enhanced prompt cache
            - Ensures consistency between context and prompts
            - Prevents stale data in prompts
            
        Usage:
            - Call after updating medical history
            - Call after updating user preferences
            - Ensures next request gets fresh data
            
        Note:
            - Safe to call even if cache entry doesn't exist
            - Invalidates prompts for all agent types for this user
        """
        cache_key = self._get_cache_key(user_id)
        if cache_key in self._cache:
            logger.debug(f"Invalidating context cache for user {user_id}")
            self._cache.pop(cache_key, None)
        
        # Also invalidate enhanced prompt cache for this user (all agent types)
        # Enhanced prompts include user context, so they must be invalidated too
        from app.services.prompt_cache import prompt_cache
        prompt_cache.invalidate_enhanced_prompt(user_id=user_id)
    
    def clear_all_cache(self):
        """
        Clear all cached contexts.
        
        This method removes all cached user contexts from memory. Useful for
        testing or memory management when cache needs to be reset.
        
        Note:
            - Clears all user contexts (not selective)
            - Useful for testing or memory management
            - Does not invalidate prompt cache (call separately if needed)
        """
        logger.debug("Clearing all context cache")
        self._cache.clear()


# Singleton instance - shared across all requests
# Global instance used throughout the application
# All agents share the same context manager instance for consistency
# Note: In production with multiple workers, consider using Redis for shared cache
#       Current in-memory cache is per-process (not shared across workers)
context_manager = ContextManager()

