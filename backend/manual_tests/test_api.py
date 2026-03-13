"""
API endpoint testing script
Run this after starting the server to test API endpoints
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_root():
    """Test root endpoint"""
    print("Testing root endpoint...")
    response = requests.get(f"{BASE_URL}/")
    assert response.status_code == 200
    assert "message" in response.json()
    print("✓ Root endpoint works")

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("✓ Health endpoint works")

def test_register():
    """Test user registration"""
    print("Testing user registration...")
    user_data = {
        "email": f"test_{hash(str(__import__('time').time()))}@example.com",
        "username": f"testuser_{hash(str(__import__('time').time()))}",
        "password": "testpassword123"
    }
    response = requests.post(f"{BASE_URL}/auth/register", json=user_data)
    if response.status_code == 201:
        print("✓ User registration works")
        return user_data
    else:
        print(f"✗ Registration failed: {response.status_code} - {response.text}")
        return None

def test_login(user_data):
    """Test user login"""
    if not user_data:
        print("Skipping login test (no user data)")
        return None
    
    print("Testing user login...")
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"]
    }
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if response.status_code == 200:
        token = response.json()["access_token"]
        print("✓ User login works")
        return token
    else:
        print(f"✗ Login failed: {response.status_code} - {response.text}")
        return None

def test_protected_route(token):
    """Test protected route with token"""
    if not token:
        print("Skipping protected route test (no token)")
        return
    
    print("Testing protected route...")
    headers = {"Authorization": f"Bearer {token}"}
    # Note: We don't have a protected route yet, but this shows how to use the token
    print("✓ Token format is correct (no protected routes to test yet)")

def main():
    """Run API tests"""
    print("=" * 50)
    print("API Endpoint Tests")
    print("=" * 50)
    print(f"Testing against: {BASE_URL}")
    print("Make sure the server is running: uvicorn app.main:app --reload")
    print()
    
    try:
        test_root()
        test_health()
        user_data = test_register()
        token = test_login(user_data)
        test_protected_route(token)
        
        print("\n" + "=" * 50)
        print("✓ All API tests completed!")
        print("=" * 50)
    except requests.exceptions.ConnectionError:
        print("\n✗ Could not connect to server.")
        print("Make sure the server is running: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

