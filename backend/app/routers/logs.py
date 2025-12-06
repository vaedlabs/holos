"""
Log routes - Workout, Nutrition, and Mental Fitness logs
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from app.dependencies import get_database, get_current_user
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.models.nutrition_log import NutritionLog
from app.models.mental_fitness_log import MentalFitnessLog
from app.schemas.logs import (
    WorkoutLogResponse, WorkoutLogsListResponse,
    NutritionLogResponse, NutritionLogsListResponse,
    MentalFitnessLogResponse, MentalFitnessLogsListResponse
)

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


@router.get("/nutrition", response_model=NutritionLogsListResponse)
async def get_nutrition_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    limit: Optional[int] = Query(default=50, ge=1, le=100, description="Maximum number of logs to return"),
    offset: Optional[int] = Query(default=0, ge=0, description="Number of logs to skip")
):
    """Get current user's nutrition logs"""
    try:
        # Query nutrition logs for the current user, ordered by most recent first
        logs_query = db.query(NutritionLog).filter(
            NutritionLog.user_id == current_user.id
        ).order_by(desc(NutritionLog.meal_date))
        
        # Get total count
        total = logs_query.count()
        
        # Apply pagination
        logs = logs_query.offset(offset).limit(limit).all()
        
        return NutritionLogsListResponse(
            logs=logs,
            total=total
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve nutrition logs: {str(e)}"
        )


@router.get("/mental-fitness", response_model=MentalFitnessLogsListResponse)
async def get_mental_fitness_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    limit: Optional[int] = Query(default=50, ge=1, le=100, description="Maximum number of logs to return"),
    offset: Optional[int] = Query(default=0, ge=0, description="Number of logs to skip")
):
    """Get current user's mental fitness logs"""
    try:
        # Query mental fitness logs for the current user, ordered by most recent first
        logs_query = db.query(MentalFitnessLog).filter(
            MentalFitnessLog.user_id == current_user.id
        ).order_by(desc(MentalFitnessLog.activity_date))
        
        # Get total count
        total = logs_query.count()
        
        # Apply pagination
        logs = logs_query.offset(offset).limit(limit).all()
        
        return MentalFitnessLogsListResponse(
            logs=logs,
            total=total
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve mental fitness logs: {str(e)}"
        )


@router.delete("/workouts/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Delete a workout log by ID"""
    try:
        log = db.query(WorkoutLog).filter(
            WorkoutLog.id == log_id,
            WorkoutLog.user_id == current_user.id
        ).first()
        
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workout log not found"
            )
        
        db.delete(log)
        db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete workout log: {str(e)}"
        )


@router.delete("/nutrition/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_nutrition_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Delete a nutrition log by ID"""
    try:
        log = db.query(NutritionLog).filter(
            NutritionLog.id == log_id,
            NutritionLog.user_id == current_user.id
        ).first()
        
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nutrition log not found"
            )
        
        db.delete(log)
        db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete nutrition log: {str(e)}"
        )


@router.delete("/mental-fitness/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mental_fitness_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database)
):
    """Delete a mental fitness log by ID"""
    try:
        log = db.query(MentalFitnessLog).filter(
            MentalFitnessLog.id == log_id,
            MentalFitnessLog.user_id == current_user.id
        ).first()
        
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mental fitness log not found"
            )
        
        db.delete(log)
        db.commit()
        return None
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete mental fitness log: {str(e)}"
        )

