"""
Log routes for managing workout, nutrition, and mental fitness logs.

This module provides FastAPI router endpoints for log management:
- Get logs: Retrieve user's workout, nutrition, or mental fitness logs with pagination
- Delete logs: Delete specific log entries by ID

Key Features:
- Workout logs: Exercise and workout tracking
- Nutrition logs: Meal and food tracking
- Mental fitness logs: Mindfulness and wellness activity tracking
- Pagination support: Limit and offset for efficient data retrieval
- User isolation: Users can only access and delete their own logs

Log Types:
- WorkoutLog: Exercise sessions, workouts, training activities
- NutritionLog: Meals, food intake, nutritional data
- MentalFitnessLog: Mindfulness practices, stress management activities, wellness activities

Pagination:
- Default limit: 50 logs per page
- Maximum limit: 100 logs per page
- Minimum limit: 1 log per page
- Offset: Number of logs to skip for pagination
- Ordered by most recent first (descending date order)

Security:
- All endpoints require authentication (get_current_user dependency)
- Users can only access and delete their own logs
- Logs are filtered by user_id to ensure data isolation
- Delete operations verify log ownership before deletion

Usage:
    GET /logs/workouts - Get workout logs with pagination
    GET /logs/nutrition - Get nutrition logs with pagination
    GET /logs/mental-fitness - Get mental fitness logs with pagination
    DELETE /logs/workouts/{log_id} - Delete workout log
    DELETE /logs/nutrition/{log_id} - Delete nutrition log
    DELETE /logs/mental-fitness/{log_id} - Delete mental fitness log
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

# FastAPI router for log management endpoints
# Prefix: /logs (all routes will be prefixed with /logs)
# Tags: ["logs"] (for API documentation grouping)
router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/workouts", response_model=WorkoutLogsListResponse)
async def get_workout_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    limit: Optional[int] = Query(default=50, ge=1, le=100, description="Maximum number of logs to return"),
    offset: Optional[int] = Query(default=0, ge=0, description="Number of logs to skip")
):
    """
    Get current user's workout logs with pagination.
    
    This endpoint retrieves the authenticated user's workout logs, ordered by
    most recent first. Supports pagination for efficient data retrieval.
    
    Workout Logs Include:
        - Exercise sessions and workouts
        - Training activities
        - Workout dates and details
        - Exercise information
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Ensures users can only access their own logs
        db: Database session (injected dependency)
        limit: Optional[int] - Maximum number of logs to return (1-100, default: 50)
        offset: Optional[int] - Number of logs to skip for pagination (default: 0)
    
    Returns:
        WorkoutLogsListResponse containing:
            - logs: List[WorkoutLog] (list of workout logs)
            - total: int (total number of logs for pagination)
            
    Raises:
        HTTPException 500: If database query fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only access their own workout logs (filtered by user_id)
        
    Ordering:
        - Logs ordered by workout_date DESC (most recent first)
        
    Example:
        GET /logs/workouts?limit=20&offset=0
        
        Returns first 20 most recent workout logs
    """
    try:
        # Query workout logs for the current user, ordered by most recent first
        # Filter by user_id to ensure users can only access their own logs
        logs_query = db.query(WorkoutLog).filter(
            WorkoutLog.user_id == current_user.id  # Security: Only current user's logs
        ).order_by(desc(WorkoutLog.workout_date))  # Most recent first
        
        # Get total count
        # Total count needed for pagination UI (before applying limit/offset)
        total = logs_query.count()
        
        # Apply pagination
        # Skip 'offset' logs and return 'limit' logs
        logs = logs_query.offset(offset).limit(limit).all()
        
        # Return paginated response
        return WorkoutLogsListResponse(
            logs=logs,  # List of workout logs
            total=total  # Total count for pagination
        )
    except Exception as e:
        # Handle database query errors
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
    """
    Get current user's nutrition logs with pagination.
    
    This endpoint retrieves the authenticated user's nutrition logs, ordered by
    most recent first. Supports pagination for efficient data retrieval.
    
    Nutrition Logs Include:
        - Meals and food intake
        - Nutritional data (calories, macronutrients)
        - Meal dates and details
        - Food items and portion information
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Ensures users can only access their own logs
        db: Database session (injected dependency)
        limit: Optional[int] - Maximum number of logs to return (1-100, default: 50)
        offset: Optional[int] - Number of logs to skip for pagination (default: 0)
    
    Returns:
        NutritionLogsListResponse containing:
            - logs: List[NutritionLog] (list of nutrition logs)
            - total: int (total number of logs for pagination)
            
    Raises:
        HTTPException 500: If database query fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only access their own nutrition logs (filtered by user_id)
        
    Ordering:
        - Logs ordered by meal_date DESC (most recent first)
        
    Example:
        GET /logs/nutrition?limit=20&offset=0
        
        Returns first 20 most recent nutrition logs
    """
    try:
        # Query nutrition logs for the current user, ordered by most recent first
        # Filter by user_id to ensure users can only access their own logs
        logs_query = db.query(NutritionLog).filter(
            NutritionLog.user_id == current_user.id  # Security: Only current user's logs
        ).order_by(desc(NutritionLog.meal_date))  # Most recent first
        
        # Get total count
        # Total count needed for pagination UI (before applying limit/offset)
        total = logs_query.count()
        
        # Apply pagination
        # Skip 'offset' logs and return 'limit' logs
        logs = logs_query.offset(offset).limit(limit).all()
        
        # Return paginated response
        return NutritionLogsListResponse(
            logs=logs,  # List of nutrition logs
            total=total  # Total count for pagination
        )
    except Exception as e:
        # Handle database query errors
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
    """
    Get current user's mental fitness logs with pagination.
    
    This endpoint retrieves the authenticated user's mental fitness logs, ordered by
    most recent first. Supports pagination for efficient data retrieval.
    
    Mental Fitness Logs Include:
        - Mindfulness practices (meditation, breathing exercises)
        - Stress management activities
        - Wellness activities
        - Activity dates and details
        - Duration and notes
    
    Args:
        current_user: Authenticated user (injected dependency)
                     Ensures users can only access their own logs
        db: Database session (injected dependency)
        limit: Optional[int] - Maximum number of logs to return (1-100, default: 50)
        offset: Optional[int] - Number of logs to skip for pagination (default: 0)
    
    Returns:
        MentalFitnessLogsListResponse containing:
            - logs: List[MentalFitnessLog] (list of mental fitness logs)
            - total: int (total number of logs for pagination)
            
    Raises:
        HTTPException 500: If database query fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only access their own mental fitness logs (filtered by user_id)
        
    Ordering:
        - Logs ordered by activity_date DESC (most recent first)
        
    Example:
        GET /logs/mental-fitness?limit=20&offset=0
        
        Returns first 20 most recent mental fitness logs
    """
    try:
        # Query mental fitness logs for the current user, ordered by most recent first
        # Filter by user_id to ensure users can only access their own logs
        logs_query = db.query(MentalFitnessLog).filter(
            MentalFitnessLog.user_id == current_user.id  # Security: Only current user's logs
        ).order_by(desc(MentalFitnessLog.activity_date))  # Most recent first
        
        # Get total count
        # Total count needed for pagination UI (before applying limit/offset)
        total = logs_query.count()
        
        # Apply pagination
        # Skip 'offset' logs and return 'limit' logs
        logs = logs_query.offset(offset).limit(limit).all()
        
        # Return paginated response
        return MentalFitnessLogsListResponse(
            logs=logs,  # List of mental fitness logs
            total=total  # Total count for pagination
        )
    except Exception as e:
        # Handle database query errors
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
    """
    Delete a workout log by ID.
    
    This endpoint deletes a specific workout log entry. The log must belong to
    the authenticated user. Returns 204 No Content on successful deletion.
    
    Args:
        log_id: int - ID of the workout log to delete
        current_user: Authenticated user (injected dependency)
                     Ensures users can only delete their own logs
        db: Database session (injected dependency)
    
    Returns:
        None: 204 No Content response on successful deletion
        
    Raises:
        HTTPException 404: If workout log not found or doesn't belong to user
        HTTPException 500: If deletion fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only delete their own workout logs (filtered by user_id)
        - Log ownership verified before deletion
        
    Example:
        DELETE /logs/workouts/123
        
        Deletes workout log with ID 123 (if it belongs to current user)
    """
    try:
        # Query workout log by ID and user_id
        # Filter by both log_id and user_id to ensure ownership
        log = db.query(WorkoutLog).filter(
            WorkoutLog.id == log_id,  # Log ID
            WorkoutLog.user_id == current_user.id  # Security: Only current user's logs
        ).first()
        
        # Check if log exists and belongs to user
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workout log not found"
            )
        
        # Delete log and commit transaction
        db.delete(log)
        db.commit()
        return None  # 204 No Content response
    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as e:
        # Rollback transaction on error
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
    """
    Delete a nutrition log by ID.
    
    This endpoint deletes a specific nutrition log entry. The log must belong to
    the authenticated user. Returns 204 No Content on successful deletion.
    
    Args:
        log_id: int - ID of the nutrition log to delete
        current_user: Authenticated user (injected dependency)
                     Ensures users can only delete their own logs
        db: Database session (injected dependency)
    
    Returns:
        None: 204 No Content response on successful deletion
        
    Raises:
        HTTPException 404: If nutrition log not found or doesn't belong to user
        HTTPException 500: If deletion fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only delete their own nutrition logs (filtered by user_id)
        - Log ownership verified before deletion
        
    Example:
        DELETE /logs/nutrition/123
        
        Deletes nutrition log with ID 123 (if it belongs to current user)
    """
    try:
        # Query nutrition log by ID and user_id
        # Filter by both log_id and user_id to ensure ownership
        log = db.query(NutritionLog).filter(
            NutritionLog.id == log_id,  # Log ID
            NutritionLog.user_id == current_user.id  # Security: Only current user's logs
        ).first()
        
        # Check if log exists and belongs to user
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nutrition log not found"
            )
        
        # Delete log and commit transaction
        db.delete(log)
        db.commit()
        return None  # 204 No Content response
    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as e:
        # Rollback transaction on error
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
    """
    Delete a mental fitness log by ID.
    
    This endpoint deletes a specific mental fitness log entry. The log must belong to
    the authenticated user. Returns 204 No Content on successful deletion.
    
    Args:
        log_id: int - ID of the mental fitness log to delete
        current_user: Authenticated user (injected dependency)
                     Ensures users can only delete their own logs
        db: Database session (injected dependency)
    
    Returns:
        None: 204 No Content response on successful deletion
        
    Raises:
        HTTPException 404: If mental fitness log not found or doesn't belong to user
        HTTPException 500: If deletion fails
        
    Security:
        - Requires authentication (get_current_user dependency)
        - Users can only delete their own mental fitness logs (filtered by user_id)
        - Log ownership verified before deletion
        
    Example:
        DELETE /logs/mental-fitness/123
        
        Deletes mental fitness log with ID 123 (if it belongs to current user)
    """
    try:
        # Query mental fitness log by ID and user_id
        # Filter by both log_id and user_id to ensure ownership
        log = db.query(MentalFitnessLog).filter(
            MentalFitnessLog.id == log_id,  # Log ID
            MentalFitnessLog.user_id == current_user.id  # Security: Only current user's logs
        ).first()
        
        # Check if log exists and belongs to user
        if not log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mental fitness log not found"
            )
        
        # Delete log and commit transaction
        db.delete(log)
        db.commit()
        return None  # 204 No Content response
    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as e:
        # Rollback transaction on error
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete mental fitness log: {str(e)}"
        )

