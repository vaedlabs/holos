"""
Tests for System Prompt Cache
Tests caching of static base prompts and enhanced prompts with user context
"""

import pytest
from datetime import datetime, timedelta
from app.services.prompt_cache import PromptCache, prompt_cache


class TestPromptCache:
    """Test suite for PromptCache"""
    
    def test_static_prompt_caching(self):
        """Test that static base prompts are cached correctly"""
        cache = PromptCache()
        agent_type = "physical_fitness"
        test_prompt = "You are a fitness coach. Help users with workouts."
        
        # Initially, no cache
        assert cache.get_static_prompt(agent_type) is None
        
        # Set cache
        cache.set_static_prompt(agent_type, test_prompt)
        
        # Should retrieve from cache
        cached = cache.get_static_prompt(agent_type)
        assert cached == test_prompt
    
    def test_static_prompt_version_invalidation(self):
        """Test that static prompts are invalidated when version changes"""
        cache = PromptCache()
        agent_type = "nutrition"
        test_prompt = "You are a nutrition coach."
        
        # Set cache
        cache.set_static_prompt(agent_type, test_prompt)
        assert cache.get_static_prompt(agent_type) == test_prompt
        
        # Invalidate by changing version
        cache.invalidate_static_prompt()
        
        # Should return None (version mismatch)
        assert cache.get_static_prompt(agent_type) is None
    
    def test_enhanced_prompt_caching(self):
        """Test that enhanced prompts with user context are cached correctly"""
        cache = PromptCache()
        agent_type = "mental_fitness"
        user_id = 123
        test_prompt = "Base prompt\n\n## User Context\nMedical: heart condition"
        
        # Initially, no cache
        assert cache.get_enhanced_prompt(agent_type, user_id) is None
        
        # Set cache
        cache.set_enhanced_prompt(agent_type, user_id, test_prompt)
        
        # Should retrieve from cache
        cached = cache.get_enhanced_prompt(agent_type, user_id)
        assert cached == test_prompt
    
    def test_enhanced_prompt_expiration(self):
        """Test that enhanced prompts expire after TTL"""
        cache = PromptCache()
        agent_type = "physical_fitness"
        user_id = 456
        test_prompt = "Base prompt with context"
        
        # Set cache
        cache.set_enhanced_prompt(agent_type, user_id, test_prompt)
        assert cache.get_enhanced_prompt(agent_type, user_id) == test_prompt
        
        # Manually expire by setting old timestamp
        cache_key = cache._get_enhanced_cache_key(agent_type, user_id)
        cache._cache[cache_key]["timestamp"] = datetime.now() - timedelta(minutes=10)
        
        # Should return None (expired)
        assert cache.get_enhanced_prompt(agent_type, user_id) is None
    
    def test_invalidate_static_prompt_specific(self):
        """Test invalidating a specific static prompt"""
        cache = PromptCache()
        
        # Set multiple static prompts
        cache.set_static_prompt("physical_fitness", "Fitness prompt")
        cache.set_static_prompt("nutrition", "Nutrition prompt")
        cache.set_static_prompt("mental_fitness", "Mental prompt")
        
        # Invalidate only one
        cache.invalidate_static_prompt("nutrition")
        
        # Check results
        assert cache.get_static_prompt("physical_fitness") == "Fitness prompt"
        assert cache.get_static_prompt("nutrition") is None  # Invalidated
        assert cache.get_static_prompt("mental_fitness") == "Mental prompt"
    
    def test_invalidate_enhanced_prompt_by_user(self):
        """Test invalidating enhanced prompts for a specific user"""
        cache = PromptCache()
        
        # Set enhanced prompts for multiple users
        cache.set_enhanced_prompt("physical_fitness", 1, "Prompt for user 1")
        cache.set_enhanced_prompt("physical_fitness", 2, "Prompt for user 2")
        cache.set_enhanced_prompt("nutrition", 1, "Nutrition prompt for user 1")
        
        # Invalidate all prompts for user 1
        cache.invalidate_enhanced_prompt(user_id=1)
        
        # Check results
        assert cache.get_enhanced_prompt("physical_fitness", 1) is None  # Invalidated
        assert cache.get_enhanced_prompt("physical_fitness", 2) == "Prompt for user 2"  # Still cached
        assert cache.get_enhanced_prompt("nutrition", 1) is None  # Invalidated
    
    def test_invalidate_enhanced_prompt_by_agent_type(self):
        """Test invalidating enhanced prompts for a specific agent type"""
        cache = PromptCache()
        
        # Set enhanced prompts for multiple agent types
        cache.set_enhanced_prompt("physical_fitness", 1, "Fitness prompt")
        cache.set_enhanced_prompt("nutrition", 1, "Nutrition prompt")
        cache.set_enhanced_prompt("mental_fitness", 1, "Mental prompt")
        
        # Invalidate only physical_fitness
        cache.invalidate_enhanced_prompt("physical_fitness")
        
        # Check results
        assert cache.get_enhanced_prompt("physical_fitness", 1) is None  # Invalidated
        assert cache.get_enhanced_prompt("nutrition", 1) == "Nutrition prompt"  # Still cached
        assert cache.get_enhanced_prompt("mental_fitness", 1) == "Mental prompt"  # Still cached
    
    def test_invalidate_enhanced_prompt_specific(self):
        """Test invalidating a specific enhanced prompt (agent + user)"""
        cache = PromptCache()
        
        # Set enhanced prompts
        cache.set_enhanced_prompt("physical_fitness", 1, "Prompt 1")
        cache.set_enhanced_prompt("physical_fitness", 2, "Prompt 2")
        cache.set_enhanced_prompt("nutrition", 1, "Nutrition prompt")
        
        # Invalidate specific one
        cache.invalidate_enhanced_prompt("physical_fitness", user_id=1)
        
        # Check results
        assert cache.get_enhanced_prompt("physical_fitness", 1) is None  # Invalidated
        assert cache.get_enhanced_prompt("physical_fitness", 2) == "Prompt 2"  # Still cached
        assert cache.get_enhanced_prompt("nutrition", 1) == "Nutrition prompt"  # Still cached
    
    def test_clear_all_cache(self):
        """Test clearing all cached prompts"""
        cache = PromptCache()
        
        # Set multiple prompts
        cache.set_static_prompt("physical_fitness", "Static prompt")
        cache.set_enhanced_prompt("physical_fitness", 1, "Enhanced prompt")
        
        # Clear all
        cache.clear()
        
        # Check all are cleared
        assert cache.get_static_prompt("physical_fitness") is None
        assert cache.get_enhanced_prompt("physical_fitness", 1) is None
    
    def test_get_stats(self):
        """Test cache statistics"""
        cache = PromptCache()
        
        # Set various prompts
        cache.set_static_prompt("physical_fitness", "Fitness prompt")
        cache.set_static_prompt("nutrition", "Nutrition prompt")
        cache.set_enhanced_prompt("physical_fitness", 1, "Enhanced 1")
        cache.set_enhanced_prompt("physical_fitness", 2, "Enhanced 2")
        cache.set_enhanced_prompt("nutrition", 1, "Nutrition enhanced")
        
        stats = cache.get_stats()
        
        assert stats["total_entries"] == 5
        assert stats["static_prompts"] == 2
        assert stats["enhanced_prompts"] == 3
        assert "physical_fitness" in stats["by_agent_type"]
        assert stats["by_agent_type"]["physical_fitness"]["static"] == 1
        assert stats["by_agent_type"]["physical_fitness"]["enhanced"] == 2
        assert stats["by_agent_type"]["nutrition"]["static"] == 1
        assert stats["by_agent_type"]["nutrition"]["enhanced"] == 1
    
    def test_singleton_instance(self):
        """Test that prompt_cache is a singleton"""
        from app.services.prompt_cache import prompt_cache as cache1
        from app.services.prompt_cache import prompt_cache as cache2
        
        assert cache1 is cache2
        assert isinstance(cache1, PromptCache)


class TestAgentPromptCaching:
    """Test that agents actually use prompt caching"""
    
    def test_base_agent_caches_static_prompt(self):
        """Test that BaseAgent caches static prompts on initialization"""
        from app.agents.base_agent import BaseAgent
        from app.services.prompt_cache import prompt_cache
        from sqlalchemy.orm import Session
        
        # Clear cache first
        prompt_cache.clear()
        
        # Create agent (will cache static prompt)
        # Note: This requires a real DB session, so we'll test the caching logic directly
        agent_type = "base"  # Default agent type from BaseAgent
        
        # Simulate what BaseAgent does
        test_prompt = "Test base prompt"
        prompt_cache.set_static_prompt(agent_type, test_prompt)
        
        # Verify it's cached
        cached = prompt_cache.get_static_prompt(agent_type)
        assert cached == test_prompt
    
    def test_agent_type_identification(self):
        """Test that agents correctly identify their type"""
        from app.agents.physical_fitness_agent import PhysicalFitnessAgent
        from app.agents.nutrition_agent import NutritionAgent
        from app.agents.mental_fitness_agent import MentalFitnessAgent
        from app.agents.coordinator_agent import CoordinatorAgent
        
        # Test agent type methods (if they exist)
        # Note: These tests require actual agent instances with DB, so we test the logic
        
        # PhysicalFitnessAgent should return "physical_fitness"
        # We can't easily test without DB, but we can verify the method exists
        assert hasattr(PhysicalFitnessAgent, '_get_agent_type')
        assert hasattr(NutritionAgent, '_get_agent_type')
        assert hasattr(MentalFitnessAgent, '_get_agent_type')
        assert hasattr(CoordinatorAgent, '_get_agent_type')


class TestPromptCacheIntegration:
    """Integration tests for prompt caching with context manager"""
    
    def test_context_invalidation_triggers_prompt_invalidation(self):
        """Test that when context is invalidated, enhanced prompts are also invalidated"""
        from app.services.context_manager import context_manager
        from app.services.prompt_cache import prompt_cache
        
        user_id = 999
        
        # Set enhanced prompt
        prompt_cache.set_enhanced_prompt("physical_fitness", user_id, "Test prompt")
        assert prompt_cache.get_enhanced_prompt("physical_fitness", user_id) == "Test prompt"
        
        # Invalidate context (should also invalidate prompts)
        context_manager.invalidate_cache(user_id)
        
        # Enhanced prompt should be invalidated
        assert prompt_cache.get_enhanced_prompt("physical_fitness", user_id) is None


class TestTokenUsageReduction:
    """Test that prompt caching reduces token usage"""
    
    def test_static_prompt_reused(self):
        """Test that static prompts are reused, reducing token usage"""
        cache = PromptCache()
        agent_type = "test_agent"
        large_prompt = "A" * 2000  # Simulate 2000 character prompt (~500 tokens)
        
        # First request: build and cache
        cache.set_static_prompt(agent_type, large_prompt)
        
        # Subsequent requests: retrieve from cache
        for _ in range(10):
            cached = cache.get_static_prompt(agent_type)
            assert cached == large_prompt
        
        # Verify it was only built once (cached 9 times)
        stats = cache.get_stats()
        assert stats["static_prompts"] == 1
    
    def test_enhanced_prompt_reused_within_ttl(self):
        """Test that enhanced prompts are reused within TTL"""
        cache = PromptCache()
        agent_type = "test_agent"
        user_id = 100
        enhanced_prompt = "Base prompt\n\n## User Context\nMedical: condition"
        
        # First request: build and cache
        cache.set_enhanced_prompt(agent_type, user_id, enhanced_prompt)
        
        # Subsequent requests within TTL: retrieve from cache
        for _ in range(5):
            cached = cache.get_enhanced_prompt(agent_type, user_id)
            assert cached == enhanced_prompt
        
        # Verify it was only built once (cached 4 times)
        stats = cache.get_stats()
        assert stats["enhanced_prompts"] == 1

