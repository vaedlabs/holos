"""
Dietary Service - Handles dietary restriction conflict detection
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.user_preferences import UserPreferences
import json
import re


# Dietary conflict mappings
# Maps dietary restrictions to conflicting food items/ingredients
DIETARY_CONFLICTS = {
    "vegan": {
        "conflicting_items": [
            "meat", "beef", "pork", "chicken", "turkey", "lamb", "fish", "seafood", 
            "sausage", "bacon", "ham", "pepperoni", "salami", "prosciutto",
            "egg", "eggs", "dairy", "milk", "cheese", "butter", "cream", "yogurt",
            "honey", "gelatin", "whey", "casein", "lard", "animal", "poultry"
        ],
        "severity": "block"  # Vegan is strict - no animal products
    },
    "vegetarian": {
        "conflicting_items": [
            "meat", "beef", "pork", "chicken", "turkey", "lamb", "fish", "seafood",
            "sausage", "bacon", "ham", "pepperoni", "salami", "prosciutto",
            "gelatin", "lard", "animal", "poultry"
        ],
        "severity": "block"  # Vegetarian is strict - no meat/fish
    },
    "pescatarian": {
        "conflicting_items": [
            "meat", "beef", "pork", "chicken", "turkey", "lamb",
            "sausage", "bacon", "ham", "pepperoni", "salami", "prosciutto",
            "poultry", "lard"
        ],
        "severity": "block"  # Pescatarian allows fish but not other meat
    },
    "halal": {
        "conflicting_items": [
            "pork", "bacon", "ham", "pepperoni", "salami", "prosciutto",
            "alcohol", "wine", "beer", "liquor", "gelatin", "lard"
        ],
        "severity": "block"
    },
    "kosher": {
        "conflicting_items": [
            "pork", "bacon", "ham", "shellfish", "lobster", "shrimp", "crab",
            "mixing meat and dairy", "gelatin", "lard"
        ],
        "severity": "block"
    },
    "gluten-free": {
        "conflicting_items": [
            "wheat", "gluten", "bread", "pasta", "flour", "barley", "rye", "oats",
            "soy sauce", "beer", "malt"
        ],
        "severity": "warning"  # Can be modified with alternatives
    },
    "dairy-free": {
        "conflicting_items": [
            "dairy", "milk", "cheese", "butter", "cream", "yogurt", "whey", "casein",
            "lactose", "sour cream", "buttermilk"
        ],
        "severity": "block"
    },
    "lactose-free": {
        "conflicting_items": [
            "milk", "cheese", "butter", "cream", "yogurt", "lactose", "whey",
            "sour cream", "buttermilk"
        ],
        "severity": "warning"  # Can be modified with lactose-free alternatives
    },
    "nut-free": {
        "conflicting_items": [
            "peanut", "peanuts", "almond", "almonds", "walnut", "walnuts", "cashew", "cashews",
            "pistachio", "pistachios", "hazelnut", "hazelnuts", "pecan", "pecans",
            "nut", "nuts", "tree nut"
        ],
        "severity": "block"
    },
    "shellfish-free": {
        "conflicting_items": [
            "shellfish", "shrimp", "lobster", "crab", "crayfish", "mussel", "mussels",
            "oyster", "oysters", "clam", "clams", "scallop", "scallops"
        ],
        "severity": "block"
    }
}


def get_user_dietary_restrictions(user_id: int, db: Session) -> Optional[str]:
    """Get dietary restrictions for a user"""
    preferences = db.query(UserPreferences).filter(
        UserPreferences.user_id == user_id
    ).first()
    
    if preferences and preferences.dietary_restrictions:
        return preferences.dietary_restrictions
    return None


def parse_dietary_restrictions(restrictions_str: str) -> List[str]:
    """
    Parse dietary restrictions from string (can be JSON or comma-separated)
    Returns list of restriction names in lowercase
    """
    if not restrictions_str:
        return []
    
    restrictions = []
    
    # Try to parse as JSON first
    try:
        parsed = json.loads(restrictions_str)
        if isinstance(parsed, list):
            restrictions = [r.lower().strip() for r in parsed]
        elif isinstance(parsed, str):
            restrictions = [parsed.lower().strip()]
    except (json.JSONDecodeError, TypeError):
        # Not JSON, try comma-separated
        restrictions = [r.lower().strip() for r in restrictions_str.split(",") if r.strip()]
    
    return restrictions


def check_dietary_conflicts(user_id: int, food_description: str, db: Session) -> Dict:
    """
    Check if food description conflicts with user's dietary restrictions
    
    Args:
        user_id: User ID
        food_description: Description of food/meal (from image analysis or text)
        db: Database session
    
    Returns:
        Dict with:
            - has_conflict: bool
            - severity: "block" or "warning" or None
            - message: Warning message
            - conflicting_restrictions: List of restriction names that conflict
    """
    # Get user's dietary restrictions
    restrictions_str = get_user_dietary_restrictions(user_id, db)
    if not restrictions_str:
        return {
            "has_conflict": False,
            "severity": None,
            "message": None,
            "conflicting_restrictions": []
        }
    
    # Parse restrictions
    user_restrictions = parse_dietary_restrictions(restrictions_str)
    if not user_restrictions:
        return {
            "has_conflict": False,
            "severity": None,
            "message": None,
            "conflicting_restrictions": []
        }
    
    # Normalize food description to lowercase for matching
    food_lower = food_description.lower()
    
    # Check each restriction
    conflicts = []
    max_severity = None
    
    for restriction in user_restrictions:
        restriction_lower = restriction.lower()
        
        # Check if this restriction has conflict mappings
        if restriction_lower in DIETARY_CONFLICTS:
            conflict_info = DIETARY_CONFLICTS[restriction_lower]
            conflicting_items = conflict_info["conflicting_items"]
            severity = conflict_info["severity"]
            
            # Check if any conflicting item appears in food description
            for item in conflicting_items:
                # Use word boundary matching to avoid false positives
                pattern = r'\b' + re.escape(item.lower()) + r'\b'
                if re.search(pattern, food_lower):
                    conflicts.append({
                        "restriction": restriction,
                        "conflicting_item": item,
                        "severity": severity
                    })
                    
                    # Track maximum severity (block > warning)
                    if severity == "block" or max_severity is None:
                        max_severity = severity
                    break  # Found conflict for this restriction, move to next
    
    if not conflicts:
        return {
            "has_conflict": False,
            "severity": None,
            "message": None,
            "conflicting_restrictions": []
        }
    
    # Build warning message
    conflicting_restrictions = list(set([c["restriction"] for c in conflicts]))
    conflicting_items = list(set([c["conflicting_item"] for c in conflicts]))
    
    if max_severity == "block":
        message = f"BLOCKED: This meal contains {', '.join(conflicting_items)} which conflicts with your {', '.join(conflicting_restrictions)} dietary restriction(s)."
    else:
        message = f"Warning: This meal may contain {', '.join(conflicting_items)} which may conflict with your {', '.join(conflicting_restrictions)} dietary preference(s). Consider alternatives."
    
    return {
        "has_conflict": True,
        "severity": max_severity,
        "message": message,
        "conflicting_restrictions": conflicting_restrictions,
        "conflicting_items": conflicting_items
    }

