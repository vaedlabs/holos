"""
Workout log routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.schemas.logs import WorkoutLogResponse, WorkoutLogsListResponse

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/workouts", response_model=WorkoutLogsListResponse)
async def get_workout_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    limit: Optional[int] = Query(default=50, ge=1, le=100, description="Maximum number of logs to return"),
    offset: Optional[int] = Query(default=0, ge=0, description="Number of logs to skip")
):
    """Get current user's workout logs"""
    try:
        # Query workout logs for the current user, ordered by most recent first
        logs_query = db.query(WorkoutLog).filter(
            WorkoutLog.user_id == current_user.id
        ).order_by(desc(WorkoutLog.workout_date))
        
        # Get total count
        total = logs_query.count()
        
        # Apply pagination
        logs = logs_query.offset(offset).limit(limit).all()
        
        return WorkoutLogsListResponse(
            logs=logs,
            total=total
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve workout logs: {str(e)}"
        )

