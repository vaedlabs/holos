"""
Medical Service - Handles medical history and exercise conflict detection.

This module provides medical history management and exercise safety checking
functionality. It implements conflict detection between medical conditions and
exercises to prevent unsafe recommendations.

CRITICAL SAFETY CONSIDERATIONS:
- This service helps prevent recommending unsafe exercises
- Conflict detection is based on common medical knowledge
- NOT a replacement for professional medical advice
- Agents MUST check conflicts before recommending exercises
- Severity levels help agents understand risk levels

Key Features:
- Medical history retrieval and updates
- Exercise conflict detection with severity levels
- Fuzzy condition matching for flexible detection
- Comprehensive conflict database (EXERCISE_CONFLICTS)

Severity Levels:
- "block": Exercise should be completely avoided (high risk)
- "warning": Exercise needs caution/modification (moderate risk)
"""

from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from app.models.medical_history import MedicalHistory
from app.models.user import User


def get_medical_history(user_id: int, db: Session) -> Optional[MedicalHistory]:
    """
    Get medical history for a user.
    
    This function retrieves the medical history record for a specific user.
    Returns None if the user has no medical history on file.
    
    Args:
        user_id: User ID to fetch medical history for
        db: Database session for querying
        
    Returns:
        Optional[MedicalHistory]: Medical history record if exists, None otherwise
        
    Note:
        - Returns None if user has no medical history
        - Used by agents to check medical restrictions
        - Cached by ContextManager to avoid redundant queries
    """
    return db.query(MedicalHistory).filter(MedicalHistory.user_id == user_id).first()


def update_medical_history(user_id: int, data: dict, db: Session) -> MedicalHistory:
    """
    Create or update medical history for a user.
    
    This function creates a new medical history record or updates an existing one.
    Supports partial updates (only updates fields provided in data dictionary).
    
    Args:
        user_id: User ID to create/update medical history for
        data: Dictionary with medical history fields:
              - conditions: Medical conditions (optional)
              - limitations: Physical limitations (optional)
              - medications: Current medications (optional)
              - notes: Additional medical notes (optional)
        db: Database session for persistence
        
    Returns:
        MedicalHistory: Created or updated medical history record
        
    Update Logic:
        - If medical history exists: Updates only provided fields (partial update)
        - If medical history doesn't exist: Creates new record with provided fields
        
    Note:
        - Supports partial updates (only updates fields in data)
        - Commits changes to database
        - Should invalidate context cache after update (call context_manager.invalidate_cache)
    """
    medical_history = get_medical_history(user_id, db)
    
    if medical_history:
        # Update existing medical history record
        # Only update fields that are provided (partial update)
        if "conditions" in data:
            medical_history.conditions = data["conditions"]
        if "limitations" in data:
            medical_history.limitations = data["limitations"]
        if "medications" in data:
            medical_history.medications = data["medications"]
        if "notes" in data:
            medical_history.notes = data["notes"]
    else:
        # Create new medical history record
        medical_history = MedicalHistory(
            user_id=user_id,
            conditions=data.get("conditions"),
            limitations=data.get("limitations"),
            medications=data.get("medications"),
            notes=data.get("notes")
        )
        db.add(medical_history)
    
    # Persist changes to database
    db.commit()
    db.refresh(medical_history)
    return medical_history


# Exercise conflict mappings with severity levels
# This dictionary maps medical conditions to exercises that may conflict with them.
# Used by check_exercise_conflict() to determine if an exercise is safe for a condition.
#
# Severity Levels:
#   "block": Exercise should be completely avoided (high risk of injury/exacerbation)
#   "warning": Exercise needs caution/modification (moderate risk, may be safe with modifications)
#
# Conflict Detection:
#   - Conditions are matched using fuzzy matching (find_matching_condition_key)
#   - Exercises are matched by substring (e.g., "squats" matches "bodyweight squats")
#   - Multiple conditions can conflict with same exercise
#   - Highest severity takes precedence (block > warning)
#
# Safety Note:
#   - This is a safety feature, NOT medical diagnosis
#   - Based on common medical knowledge and exercise contraindications
#   - Users should consult healthcare providers for medical advice
#   - Agents use this to avoid recommending unsafe exercises
EXERCISE_CONFLICTS = {
    # Musculoskeletal injuries (mostly warnings - can be modified)
    "knee injury": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "burpees", "deadlifts", "dead lifts"]},
    "knee pain": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "burpees", "deadlifts", "dead lifts"]},
    "knee problems": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "deadlifts", "dead lifts"]},
    "acl": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "burpees", "deadlifts", "dead lifts", "heavy lifting"]},
    "acl injury": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "burpees", "deadlifts", "dead lifts", "heavy lifting"]},
    "acl tear": {"severity": "warning", "exercises": ["squats", "lunges", "running", "jumping", "leg press", "step-ups", "box jumps", "burpees", "deadlifts", "dead lifts", "heavy lifting"]},
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
    "heart condition": {"severity": "block", "exercises": ["high intensity", "hiit", "sprinting", "heavy lifting", "max effort", "triathlon", "marathon", "endurance events", "endurance running", "long distance running", "ultramarathon", "ironman", "half ironman"]},
    "heart disease": {"severity": "block", "exercises": ["high intensity", "hiit", "sprinting", "heavy lifting", "max effort", "circuit training", "triathlon", "marathon", "endurance events", "endurance running", "long distance running", "ultramarathon", "ironman", "half ironman"]},
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
    """
    Normalize condition string for matching.
    
    This function normalizes condition strings to lowercase and removes
    whitespace for consistent matching against EXERCISE_CONFLICTS keys.
    
    Args:
        condition: Condition string to normalize
        
    Returns:
        str: Normalized condition (lowercase, stripped)
        
    Example:
        "Knee Injury" -> "knee injury"
        "  Back Pain  " -> "back pain"
    """
    return condition.lower().strip()

def find_matching_condition_key(normalized_condition: str) -> Optional[str]:
    """
    Find matching condition key using improved fuzzy matching.
    
    This function finds the best matching condition key from EXERCISE_CONFLICTS
    using fuzzy matching. Handles variations and partial matches.
    
    Args:
        normalized_condition: Normalized condition string (lowercase, stripped)
        
    Returns:
        Optional[str]: Matching condition key from EXERCISE_CONFLICTS, or None
        
    Matching Strategy (in priority order):
        1. Direct match: Exact match in EXERCISE_CONFLICTS
        2. Word-based match: All words from condition key appear in condition
           (e.g., "knee problems" matches "knee injury" because both contain "knee")
        3. Substring match: Condition key appears as substring in condition
           (e.g., "chronic knee pain" contains "knee pain")
    
    Examples:
        "knee injury" -> "knee injury" (direct match)
        "knee problems" -> "knee injury" (word-based match)
        "chronic knee pain" -> "knee pain" (substring match)
        "unknown condition" -> None (no match)
        
    Note:
        - Fuzzy matching handles user input variations
        - Returns None if no match found
        - Used by check_exercise_conflict() to find conflicts
    """
    # Direct match: Check if condition exactly matches a key
    if normalized_condition in EXERCISE_CONFLICTS:
        return normalized_condition
    
    # Word-based match: Check if all words from condition key appear in condition
    # Handles variations like "knee problems" matching "knee injury"
    # Only checks words longer than 2 characters (avoids matching common words)
    for condition_key in EXERCISE_CONFLICTS.keys():
        # Split condition key into words
        key_words = condition_key.split()
        # Check if all key words appear in the condition
        if all(word in normalized_condition for word in key_words if len(word) > 2):
            return condition_key
    
    # Substring match: Check if condition contains any condition key
    # Handles cases like "chronic knee pain" containing "knee pain"
    for condition_key in EXERCISE_CONFLICTS.keys():
        if condition_key in normalized_condition:
            return condition_key
    
    return None


def check_exercise_conflict(condition: str, exercise: str) -> Dict[str, any]:
    """
    Check if an exercise conflicts with a medical condition.
    
    This function determines if a specific exercise conflicts with a medical
    condition. Returns conflict information including severity level.
    
    Args:
        condition: Medical condition string (e.g., "knee injury", "heart disease")
        exercise: Exercise name string (e.g., "squats", "running", "deadlifts")
        
    Returns:
        Dict[str, any]: Conflict information:
            {
                "has_conflict": bool,  # True if conflict exists
                "severity": str or None,  # "block" or "warning" or None
                "matched_condition": str or None  # Matched condition key
            }
            
    Conflict Detection:
        1. Normalize condition and exercise strings
        2. Find matching condition key using fuzzy matching
        3. Get conflicting exercises for matched condition
        4. Check if exercise matches any conflicting exercise (substring match)
        5. Return conflict info with severity
        
    Severity Levels:
        - "block": Exercise should be completely avoided (high risk)
        - "warning": Exercise needs caution/modification (moderate risk)
        - None: No conflict detected
        
    Exercise Matching:
        - Uses substring matching (e.g., "squats" matches "bodyweight squats")
        - Case-insensitive matching
        - Handles exercise name variations
        
    Example:
        check_exercise_conflict("knee injury", "squats")
        -> {"has_conflict": True, "severity": "warning", "matched_condition": "knee injury"}
        
        check_exercise_conflict("heart disease", "running")
        -> {"has_conflict": False, "severity": None, "matched_condition": None}
        
    Note:
        - Returns conflict info even if no conflict (has_conflict=False)
        - Used by check_user_exercise_conflicts() for user-specific checking
        - Agents use this to avoid recommending unsafe exercises
    """
    # Normalize inputs for consistent matching
    normalized_condition = normalize_condition(condition)
    normalized_exercise = exercise.lower().strip()
    
    # Find matching condition key using improved fuzzy matching
    # Handles variations in condition naming
    condition_key = find_matching_condition_key(normalized_condition)
    
    # If no matching condition found, no conflict
    if not condition_key:
        return {
            "has_conflict": False,
            "severity": None,
            "matched_condition": None
        }
    
    # Get conflict info for this condition
    # Contains list of conflicting exercises and severity level
    conflict_info = EXERCISE_CONFLICTS[condition_key]
    conflicting_exercises = conflict_info["exercises"]
    severity = conflict_info["severity"]
    
    # Check if exercise matches any conflicting exercise
    # Uses substring matching (e.g., "squats" matches "bodyweight squats")
    for conflicting_exercise in conflicting_exercises:
        if conflicting_exercise in normalized_exercise:
            return {
                "has_conflict": True,
                "severity": severity,  # "block" or "warning"
                "matched_condition": condition_key  # Matched condition key
            }
    
    # No conflict found
    return {
        "has_conflict": False,
        "severity": None,
        "matched_condition": None
    }


def get_conflicting_exercises(conditions: str) -> Dict[str, List[str]]:
    """
    Get list of exercises that conflict with given conditions, grouped by severity.
    
    This function returns all exercises that conflict with the given conditions,
    grouped by severity level. Useful for getting a comprehensive list of
    exercises to avoid or modify.
    
    Args:
        conditions: Comma-separated list of medical conditions
                   (e.g., "knee injury, back pain")
        
    Returns:
        Dict[str, List[str]]: Dictionary with conflicting exercises:
            {
                "block": List[str],  # Exercises to completely avoid
                "warning": List[str]  # Exercises needing caution/modification
            }
            
    Processing:
        1. Split conditions by comma
        2. For each condition, find matching condition key
        3. Collect conflicting exercises grouped by severity
        4. Use sets to avoid duplicates
        
    Example:
        get_conflicting_exercises("knee injury, back pain")
        -> {
            "block": ["deadlifts", "squats", "bent-over rows", ...],
            "warning": ["squats", "lunges", "running", ...]
        }
        
    Note:
        - Returns empty lists if no conditions provided
        - Uses sets internally to avoid duplicate exercises
        - Exercises may appear in both lists if multiple conditions conflict
        - Used for comprehensive exercise restriction lists
    """
    if not conditions:
        return {"block": [], "warning": []}
    
    # Use sets to avoid duplicate exercises
    blocked_exercises = set()  # Exercises to completely avoid
    warning_exercises = set()  # Exercises needing caution/modification
    
    # Split conditions by comma and process each
    condition_list = [c.strip() for c in conditions.split(",") if c.strip()]
    
    for condition in condition_list:
        normalized_condition = normalize_condition(condition)
        condition_key = find_matching_condition_key(normalized_condition)
        
        if condition_key:
            # Get conflict info for matched condition
            conflict_info = EXERCISE_CONFLICTS[condition_key]
            exercises = conflict_info["exercises"]
            severity = conflict_info["severity"]
            
            # Add exercises to appropriate set based on severity
            if severity == "block":
                blocked_exercises.update(exercises)
            elif severity == "warning":
                warning_exercises.update(exercises)
    
    # Convert sets to lists for return
    return {
        "block": list(blocked_exercises),
        "warning": list(warning_exercises)
    }


def check_user_exercise_conflicts(user_id: int, exercise: str, db: Session) -> Dict:
    """
    Check if an exercise conflicts with user's medical history.
    
    This function checks if an exercise conflicts with any of the user's
    medical conditions. It provides comprehensive conflict information including
    severity, conflicting conditions, and reasoning context for agents.
    
    CRITICAL: This function is used by Physical Fitness Agent to prevent
    recommending unsafe exercises. Agents MUST check conflicts before
    recommending exercises.
    
    Args:
        user_id: User ID to check medical history for
        exercise: Exercise name to check for conflicts (e.g., "squats", "deadlifts")
        db: Database session for querying medical history
        
    Returns:
        Dict: Conflict information:
            {
                "has_conflict": bool,  # True if conflict exists
                "severity": str or None,  # "block" or "warning" or None
                "conflicting_conditions": List[str],  # List of conflicting conditions
                "message": str or None,  # Human-readable conflict message
                "reasoning_context": Dict or None  # Detailed context for agent reasoning
            }
            
    Conflict Detection:
        1. Fetch user's medical history
        2. Split conditions by comma
        3. Check each condition against exercise
        4. Collect all conflicting conditions
        5. Determine highest severity (block > warning)
        6. Build comprehensive conflict information
        
    Severity Precedence:
        - "block" takes precedence over "warning"
        - If any condition blocks exercise, severity is "block"
        - If all conflicts are warnings, severity is "warning"
        
    Reasoning Context:
        Provides detailed information for agents to reason about conflicts:
        - Conflicting conditions list
        - Severity level
        - Matched condition keys
        - Medical notes (if available)
        - Physical limitations (if available)
        
    Message Format:
        - BLOCKED: For high-risk conflicts (severity="block")
        - Warning: For moderate-risk conflicts (severity="warning")
        - Includes condition names and severity indicators
        - Provides guidance for agent reasoning
        
    Example:
        check_user_exercise_conflicts(123, "squats", db)
        -> {
            "has_conflict": True,
            "severity": "warning",
            "conflicting_conditions": ["knee injury"],
            "message": "Warning: squats may need modification...",
            "reasoning_context": {...}
        }
        
    Note:
        - Returns conflict info even if no conflict (has_conflict=False)
        - Used by Physical Fitness Agent before recommending exercises
        - Agents use reasoning_context to provide informed recommendations
        - This is a safety feature, NOT medical diagnosis
    """
    # Fetch user's medical history
    medical_history = get_medical_history(user_id, db)
    
    # If no medical history or no conditions, no conflicts
    if not medical_history or not medical_history.conditions:
        return {
            "has_conflict": False,
            "severity": None,
            "conflicting_conditions": [],
            "message": None,
            "reasoning_context": None
        }
    
    # Track conflicting conditions and severity
    conflicting_conditions = []  # List of conditions that conflict
    highest_severity = None  # "block" takes precedence over "warning"
    condition_list = [c.strip() for c in medical_history.conditions.split(",") if c.strip()]
    matched_conditions_info = []  # Store detailed info for agent reasoning
    
    # Check each condition for conflicts
    for condition in condition_list:
        conflict_result = check_exercise_conflict(condition, exercise)
        if conflict_result["has_conflict"]:
            # Conflict found - add to list
            conflicting_conditions.append(condition)
            severity = conflict_result["severity"]
            matched_condition_key = conflict_result.get("matched_condition")
            
            # Track highest severity (block > warning)
            # Block severity takes precedence over warning
            if severity == "block":
                highest_severity = "block"
            elif severity == "warning" and highest_severity != "block":
                highest_severity = "warning"
            
            # Store detailed info for agent reasoning
            # Helps agents understand why exercise conflicts
            matched_conditions_info.append({
                "condition": condition,  # Original condition string
                "matched_key": matched_condition_key,  # Matched key from EXERCISE_CONFLICTS
                "severity": severity  # Severity level for this condition
            })
    
    if conflicting_conditions:
        # Build context-rich message that allows agent reasoning
        # Message includes condition names and severity
        conditions_str = ', '.join(conflicting_conditions)
        
        # Create reasoning context for the agent
        # Provides detailed information for informed decision-making
        reasoning_context = {
            "conflicting_conditions": conflicting_conditions,  # List of conflicting conditions
            "severity": highest_severity,  # Highest severity level
            "matched_conditions_info": matched_conditions_info,  # Detailed match info
            "medical_notes": medical_history.notes if medical_history.notes else None,  # Additional medical notes
            "limitations": medical_history.limitations if medical_history.limitations else None  # Physical limitations
        }
        
        # Build informative message (not prescriptive - allows agent reasoning)
        # Include explicit severity indicators for frontend detection
        # Message guides agent on how to handle conflict
        if highest_severity == "block":
            message = f"BLOCKED: {exercise} conflicts with your conditions ({conditions_str}). Severity: HIGH RISK. Consider: condition severity, doctor's approval, modifications, and safer alternatives."
        else:
            message = f"Warning: {exercise} may need modification for your conditions ({conditions_str}). Severity: MODERATE. Consider: condition management, modifications, and gradual progression."
        
        return {
            "has_conflict": True,
            "severity": highest_severity,
            "conflicting_conditions": conflicting_conditions,
            "message": message,
            "reasoning_context": reasoning_context
        }
    
    # No conflicts found
    return {
        "has_conflict": False,
        "severity": None,
        "conflicting_conditions": [],
        "message": None,
        "reasoning_context": None
    }

