"""
Cache statistics and management endpoints
"""

from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.models.user import User
from app.services.tool_cache import tool_cache
from typing import Dict, Any

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats")
async def get_cache_stats(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get cache statistics.
    Requires authentication.
    """
    stats = tool_cache.get_stats()
    return {
        "cache_stats": stats,
        "message": "Cache statistics retrieved successfully"
    }


@router.post("/clear")
async def clear_cache(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Clear all cache entries.
    Requires authentication.
    """
    tool_cache.clear()
    return {
        "message": "Cache cleared successfully"
    }


@router.post("/invalidate/{tool_name}")
async def invalidate_tool_cache(
    tool_name: str,
    user_id: int = None,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Invalidate cache for a specific tool.
    If user_id is provided, invalidates cache for that user.
    Otherwise, invalidates all cache entries for the tool.
    """
    if user_id:
        tool_cache.invalidate_user(user_id, tool_name)
        return {
            "message": f"Cache invalidated for {tool_name} (user_id={user_id})"
        }
    else:
        # Invalidate all entries for this tool
        # This is a simplified version - in production, you might want more control
        stats = tool_cache.get_stats()
        count = stats["tools"].get(tool_name, 0)
        tool_cache.clear()  # For now, clear all (could be improved)
        return {
            "message": f"Cache cleared (was {count} entries for {tool_name})"
        }

