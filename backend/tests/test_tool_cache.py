"""
Tests for Tool Cache - tool result caching
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from app.services.tool_cache import ToolCache, tool_cache


class TestToolCache:
    """Test ToolCache functionality"""
    
    @pytest.fixture
    def cache(self):
        """Create a fresh ToolCache instance"""
        return ToolCache()
    
    def test_cache_key_generation(self, cache):
        """Test that cache keys are generated correctly"""
        key1 = cache._get_cache_key("get_medical_history", user_id=1, query="")
        key2 = cache._get_cache_key("get_medical_history", user_id=1, query="")
        key3 = cache._get_cache_key("get_medical_history", user_id=2, query="")
        key4 = cache._get_cache_key("get_user_preferences", user_id=1, query="")
        
        # Same parameters should generate same key
        assert key1 == key2
        
        # Different user_id should generate different key
        assert key1 != key3
        
        # Different tool should generate different key
        assert key1 != key4
    
    def test_cache_set_and_get(self, cache):
        """Test basic cache set and get operations"""
        result = "Test result"
        cache.set("get_medical_history", result, user_id=1, query="")
        
        cached = cache.get("get_medical_history", user_id=1, query="")
        assert cached == result
    
    def test_cache_miss(self, cache):
        """Test that cache returns None for non-existent entries"""
        cached = cache.get("get_medical_history", user_id=1, query="")
        assert cached is None
    
    def test_cache_ttl_expiration(self, cache):
        """Test that cache entries expire after TTL"""
        result = "Test result"
        cache.set("get_medical_history", result, user_id=1, query="")
        
        # Should be cached immediately
        cached = cache.get("get_medical_history", user_id=1, query="")
        assert cached == result
        
        # Manually expire the cache by setting old timestamp
        cache_key = cache._get_cache_key("get_medical_history", user_id=1, query="")
        cache._cache[cache_key]["timestamp"] = datetime.now() - timedelta(minutes=10)  # 10 minutes ago
        
        # Should return None after expiration
        cached = cache.get("get_medical_history", user_id=1, query="")
        assert cached is None
        # Cache entry should be removed
        assert cache_key not in cache._cache
    
    def test_cache_different_ttl_per_tool(self, cache):
        """Test that different tools have different TTLs"""
        # get_medical_history has 5 minute TTL
        cache.set("get_medical_history", "result1", user_id=1)
        cache_key1 = cache._get_cache_key("get_medical_history", user_id=1)
        
        # web_search has 1 hour TTL
        cache.set("web_search", "result2", query="test")
        cache_key2 = cache._get_cache_key("web_search", query="test")
        
        # Expire get_medical_history (5 min TTL)
        cache._cache[cache_key1]["timestamp"] = datetime.now() - timedelta(minutes=6)
        
        # Expire web_search (1 hour TTL) - but only 6 minutes have passed
        cache._cache[cache_key2]["timestamp"] = datetime.now() - timedelta(minutes=6)
        
        # get_medical_history should be expired
        assert cache.get("get_medical_history", user_id=1) is None
        
        # web_search should still be cached (6 min < 1 hour)
        assert cache.get("web_search", query="test") == "result2"
    
    def test_cache_invalidate(self, cache):
        """Test that cache invalidation works"""
        result = "Test result"
        cache.set("get_medical_history", result, user_id=1, query="")
        
        # Should be cached
        assert cache.get("get_medical_history", user_id=1, query="") == result
        
        # Invalidate
        cache.invalidate("get_medical_history", user_id=1, query="")
        
        # Should be gone
        assert cache.get("get_medical_history", user_id=1, query="") is None
    
    def test_cache_clear(self, cache):
        """Test that clearing cache removes all entries"""
        cache.set("get_medical_history", "result1", user_id=1)
        cache.set("get_user_preferences", "result2", user_id=1)
        cache.set("web_search", "result3", query="test")
        
        assert len(cache._cache) == 3
        
        cache.clear()
        
        assert len(cache._cache) == 0
    
    def test_cache_stats(self, cache):
        """Test that cache statistics are generated correctly"""
        cache.set("get_medical_history", "result1", user_id=1)
        cache.set("get_medical_history", "result2", user_id=2)
        cache.set("get_user_preferences", "result3", user_id=1)
        cache.set("web_search", "result4", query="test")
        
        stats = cache.get_stats()
        
        assert stats["total_entries"] == 4
        assert "get_medical_history" in stats["tools"]
        assert stats["tools"]["get_medical_history"] == 2
        assert "get_user_preferences" in stats["tools"]
        assert stats["tools"]["get_user_preferences"] == 1
        assert "web_search" in stats["tools"]
        assert stats["tools"]["web_search"] == 1
    
    def test_cache_user_id_in_key(self, cache):
        """Test that user_id is included in cache key for user-specific tools"""
        # Same tool, different users should have different cache entries
        cache.set("get_medical_history", "user1_result", user_id=1, query="")
        cache.set("get_medical_history", "user2_result", user_id=2, query="")
        
        assert cache.get("get_medical_history", user_id=1, query="") == "user1_result"
        assert cache.get("get_medical_history", user_id=2, query="") == "user2_result"
    
    def test_cache_without_user_id(self, cache):
        """Test that tools without user_id work correctly"""
        cache.set("web_search", "search_result", query="test query")
        
        cached = cache.get("web_search", query="test query")
        assert cached == "search_result"
        
        # Different query should be different cache entry
        cached2 = cache.get("web_search", query="different query")
        assert cached2 is None


class TestToolCacheIntegration:
    """Test tool cache integration with actual tools"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock()
    
    @pytest.fixture
    def mock_env_vars(self, monkeypatch):
        """Set up mock environment variables"""
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-minimum-32-characters-long")
    
    def test_get_medical_history_tool_uses_cache(self, mock_db, mock_env_vars):
        """Test that GetMedicalHistoryTool uses cache"""
        from app.agents.base_agent import GetMedicalHistoryTool
        from app.services.medical_service import get_medical_history
        from sqlalchemy.orm import Session
        
        # Create a proper mock Session
        mock_session = Mock(spec=Session)
        
        # Mock get_medical_history to track calls
        call_count = [0]
        
        def mock_get_medical_history(user_id, db):
            call_count[0] += 1
            return None
        
        tool = GetMedicalHistoryTool(user_id=1, db=mock_session)
        
        with patch('app.agents.base_agent.get_medical_history', side_effect=mock_get_medical_history):
            # First call - should hit database
            result1 = tool._run("")
            assert call_count[0] == 1
            
            # Second call - should use cache
            result2 = tool._run("")
            assert call_count[0] == 1  # Should not increment
            
            # Results should be the same
            assert result1 == result2
    
    def test_get_user_preferences_tool_uses_cache(self, mock_db, mock_env_vars):
        """Test that GetUserPreferencesTool uses cache"""
        from app.agents.base_agent import GetUserPreferencesTool
        from app.models.user_preferences import UserPreferences
        from sqlalchemy.orm import Session
        
        # Create a proper mock Session
        mock_session = Mock(spec=Session)
        
        # Mock database query
        mock_preferences = Mock()
        mock_preferences.goals = "Build muscle"
        mock_preferences.exercise_types = None
        mock_preferences.activity_level = None
        mock_preferences.location = None
        mock_preferences.dietary_restrictions = None
        
        query_mock = Mock()
        filter_mock = Mock()
        filter_mock.first.return_value = mock_preferences
        query_mock.filter.return_value = filter_mock
        mock_session.query.return_value = query_mock
        
        tool = GetUserPreferencesTool(user_id=1, db=mock_session)
        
        # First call - should hit database
        result1 = tool._run("")
        assert mock_session.query.called
        
        # Reset mock
        mock_session.query.reset_mock()
        
        # Second call - should use cache
        result2 = tool._run("")
        # Should not query database again
        assert not mock_session.query.called
        
        # Results should be the same
        assert result1 == result2
    
    def test_web_search_tool_uses_cache(self, mock_db, mock_env_vars):
        """Test that WebSearchTool uses cache"""
        from app.agents.base_agent import WebSearchTool
        
        tool = WebSearchTool()
        
        # Mock Tavily client
        mock_client = Mock()
        mock_response = {
            "results": [
                {"title": "Test", "url": "http://test.com", "content": "Test content"}
            ]
        }
        mock_client.search.return_value = mock_response
        
        # Patch the import inside the _run method
        with patch('tavily.TavilyClient', return_value=mock_client):
            with patch.dict('os.environ', {'TAVILY_API_KEY': 'test-key'}):
                # First call - should hit API
                result1 = tool._run("test query")
                assert mock_client.search.called
                assert "Test" in result1
                
                # Reset mock
                mock_client.search.reset_mock()
                
                # Second call - should use cache
                result2 = tool._run("test query")
                # Should not call API again
                assert not mock_client.search.called
                
                # Results should be the same
                assert result1 == result2
    
    def test_cache_invalidation_on_data_update(self, mock_db, mock_env_vars):
        """Test that cache can be invalidated when data is updated"""
        from app.services.tool_cache import tool_cache
        from app.agents.base_agent import GetMedicalHistoryTool
        from sqlalchemy.orm import Session
        
        # Create a proper mock Session
        mock_session = Mock(spec=Session)
        
        tool = GetMedicalHistoryTool(user_id=1, db=mock_session)
        
        # Clear cache first to ensure fresh calls
        tool_cache.clear()
        
        # Mock get_medical_history - return a proper mock with all attributes
        # Create a mock that behaves like a real MedicalHistory object
        # Use a simple object that is truthy
        class MockMedicalHistory:
            def __init__(self):
                self.conditions = "Initial condition"
                self.limitations = None
                self.medications = None
                self.notes = None
        
        mock_history = MockMedicalHistory()
        
        # Ensure the mock returns True for truthiness checks
        def mock_get_medical_history(user_id, db):
            return mock_history
        
        with patch('app.agents.base_agent.get_medical_history', side_effect=mock_get_medical_history):
            # First call - should get the mock history
            result1 = tool._run("")
            assert "Initial condition" in result1
            
            # Update mock (create new instance to simulate data change)
            mock_history.conditions = "Updated condition"
            
            # Second call - should still return cached (old) result
            result2 = tool._run("")
            assert "Initial condition" in result2
            
            # Invalidate cache
            tool_cache.invalidate("get_medical_history", user_id=1, query="")
            
            # Third call - should fetch fresh data
            result3 = tool._run("")
            assert "Updated condition" in result3

