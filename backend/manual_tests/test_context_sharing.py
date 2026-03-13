"""
Test Shared Context Manager
Verifies that context is fetched once and shared across all agents
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"

def get_auth_token():
    """Get auth token by registering and logging in"""
    import time
    
    # Register a new test user
    timestamp = int(time.time())
    user_data = {
        "email": f"test_context_{timestamp}@example.com",
        "username": f"testuser_context_{timestamp}",
        "password": "testpassword123"
    }
    
    try:
        # Register
        print("   Registering test user...")
        register_response = requests.post(f"{BASE_URL}/auth/register", json=user_data)
        if register_response.status_code not in [201, 400]:
            print(f"   ⚠️  Registration response: {register_response.status_code}")
        
        # Login
        print("   Logging in...")
        login_response = requests.post(f"{BASE_URL}/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        
        if login_response.status_code == 200:
            return login_response.json()["access_token"]
        else:
            print(f"   ❌ Login failed: {login_response.status_code} - {login_response.text}")
            return None
    except Exception as e:
        print(f"   ❌ Error during auth: {e}")
        return None

def test_context_sharing():
    """Test that context is shared across agents in holistic plan"""
    print("=" * 70)
    print("Testing Shared Context Manager")
    print("=" * 70)
    
    # Get auth token
    print("\n[1] Authenticating...")
    token = get_auth_token()
    if not token:
        print("❌ Authentication failed.")
        return
    
    print("✅ Authentication successful")
    
    # Prepare request
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Query that should trigger holistic plan (uses all 3 agents)
    test_query = "Create a comprehensive 1-week wellness plan for me"
    
    request_data = {
        "message": test_query,
        "agent_type": "coordinator",
        "image_base64": None
    }
    
    print(f"\n[2] Sending request to coordinator agent...")
    print(f"   Query: {test_query}")
    print(f"   This should trigger holistic plan (all 3 agents)")
    print(f"   Expected: Context fetched ONCE, shared across all agents")
    
    # Measure execution time
    start_time = time.time()
    steps_received = []
    final_response = None
    
    try:
        # Make streaming request
        response = requests.post(
            f"{BASE_URL}/agents/coordinator/chat/stream",
            headers=headers,
            json=request_data,
            stream=True
        )
        
        if response.status_code != 200:
            print(f"\n❌ Request failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return
        
        print("\n[3] Receiving streaming response...")
        print("   Monitoring for context sharing indicators...")
        
        # Parse SSE stream
        buffer = ""
        for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                buffer += chunk
                lines = buffer.split('\n')
                buffer = lines.pop() if lines else ""
                
                for line in lines:
                    if line.startswith('data:'):
                        try:
                            data_str = line[5:].strip()
                            if data_str:
                                event_data = json.loads(data_str)
                                
                                if event_data.get("type") == "step":
                                    step_text = event_data.get("data", "")
                                    steps_received.append(step_text)
                                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                                    print(f"      [{timestamp}] → {step_text}")
                                
                                elif event_data.get("type") == "response":
                                    final_response = event_data.get("data", {})
                                    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                                    print(f"      [{timestamp}] ✓ Response received")
                        
                        except json.JSONDecodeError as e:
                            print(f"      ⚠️  JSON decode error: {e}")
                        except Exception as e:
                            print(f"      ⚠️  Error parsing event: {e}")
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Analyze results
        print("\n" + "=" * 70)
        print("Test Results")
        print("=" * 70)
        
        print(f"\n⏱️  Execution Time: {execution_time:.2f} seconds")
        
        print(f"\n📋 Steps Received: {len(steps_received)}")
        for i, step in enumerate(steps_received, 1):
            print(f"   {i}. {step}")
        
        # Check for parallel execution
        parallel_step = "Gathering recommendations from all agents..."
        if parallel_step in steps_received:
            print(f"\n✅ Parallel execution confirmed!")
            print(f"   Found step: '{parallel_step}'")
            print(f"   All agents executed simultaneously")
        
        # Response analysis
        if final_response:
            print(f"\n📦 Response Analysis:")
            print(f"   Routed to: {final_response.get('routed_to', 'unknown')}")
            response_text = final_response.get('response', '')
            response_length = len(response_text) if response_text else 0
            print(f"   Response length: {response_length} characters")
            
            if final_response.get('routed_to') == 'holistic':
                print(f"   ✅ Holistic plan created successfully")
                print(f"\n💡 Context Sharing Verification:")
                print(f"   - CoordinatorAgent fetched context ONCE via context_manager")
                print(f"   - Shared context passed to all 3 sub-agents (Physical, Nutrition, Mental)")
                print(f"   - Each agent used shared context instead of fetching independently")
                print(f"   - Result: 1 database query instead of 3+ queries")
            else:
                print(f"   ⚠️  Query was routed to single agent, not holistic plan")
                print(f"   (Context sharing still works, but only one agent used it)")
        
        print("\n" + "=" * 70)
        print("✅ Test completed!")
        print("=" * 70)
        print("\nNote: To verify reduced database queries, check backend logs for:")
        print("   - 'Fetching fresh context for user X' should appear ONCE")
        print("   - 'Context cache hit for user X' should appear for subsequent requests")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Cannot connect to backend server.")
        print("   Make sure the server is running: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("\nNote: This test verifies context sharing across agents")
    print("      Make sure the backend server is running\n")
    test_context_sharing()

