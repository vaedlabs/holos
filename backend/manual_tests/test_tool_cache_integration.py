"""
Integration test script to verify tool caching works in real application usage.
Run this script to test caching behavior with actual API calls.
"""

import asyncio
import requests
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
TEST_EMAIL = "cache_test@example.com"
TEST_PASSWORD = "testpassword123"
TEST_USERNAME = "cache_test_user"

def register_user() -> Dict[str, Any]:
    """Register a test user"""
    print("📝 Registering test user...")
    response = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "username": TEST_USERNAME
        }
    )
    if response.status_code == 201:
        print("✅ User registered successfully")
        return response.json()
    elif response.status_code == 400:
        print("ℹ️  User already exists, attempting login...")
        return login_user()
    else:
        print(f"❌ Registration failed: {response.status_code} - {response.text}")
        return None

def login_user() -> Dict[str, Any]:
    """Login and get access token"""
    print("🔐 Logging in...")
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={
            "username": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
    )
    if response.status_code == 200:
        print("✅ Login successful")
        return response.json()
    else:
        print(f"❌ Login failed: {response.status_code} - {response.text}")
        return None

def setup_user_data(token: str):
    """Set up medical history and preferences for testing"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("📋 Setting up medical history...")
    response = requests.post(
        f"{BASE_URL}/medical-history",
        headers=headers,
        json={
            "conditions": "Test condition for caching",
            "limitations": "No heavy lifting",
            "medications": "None",
            "notes": "Cache test user"
        }
    )
    if response.status_code == 201:
        print("✅ Medical history created")
    else:
        print(f"ℹ️  Medical history: {response.status_code}")
    
    print("⚙️  Setting up user preferences...")
    response = requests.post(
        f"{BASE_URL}/preferences",
        headers=headers,
        json={
            "goals": "Build muscle",
            "exercise_types": "Weight training",
            "activity_level": "Moderate",
            "location": "Gym",
            "dietary_restrictions": "None"
        }
    )
    if response.status_code == 200:
        print("✅ Preferences created")
    else:
        print(f"ℹ️  Preferences: {response.status_code}")

def test_caching_with_agent(token: str, agent_type: str = "physical-fitness"):
    """Test caching by making multiple agent calls and checking logs"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print(f"\n🧪 Testing caching with {agent_type} agent...")
    print("=" * 60)
    
    # First call - should be cache MISS
    print("\n📞 Call 1: First request (should be cache MISS)")
    start_time = time.time()
    response1 = requests.post(
        f"{BASE_URL}/agents/{agent_type}/chat",
        headers=headers,
        json={
            "message": "What exercises should I do?",
            "agent_type": agent_type
        }
    )
    time1 = time.time() - start_time
    
    if response1.status_code == 200:
        data1 = response1.json()
        print(f"✅ Response received in {time1:.2f}s")
        print(f"   Response preview: {data1.get('response', '')[:100]}...")
    else:
        print(f"❌ Request failed: {response1.status_code} - {response1.text}")
        return
    
    # Wait a moment
    time.sleep(0.5)
    
    # Second call - should be cache HIT for tools
    print("\n📞 Call 2: Second request (should be cache HIT for tools)")
    start_time = time.time()
    response2 = requests.post(
        f"{BASE_URL}/agents/{agent_type}/chat",
        headers=headers,
        json={
            "message": "Tell me more about those exercises",
            "agent_type": agent_type
        }
    )
    time2 = time.time() - start_time
    
    if response2.status_code == 200:
        data2 = response2.json()
        print(f"✅ Response received in {time2:.2f}s")
        print(f"   Response preview: {data2.get('response', '')[:100]}...")
        
        # Compare response times
        if time2 < time1:
            print(f"   ⚡ Speed improvement: {((time1 - time2) / time1 * 100):.1f}% faster")
        else:
            print(f"   ⚠️  No speed improvement (may be due to LLM processing time)")
    else:
        print(f"❌ Request failed: {response2.status_code} - {response2.text}")
        return
    
    # Third call - should still be cache HIT
    print("\n📞 Call 3: Third request (should still be cache HIT)")
    start_time = time.time()
    response3 = requests.post(
        f"{BASE_URL}/agents/{agent_type}/chat",
        headers=headers,
        json={
            "message": "What are my preferences?",
            "agent_type": agent_type
        }
    )
    time3 = time.time() - start_time
    
    if response3.status_code == 200:
        data3 = response3.json()
        print(f"✅ Response received in {time3:.2f}s")
        print(f"   Response preview: {data3.get('response', '')[:100]}...")
    else:
        print(f"❌ Request failed: {response3.status_code} - {response3.text}")
        return
    
    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"   Call 1: {time1:.2f}s (cache MISS)")
    print(f"   Call 2: {time2:.2f}s (cache HIT)")
    print(f"   Call 3: {time3:.2f}s (cache HIT)")
    print("\n💡 Check backend logs for cache HIT/MISS messages")
    print("   Look for: ✅ Cache HIT, ❌ Cache MISS, 💾 Cache SET")

def get_cache_stats(token: str):
    """Get cache statistics (if we add an endpoint for it)"""
    headers = {"Authorization": f"Bearer {token}"}
    
    # This would require adding a cache stats endpoint
    # For now, we'll just print instructions
    print("\n📊 To view cache statistics:")
    print("   1. Check backend logs for cache HIT/MISS messages")
    print("   2. Or add a GET /cache/stats endpoint to view cache stats")

def main():
    """Main test function"""
    print("🚀 Tool Cache Integration Test")
    print("=" * 60)
    print("\n⚠️  Make sure the backend server is running on http://localhost:8000")
    print("⚠️  Make sure logging is set to INFO level to see cache messages")
    print()
    
    # Register/Login
    auth_data = register_user()
    if not auth_data:
        print("❌ Failed to authenticate")
        return
    
    token = auth_data.get("access_token")
    if not token:
        print("❌ No access token received")
        return
    
    # Setup user data
    setup_user_data(token)
    
    # Test caching
    test_caching_with_agent(token, "physical-fitness")
    
    print("\n✅ Test complete!")
    print("\n💡 Tips:")
    print("   - Check backend console/logs for cache HIT/MISS messages")
    print("   - Cache TTLs: medical_history=5min, preferences=5min, web_search=1hour")
    print("   - Subsequent calls within TTL should show cache HITs")
    print("   - Calls after TTL expiration will show cache MISS")

if __name__ == "__main__":
    main()

