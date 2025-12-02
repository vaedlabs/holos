"""
Test script to verify image files are deleted when clearing conversations or deleting accounts.

Usage:
    python test_image_deletion.py

This script will:
1. Create a test user and upload an image
2. Verify the image file exists
3. Test clearing conversation history (should delete image)
4. Test account deletion (should delete image)
"""

import os
import sys
import requests
import base64
from pathlib import Path
from io import BytesIO
from PIL import Image

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, engine
from app.models.user import User
from app.models.conversation_message import ConversationMessage

API_URL = os.getenv("API_URL", "http://localhost:8000")
UPLOADS_DIR = Path("uploads/images")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def create_test_image():
    """Create a simple test image and return it as base64"""
    # Create a simple 100x100 red image
    img = Image.new('RGB', (100, 100), color='red')
    buffer = BytesIO()
    img.save(buffer, format='JPEG')
    img_bytes = buffer.getvalue()
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    return img_base64


def get_image_files_for_user(user_id: int):
    """Get all image files for a specific user"""
    user_images = []
    if UPLOADS_DIR.exists():
        for file in UPLOADS_DIR.glob(f"{user_id}_*.jpg"):
            user_images.append(file)
    return user_images


def test_clear_conversation_deletes_images():
    """Test that clearing conversation history deletes associated images"""
    print("\n" + "="*60)
    print("TEST 1: Clear Conversation History - Image Deletion")
    print("="*60)
    
    # Create test user
    test_email = f"test_clear_{os.urandom(4).hex()}@example.com"
    test_password = "testpass123"
    
    # Register user
    register_response = requests.post(
        f"{API_URL}/auth/register",
        json={
            "email": test_email,
            "username": f"test_clear_{os.urandom(4).hex()}",
            "password": test_password
        }
    )
    
    if register_response.status_code != 201:
        print(f"❌ Failed to register user: {register_response.text}")
        return False
    
    user_data = register_response.json()
    user_id = user_data["id"]
    print(f"✅ Created test user: {user_id} ({test_email})")
    
    # Login to get token
    login_response = requests.post(
        f"{API_URL}/auth/login",
        json={"email": test_email, "password": test_password}
    )
    
    if login_response.status_code != 200:
        print(f"❌ Failed to login: {login_response.text}")
        return False
    
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Upload an image
    img_base64 = create_test_image()
    upload_response = requests.post(
        f"{API_URL}/conversation/upload-image",
        headers=headers,
        data={"image_base64": img_base64}
    )
    
    if upload_response.status_code != 200:
        print(f"❌ Failed to upload image: {upload_response.text}")
        return False
    
    image_path = upload_response.json()["image_path"]
    filename = image_path.split('/')[-1]
    image_file = UPLOADS_DIR / filename
    
    print(f"✅ Uploaded image: {image_path}")
    
    # Verify image file exists
    if not image_file.exists():
        print(f"❌ Image file does not exist: {image_file}")
        return False
    
    print(f"✅ Verified image file exists: {image_file}")
    
    # Save a message with the image
    save_response = requests.post(
        f"{API_URL}/conversation/messages",
        headers=headers,
        json={
            "role": "user",
            "content": "Test message with image",
            "image_path": image_path,
            "agent_type": "nutrition"
        }
    )
    
    if save_response.status_code != 200:
        print(f"❌ Failed to save message: {save_response.text}")
        return False
    
    print(f"✅ Saved message with image")
    
    # Check user's image files before clearing
    user_images_before = get_image_files_for_user(user_id)
    print(f"📊 User images before clear: {len(user_images_before)} files")
    
    # Clear conversation history
    clear_response = requests.delete(
        f"{API_URL}/conversation/messages",
        headers=headers
    )
    
    if clear_response.status_code != 204:
        print(f"❌ Failed to clear conversation: {clear_response.text}")
        return False
    
    print(f"✅ Cleared conversation history")
    
    # Verify image file is deleted
    if image_file.exists():
        print(f"❌ Image file still exists after clearing: {image_file}")
        return False
    
    print(f"✅ Image file deleted successfully: {image_file}")
    
    # Check user's image files after clearing
    user_images_after = get_image_files_for_user(user_id)
    print(f"📊 User images after clear: {len(user_images_after)} files")
    
    if len(user_images_after) >= len(user_images_before):
        print(f"⚠️  Warning: Image count didn't decrease (might be other images)")
    
    print("✅ TEST 1 PASSED: Clear conversation deletes images")
    return True


def test_delete_account_deletes_images():
    """Test that deleting account deletes all user's images"""
    print("\n" + "="*60)
    print("TEST 2: Delete Account - Image Deletion")
    print("="*60)
    
    # Create test user
    test_email = f"test_delete_{os.urandom(4).hex()}@example.com"
    test_password = "testpass123"
    
    # Register user
    register_response = requests.post(
        f"{API_URL}/auth/register",
        json={
            "email": test_email,
            "username": f"test_delete_{os.urandom(4).hex()}",
            "password": test_password
        }
    )
    
    if register_response.status_code != 201:
        print(f"❌ Failed to register user: {register_response.text}")
        return False
    
    user_data = register_response.json()
    user_id = user_data["id"]
    print(f"✅ Created test user: {user_id} ({test_email})")
    
    # Login to get token
    login_response = requests.post(
        f"{API_URL}/auth/login",
        json={"email": test_email, "password": test_password}
    )
    
    if login_response.status_code != 200:
        print(f"❌ Failed to login: {login_response.text}")
        return False
    
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Upload multiple images
    image_files = []
    for i in range(3):
        img_base64 = create_test_image()
        upload_response = requests.post(
            f"{API_URL}/conversation/upload-image",
            headers=headers,
            data={"image_base64": img_base64}
        )
        
        if upload_response.status_code != 200:
            print(f"❌ Failed to upload image {i+1}: {upload_response.text}")
            continue
        
        image_path = upload_response.json()["image_path"]
        filename = image_path.split('/')[-1]
        image_file = UPLOADS_DIR / filename
        image_files.append(image_file)
        
        # Save message with image
        requests.post(
            f"{API_URL}/conversation/messages",
            headers=headers,
            json={
                "role": "user",
                "content": f"Test message {i+1} with image",
                "image_path": image_path,
                "agent_type": "nutrition"
            }
        )
    
    print(f"✅ Uploaded {len(image_files)} images")
    
    # Verify all image files exist
    for img_file in image_files:
        if not img_file.exists():
            print(f"❌ Image file does not exist: {img_file}")
            return False
    
    print(f"✅ Verified all {len(image_files)} image files exist")
    
    # Check user's image files before deletion
    user_images_before = get_image_files_for_user(user_id)
    print(f"📊 User images before account deletion: {len(user_images_before)} files")
    
    # Delete account
    delete_response = requests.delete(
        f"{API_URL}/auth/delete-account",
        headers=headers
    )
    
    if delete_response.status_code != 204:
        print(f"❌ Failed to delete account: {delete_response.text}")
        return False
    
    print(f"✅ Deleted account")
    
    # Verify all image files are deleted
    all_deleted = True
    for img_file in image_files:
        if img_file.exists():
            print(f"❌ Image file still exists after account deletion: {img_file}")
            all_deleted = False
    
    if not all_deleted:
        return False
    
    print(f"✅ All {len(image_files)} image files deleted successfully")
    
    # Check user's image files after deletion
    user_images_after = get_image_files_for_user(user_id)
    print(f"📊 User images after account deletion: {len(user_images_after)} files")
    
    if len(user_images_after) > 0:
        print(f"⚠️  Warning: Some image files still exist for user {user_id}")
        for img in user_images_after:
            print(f"   - {img}")
    
    print("✅ TEST 2 PASSED: Delete account deletes all user images")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("IMAGE DELETION TEST SUITE")
    print("="*60)
    print(f"API URL: {API_URL}")
    print(f"Uploads directory: {UPLOADS_DIR.absolute()}")
    
    # Check if backend is running
    try:
        health_check = requests.get(f"{API_URL}/docs", timeout=2)
        print("✅ Backend is running")
    except requests.exceptions.RequestException:
        print("❌ Backend is not running. Please start the backend server first.")
        print("   Run: cd backend && uvicorn app.main:app --reload")
        return
    
    results = []
    
    # Test 1: Clear conversation deletes images
    try:
        result1 = test_clear_conversation_deletes_images()
        results.append(("Clear Conversation", result1))
    except Exception as e:
        print(f"❌ TEST 1 FAILED with exception: {e}")
        results.append(("Clear Conversation", False))
    
    # Test 2: Delete account deletes images
    try:
        result2 = test_delete_account_deletes_images()
        results.append(("Delete Account", result2))
    except Exception as e:
        print(f"❌ TEST 2 FAILED with exception: {e}")
        results.append(("Delete Account", False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(result[1] for result in results)
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*60)


if __name__ == "__main__":
    main()


