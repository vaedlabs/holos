"""The account's logged entries, newest first, and deleting one (C.17 writes them).

    GET    /logs/workouts | /logs/nutrition | /logs/mental-fitness   ?limit=50&offset=0
    DELETE /logs/workouts/{id} | /logs/nutrition/{id} | /logs/mental-fitness/{id}

Every query is filtered by the signed-in user, so another account's entry looks like no
entry (404).
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_database
from app.models.mental_fitness_log import MentalFitnessLog
from app.models.nutrition_log import NutritionLog
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.routers.errors import ApiError
from app.schemas.logs import (
    MentalFitnessLogsListResponse,
    NutritionLogsListResponse,
    WorkoutLogsListResponse,
)

router = APIRouter(prefix="/logs", tags=["logs"])

LIMIT = Query(default=50, ge=1, le=100, description="Maximum number of logs to return")
OFFSET = Query(default=0, ge=0, description="Number of logs to skip")


def _page(db: Session, model, newest_first, user_id: int, limit: int, offset: int) -> dict:
    query = db.query(model).filter(model.user_id == user_id).order_by(desc(newest_first))
    return {"logs": query.offset(offset).limit(limit).all(), "total": query.count()}


def _delete(db: Session, model, log_id: int, user_id: int) -> None:
    entry = db.query(model).filter(model.id == log_id, model.user_id == user_id).first()
    if entry is None:
        raise ApiError(404, "not_found", "There is no such entry.")
    db.delete(entry)
    db.commit()


@router.get("/workouts", response_model=WorkoutLogsListResponse)
def get_workout_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    limit: int = LIMIT,
    offset: int = OFFSET,
):
    return _page(db, WorkoutLog, WorkoutLog.workout_date, current_user.id, limit, offset)


@router.get("/nutrition", response_model=NutritionLogsListResponse)
def get_nutrition_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    limit: int = LIMIT,
    offset: int = OFFSET,
):
    return _page(db, NutritionLog, NutritionLog.meal_date, current_user.id, limit, offset)


@router.get("/mental-fitness", response_model=MentalFitnessLogsListResponse)
def get_mental_fitness_logs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
    limit: int = LIMIT,
    offset: int = OFFSET,
):
    return _page(db, MentalFitnessLog, MentalFitnessLog.activity_date, current_user.id,
                 limit, offset)


@router.delete("/workouts/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> None:
    _delete(db, WorkoutLog, log_id, current_user.id)


@router.delete("/nutrition/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_nutrition_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> None:
    _delete(db, NutritionLog, log_id, current_user.id)


@router.delete("/mental-fitness/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mental_fitness_log(
    log_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_database),
) -> None:
    _delete(db, MentalFitnessLog, log_id, current_user.id)
