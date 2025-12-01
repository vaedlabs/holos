"""
Medical Service - Handles medical history and exercise conflict detection
"""

from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from app.models.medical_history import MedicalHistory
from app.models.user import User


def get_medical_history(user_id: int, db: Session) -> Optional[MedicalHistory]:
    """Get medical history for a user"""
    return db.query(MedicalHistory).filter(MedicalHistory.user_id == user_id).first()


def update_medical_history(user_id: int, data: dict, db: Session) -> MedicalHistory:
    """Create or update medical history for a user"""
    medical_history = get_medical_history(user_id, db)
    
    if medical_history:
        # Update existing
        if "conditions" in data:
            medical_history.conditions = data["conditions"]
        if "limitations" in data:
            medical_history.limitations = data["limitations"]
        if "medications" in data:
            medical_history.medications = data["medications"]
        if "notes" in data:
            medical_history.notes = data["notes"]
    else:
        # Create new
        medical_history = MedicalHistory(
            user_id=user_id,
            conditions=data.get("conditions"),
            limitations=data.get("limitations"),
            medications=data.get("medications"),
            notes=data.get("notes")
        )
        db.add(medical_history)
    
    db.commit()
    db.refresh(medical_history)
    return medical_history


# Exercise conflict mappings with severity levels
# "block" = exercise should be completely avoided
# "warning" = exercise needs caution/modification
EXERCISE_CONFLICTS = {
    # Musculoskeletal injuries (mostly warnings - can be modified)
    "knee injury": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "burpees"]},
    "knee pain": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "burpees"]},
    "knee problems": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps"]},
    "back injury": {"severity": "block", "exercises": ["deadlifts", "squats", "bent-over rows", "overhead press", "heavy lifting", "good mornings", "back extensions"]},
    "back pain": {"severity": "warning", "exercises": ["deadlifts", "squats", "bent-over rows", "overhead press", "heavy lifting", "good mornings"]},
    "lower back pain": {"severity": "warning", "exercises": ["deadlifts", "squats", "bent-over rows", "heavy lifting", "good mornings"]},
    "shoulder injury": {"severity": "block", "exercises": ["overhead press", "lateral raises", "upright rows", "pull-ups", "shoulder press", "dips", "handstands"]},
    "shoulder pain": {"severity": "warning", "exercises": ["overhead press", "lateral raises", "upright rows", "pull-ups", "shoulder press", "dips"]},
    "rotator cuff": {"severity": "block", "exercises": ["overhead press", "lateral raises", "upright rows", "pull-ups", "shoulder press", "dips"]},
    "wrist injury": {"severity": "warning", "exercises": ["push-ups", "planks", "handstands", "wrist curls", "dips", "burpees"]},
    "wrist pain": {"severity": "warning", "exercises": ["push-ups", "planks", "handstands", "wrist curls", "dips"]},
    "carpal tunnel": {"severity": "warning", "exercises": ["push-ups", "planks", "handstands", "wrist curls", "dips"]},
    "ankle injury": {"severity": "warning", "exercises": ["running", "jumping", "squats", "lunges", "box jumps", "burpees", "plyometrics"]},
    "ankle pain": {"severity": "warning", "exercises": ["running", "jumping", "squats", "lunges", "box jumps", "burpees"]},
    "neck injury": {"severity": "block", "exercises": ["overhead press", "deadlifts", "heavy lifting", "neck bridges", "bridges", "headstands"]},
    "neck pain": {"severity": "warning", "exercises": ["overhead press", "deadlifts", "heavy lifting", "neck bridges", "bridges"]},
    
    # Cardiovascular conditions (mostly blocks - high risk)
    "heart condition": {"severity": "block", "exercises": ["high intensity", "hiit", "sprinting", "heavy lifting", "max effort"]},
    "heart disease": {"severity": "block", "exercises": ["high intensity", "hiit", "sprinting", "heavy lifting", "max effort", "circuit training"]},
    "hypertension": {"severity": "warning", "exercises": ["heavy lifting", "max effort", "high intensity", "sprinting"]},
    "high blood pressure": {"severity": "warning", "exercises": ["heavy lifting", "max effort", "high intensity", "sprinting"]},
    "arrhythmia": {"severity": "block", "exercises": ["high intensity", "hiit", "sprinting", "heavy lifting", "max effort"]},
    
    # Metabolic conditions
    "diabetes": {"severity": "warning", "exercises": []},  # No specific exercise restrictions, but need monitoring
    "type 1 diabetes": {"severity": "warning", "exercises": []},
    "type 2 diabetes": {"severity": "warning", "exercises": []},
    
    # Bone/joint conditions
    "osteoporosis": {"severity": "block", "exercises": ["heavy lifting", "high impact", "jumping", "running", "box jumps", "burpees"]},
    "arthritis": {"severity": "warning", "exercises": ["high impact", "jumping", "running", "heavy lifting"]},
    "rheumatoid arthritis": {"severity": "warning", "exercises": ["high impact", "jumping", "running", "heavy lifting"]},
    "osteoarthritis": {"severity": "warning", "exercises": ["high impact", "jumping", "running", "heavy lifting"]},
    
    # Respiratory conditions
    "asthma": {"severity": "warning", "exercises": ["high intensity", "sprinting", "endurance running", "hiit"]},
    "copd": {"severity": "block", "exercises": ["high intensity", "sprinting", "endurance running", "hiit", "circuit training"]},
    
    # Pregnancy (special consideration)
    "pregnant": {"severity": "warning", "exercises": ["heavy lifting", "high impact", "jumping", "lying on back", "abdominal crunches"]},
    "pregnancy": {"severity": "warning", "exercises": ["heavy lifting", "high impact", "jumping", "lying on back", "abdominal crunches"]},
    
    # Hernia
    "hernia": {"severity": "block", "exercises": ["heavy lifting", "squats", "deadlifts", "abdominal crunches", "leg press"]},
    "inguinal hernia": {"severity": "block", "exercises": ["heavy lifting", "squats", "deadlifts", "abdominal crunches", "leg press"]},
}


def normalize_condition(condition: str) -> str:
    """Normalize condition string for matching"""
    return condition.lower().strip()

def find_matching_condition_key(normalized_condition: str) -> Optional[str]:
    """
    Find matching condition key using improved fuzzy matching.
    Handles variations like "knee problems" matching "knee injury".
    """
    # Direct match
    if normalized_condition in EXERCISE_CONFLICTS:
        return normalized_condition
    
    # Check if any condition key is contained in the normalized condition
    # e.g., "knee problems" contains "knee injury" keywords
    for condition_key in EXERCISE_CONFLICTS.keys():
        # Split condition key into words
        key_words = condition_key.split()
        # Check if all key words appear in the condition
        if all(word in normalized_condition for word in key_words if len(word) > 2):
            return condition_key
    
    # Check if condition contains any condition key
    # e.g., "chronic knee pain" contains "knee pain"
    for condition_key in EXERCISE_CONFLICTS.keys():
        if condition_key in normalized_condition:
            return condition_key
    
    return None


def check_exercise_conflict(condition: str, exercise: str) -> Dict[str, any]:
    """
    Check if an exercise conflicts with a medical condition.
    Returns dict with conflict info including severity level.
    """
    normalized_condition = normalize_condition(condition)
    normalized_exercise = exercise.lower().strip()
    
    # Find matching condition key using improved matching
    condition_key = find_matching_condition_key(normalized_condition)
    
    if not condition_key:
        return {
            "has_conflict": False,
            "severity": None,
            "matched_condition": None
        }
    
    # Get conflict info for this condition
    conflict_info = EXERCISE_CONFLICTS[condition_key]
    conflicting_exercises = conflict_info["exercises"]
    severity = conflict_info["severity"]
    
    # Check if exercise matches any conflicting exercise
    for conflicting_exercise in conflicting_exercises:
        if conflicting_exercise in normalized_exercise:
            return {
                "has_conflict": True,
                "severity": severity,
                "matched_condition": condition_key
            }
    
    return {
        "has_conflict": False,
        "severity": None,
        "matched_condition": None
    }


def get_conflicting_exercises(conditions: str) -> Dict[str, List[str]]:
    """
    Get list of exercises that conflict with given conditions, grouped by severity.
    Returns a dict with 'block' and 'warning' lists.
    """
    if not conditions:
        return {"block": [], "warning": []}
    
    blocked_exercises = set()
    warning_exercises = set()
    condition_list = [c.strip() for c in conditions.split(",") if c.strip()]
    
    for condition in condition_list:
        normalized_condition = normalize_condition(condition)
        condition_key = find_matching_condition_key(normalized_condition)
        
        if condition_key:
            conflict_info = EXERCISE_CONFLICTS[condition_key]
            exercises = conflict_info["exercises"]
            severity = conflict_info["severity"]
            
            if severity == "block":
                blocked_exercises.update(exercises)
            elif severity == "warning":
                warning_exercises.update(exercises)
    
    return {
        "block": list(blocked_exercises),
        "warning": list(warning_exercises)
    }


def check_user_exercise_conflicts(user_id: int, exercise: str, db: Session) -> Dict:
    """
    Check if an exercise conflicts with user's medical history.
    Returns a dict with conflict information including severity.
    """
    medical_history = get_medical_history(user_id, db)
    
    if not medical_history or not medical_history.conditions:
        return {
            "has_conflict": False,
            "severity": None,
            "conflicting_conditions": [],
            "message": None
        }
    
    conflicting_conditions = []
    highest_severity = None  # "block" takes precedence over "warning"
    condition_list = [c.strip() for c in medical_history.conditions.split(",") if c.strip()]
    
    for condition in condition_list:
        conflict_result = check_exercise_conflict(condition, exercise)
        if conflict_result["has_conflict"]:
            conflicting_conditions.append(condition)
            severity = conflict_result["severity"]
            
            # Track highest severity (block > warning)
            if severity == "block":
                highest_severity = "block"
            elif severity == "warning" and highest_severity != "block":
                highest_severity = "warning"
    
    if conflicting_conditions:
        # Build appropriate message based on severity
        if highest_severity == "block":
            message = f"BLOCKED: {exercise} should be avoided due to your conditions: {', '.join(conflicting_conditions)}. Please consult your healthcare provider."
        else:
            message = f"Warning: {exercise} may conflict with your conditions: {', '.join(conflicting_conditions)}. Proceed with caution or consult your healthcare provider."
        
        return {
            "has_conflict": True,
            "severity": highest_severity,
            "conflicting_conditions": conflicting_conditions,
            "message": message
        }
    
    return {
        "has_conflict": False,
        "severity": None,
        "conflicting_conditions": [],
        "message": None
    }

