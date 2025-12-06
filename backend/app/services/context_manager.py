"""
Context Manager - Shared context service for agents
Eliminates redundant database queries by caching and sharing user context
"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.services.medical_service import get_medical_history
from app.models.user_preferences import UserPreferences
import logging

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manages shared user context with in-memory caching.
    Fetches medical history and preferences once per request and shares across agents.
    """
    
    def __init__(self, cache_ttl_minutes: int = 5):
        """
        Initialize ContextManager.
        
        Args:
            cache_ttl_minutes: Time-to-live for cache entries in minutes (default: 5)
        """
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = timedelta(minutes=cache_ttl_minutes)
    
    def _get_cache_key(self, user_id: int) -> str:
        """Generate cache key for user"""
        return f"user_context_{user_id}"
    
    def get_user_context(
        self, 
        user_id: int, 
        db: Session, 
        force_refresh: bool = False
    ) -> Dict[str, Optional[Dict]]:
        """
        Get user context (medical history + preferences) with caching.
        
        Args:
            user_id: User ID
            db: Database session
            force_refresh: If True, bypass cache and fetch fresh data
        
        Returns:
            Dictionary with 'medical_history' and 'preferences' keys
        """
        cache_key = self._get_cache_key(user_id)
        
        # Check cache if not forcing refresh
        if not force_refresh and cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.now() - cached["timestamp"] < self._cache_ttl:
                logger.debug(f"Context cache hit for user {user_id}")
                return cached["data"]
            else:
                # Cache expired, remove it
                logger.debug(f"Context cache expired for user {user_id}")
                self._cache.pop(cache_key, None)
        
        # Fetch fresh context
        logger.debug(f"Fetching fresh context for user {user_id}")
        
        medical_history = get_medical_history(user_id, db)
        preferences = db.query(UserPreferences).filter(
            UserPreferences.user_id == user_id
        ).first()
        
        # Build context dictionary
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
        
        # Cache the context
        self._cache[cache_key] = {
            "data": context,
            "timestamp": datetime.now()
        }
        
        return context
    
    def invalidate_cache(self, user_id: int):
        """
        Invalidate cached context for a user.
        Call this when user data is updated.
        Also invalidates enhanced prompt cache for this user.
        
        Args:
            user_id: User ID
        """
        cache_key = self._get_cache_key(user_id)
        if cache_key in self._cache:
            logger.debug(f"Invalidating context cache for user {user_id}")
            self._cache.pop(cache_key, None)
        
        # Also invalidate enhanced prompt cache for this user (all agent types)
        from app.services.prompt_cache import prompt_cache
        prompt_cache.invalidate_enhanced_prompt(user_id=user_id)
    
    def clear_all_cache(self):
        """Clear all cached contexts (useful for testing or memory management)"""
        logger.debug("Clearing all context cache")
        self._cache.clear()


# Singleton instance - shared across all requests
# Note: In production with multiple workers, consider using Redis for shared cache
context_manager = ContextManager()

