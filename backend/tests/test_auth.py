"""
Tests for authentication utilities
"""

import pytest
import os
from datetime import timedelta
from app.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token
)


class TestPasswordHashing:
    """Test password hashing and verification"""
    
    def test_password_hashing(self):
        """Test that password hashing works correctly"""
        password = "test_password_123"
        hashed = get_password_hash(password)
        
        # Hashed password should be different from plain password
        assert hashed != password
        assert len(hashed) > 0
        
        # Should be able to verify correct password
        assert verify_password(password, hashed) is True
        
        # Should reject wrong password
        assert verify_password("wrong_password", hashed) is False
    
    def test_password_hashing_different_hashes(self):
        """Test that same password produces different hashes (salt)"""
        password = "test_password_123"
        hashed1 = get_password_hash(password)
        hashed2 = get_password_hash(password)
        
        # Hashes should be different due to salt
        assert hashed1 != hashed2
        
        # But both should verify correctly
        assert verify_password(password, hashed1) is True
        assert verify_password(password, hashed2) is True
    
    def test_password_length_limit(self):
        """Test that passwords longer than 72 bytes are handled"""
        # Create a password longer than 72 bytes
        long_password = "a" * 100
        hashed = get_password_hash(long_password)
        
        # Should still hash (truncated to 72 bytes)
        assert hashed is not None
        assert len(hashed) > 0
        
        # Should verify with truncated password
        assert verify_password(long_password[:72], hashed) is True


class TestJWTTokens:
    """Test JWT token creation and decoding"""
    
    @pytest.fixture(autouse=True)
    def setup_jwt_secret(self, monkeypatch):
        """Set JWT_SECRET_KEY for testing"""
        # Use a test secret key
        test_secret = "test-secret-key-for-testing-purposes-minimum-32-chars"
        monkeypatch.setenv("JWT_SECRET_KEY", test_secret)
        # Reload the module to pick up the new secret
        import importlib
        import app.auth
        importlib.reload(app.auth)
    
    def test_jwt_token_creation(self):
        """Test that JWT tokens can be created"""
        data = {"sub": "123", "email": "test@example.com"}
        token = create_access_token(data)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_jwt_token_decoding(self):
        """Test that JWT tokens can be decoded correctly"""
        data = {"sub": "123", "email": "test@example.com"}
        token = create_access_token(data)
        
        payload = decode_access_token(token)
        
        assert payload is not None
        assert payload["sub"] == "123"
        assert payload["email"] == "test@example.com"
        assert "exp" in payload  # Expiration should be included
    
    def test_jwt_token_expiration(self):
        """Test that JWT tokens have expiration"""
        data = {"sub": "123"}
        token = create_access_token(data)
        payload = decode_access_token(token)
        
        assert payload is not None
        assert "exp" in payload
        
        # Expiration should be in the future
        from datetime import datetime
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp)
        assert exp_datetime > datetime.utcnow()
    
    def test_jwt_token_custom_expiration(self):
        """Test JWT token with custom expiration"""
        data = {"sub": "123"}
        expires_delta = timedelta(minutes=60)
        token = create_access_token(data, expires_delta=expires_delta)
        payload = decode_access_token(token)
        
        assert payload is not None
        assert "exp" in payload
    
    def test_jwt_token_invalid_token(self):
        """Test that invalid tokens return None"""
        invalid_token = "invalid.token.here"
        payload = decode_access_token(invalid_token)
        
        assert payload is None
    
    def test_jwt_token_empty_token(self):
        """Test that empty tokens return None"""
        payload = decode_access_token("")
        assert payload is None
        
        payload = decode_access_token(None)
        assert payload is None
    
    def test_jwt_token_with_whitespace(self):
        """Test that tokens with whitespace are cleaned"""
        data = {"sub": "123"}
        token = create_access_token(data)
        
        # Test with whitespace
        payload1 = decode_access_token(f" {token} ")
        payload2 = decode_access_token(f'"{token}"')
        payload3 = decode_access_token(f"'{token}'")
        
        assert payload1 is not None
        assert payload2 is not None
        assert payload3 is not None
        assert payload1["sub"] == "123"
        assert payload2["sub"] == "123"
        assert payload3["sub"] == "123"

