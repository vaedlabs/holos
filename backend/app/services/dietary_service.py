"""
Dietary Service - Handles dietary restriction conflict detection.

This module provides dietary restriction management and food conflict detection
functionality. It implements conflict detection between dietary restrictions and
food items to prevent recommending foods that violate user restrictions.

Key Features:
- Dietary restriction retrieval from user preferences
- Food conflict detection with severity levels
- Support for multiple restriction formats (JSON, comma-separated)
- Comprehensive conflict database (DIETARY_CONFLICTS)

Severity Levels:
- "block": Food should be completely avoided (strict restrictions)
- "warning": Food may need alternatives (flexible restrictions)

Restriction Types:
- Dietary preferences: vegan, vegetarian, pescatarian
- Religious: halal, kosher
- Allergies/intolerances: nut-free, shellfish-free, dairy-free, lactose-free
- Health-related: gluten-free

Usage:
- Used by Nutrition Agent to check meal recommendations
- Prevents recommending foods that violate user restrictions
- Provides warnings for foods that may conflict
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.user_preferences import UserPreferences
import json
import re


# Dietary conflict mappings
# This dictionary maps dietary restrictions to conflicting food items/ingredients.
# Used by check_dietary_conflicts() to determine if a food violates restrictions.
#
# Structure:
#   {
#       "restriction_name": {
#           "conflicting_items": List[str],  # Food items that conflict
#           "severity": str  # "block" or "warning"
#       }
#   }
#
# Severity Levels:
#   "block": Food should be completely avoided (strict restrictions)
#   "warning": Food may need alternatives (flexible restrictions)
#
# Conflict Detection:
#   - Restrictions are matched by name (case-insensitive)
#   - Food items are matched using word boundary regex
#   - Prevents false positives (e.g., "nut" in "peanut" but not "nutshell")
#
# Note:
#   - Used by Nutrition Agent to check meal recommendations
#   - Helps prevent recommending foods that violate user restrictions
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
    """
    Get dietary restrictions for a user.
    
    This function retrieves the dietary restrictions string from user preferences.
    Returns None if user has no preferences or no dietary restrictions set.
    
    Args:
        user_id: User ID to fetch dietary restrictions for
        db: Database session for querying
        
    Returns:
        Optional[str]: Dietary restrictions string if exists, None otherwise
        
    Note:
        - Returns raw string (may be JSON or comma-separated)
        - Use parse_dietary_restrictions() to parse into list
        - Used by check_dietary_conflicts() to check food recommendations
    """
    preferences = db.query(UserPreferences).filter(
        UserPreferences.user_id == user_id
    ).first()
    
    if preferences and preferences.dietary_restrictions:
        return preferences.dietary_restrictions
    return None


def parse_dietary_restrictions(restrictions_str: str) -> List[str]:
    """
    Parse dietary restrictions from string (can be JSON or comma-separated).
    
    This function parses dietary restrictions from various formats and returns
    a normalized list of restriction names. Supports both JSON arrays and
    comma-separated strings.
    
    Args:
        restrictions_str: Dietary restrictions string in JSON or comma-separated format
                         Examples:
                         - JSON: '["vegan", "gluten-free"]'
                         - Comma-separated: "vegan, gluten-free"
                         - Single: "vegan"
        
    Returns:
        List[str]: List of restriction names in lowercase, normalized
        
    Parsing Strategy:
        1. Try to parse as JSON first (handles JSON arrays and strings)
        2. If JSON parsing fails, parse as comma-separated string
        3. Normalize all restrictions to lowercase and strip whitespace
        
    Examples:
        parse_dietary_restrictions('["vegan", "gluten-free"]')
        -> ["vegan", "gluten-free"]
        
        parse_dietary_restrictions("vegan, gluten-free")
        -> ["vegan", "gluten-free"]
        
        parse_dietary_restrictions("vegan")
        -> ["vegan"]
        
    Note:
        - Returns empty list if restrictions_str is empty or None
        - Handles both JSON and comma-separated formats
        - Normalizes to lowercase for consistent matching
    """
    if not restrictions_str:
        return []
    
    restrictions = []
    
    # Try to parse as JSON first
    # Handles JSON arrays: ["vegan", "gluten-free"]
    # Handles JSON strings: "vegan"
    try:
        parsed = json.loads(restrictions_str)
        if isinstance(parsed, list):
            # JSON array - extract all items
            restrictions = [r.lower().strip() for r in parsed]
        elif isinstance(parsed, str):
            # JSON string - single restriction
            restrictions = [parsed.lower().strip()]
    except (json.JSONDecodeError, TypeError):
        # Not JSON, try comma-separated format
        # Handles: "vegan, gluten-free, nut-free"
        restrictions = [r.lower().strip() for r in restrictions_str.split(",") if r.strip()]
    
    return restrictions


def check_dietary_conflicts(user_id: int, food_description: str, db: Session) -> Dict:
    """
    Check if food description conflicts with user's dietary restrictions.
    
    This function checks if a food description (from image analysis or text)
    conflicts with any of the user's dietary restrictions. It provides
    comprehensive conflict information including severity and conflicting items.
    
    CRITICAL: This function is used by Nutrition Agent to prevent recommending
    foods that violate user restrictions. Agents MUST check conflicts before
    recommending meals.
    
    Args:
        user_id: User ID to check dietary restrictions for
        food_description: Description of food/meal (from image analysis or text)
                         Examples: "grilled chicken salad", "pasta with cheese"
        db: Database session for querying user preferences
        
    Returns:
        Dict: Conflict information:
            {
                "has_conflict": bool,  # True if conflict exists
                "severity": str or None,  # "block" or "warning" or None
                "message": str or None,  # Human-readable conflict message
                "conflicting_restrictions": List[str],  # List of conflicting restrictions
                "conflicting_items": List[str]  # List of conflicting food items
            }
            
    Conflict Detection:
        1. Fetch user's dietary restrictions
        2. Parse restrictions (JSON or comma-separated)
        3. Normalize food description to lowercase
        4. Check each restriction against food description
        5. Use word boundary regex to match conflicting items
        6. Collect all conflicts and determine highest severity
        7. Build comprehensive conflict information
        
    Severity Precedence:
        - "block" takes precedence over "warning"
        - If any restriction blocks food, severity is "block"
        - If all conflicts are warnings, severity is "warning"
        
    Word Boundary Matching:
        - Uses regex word boundaries (\b) to avoid false positives
        - Example: "nut" matches "peanut" but not "nutshell"
        - Prevents matching partial words incorrectly
        
    Message Format:
        - BLOCKED: For strict restrictions (severity="block")
        - Warning: For flexible restrictions (severity="warning")
        - Includes conflicting items and restrictions
        
    Example:
        check_dietary_conflicts(123, "grilled chicken salad", db)
        -> {
            "has_conflict": True,
            "severity": "block",
            "message": "BLOCKED: This meal contains chicken which conflicts...",
            "conflicting_restrictions": ["vegan"],
            "conflicting_items": ["chicken"]
        }
        
    Note:
        - Returns conflict info even if no conflict (has_conflict=False)
        - Used by Nutrition Agent before recommending meals
        - This is a safety feature to respect user restrictions
        - Word boundary matching prevents false positives
    """
    # Get user's dietary restrictions from preferences
    restrictions_str = get_user_dietary_restrictions(user_id, db)
    if not restrictions_str:
        # No restrictions - no conflicts
        return {
            "has_conflict": False,
            "severity": None,
            "message": None,
            "conflicting_restrictions": []
        }
    
    # Parse restrictions into list
    # Handles both JSON and comma-separated formats
    user_restrictions = parse_dietary_restrictions(restrictions_str)
    if not user_restrictions:
        # Empty restrictions list - no conflicts
        return {
            "has_conflict": False,
            "severity": None,
            "message": None,
            "conflicting_restrictions": []
        }
    
    # Normalize food description to lowercase for matching
    # Case-insensitive matching for consistent results
    food_lower = food_description.lower()
    
    # Check each restriction for conflicts
    conflicts = []  # List of conflict details
    max_severity = None  # Highest severity found (block > warning)
    
    for restriction in user_restrictions:
        restriction_lower = restriction.lower()
        
        # Check if this restriction has conflict mappings
        # Only check restrictions that are in DIETARY_CONFLICTS
        if restriction_lower in DIETARY_CONFLICTS:
            conflict_info = DIETARY_CONFLICTS[restriction_lower]
            conflicting_items = conflict_info["conflicting_items"]
            severity = conflict_info["severity"]
            
            # Check if any conflicting item appears in food description
            # Uses word boundary regex to avoid false positives
            for item in conflicting_items:
                # Use word boundary matching to avoid false positives
                # Example: "nut" matches "peanut" but not "nutshell"
                pattern = r'\b' + re.escape(item.lower()) + r'\b'
                if re.search(pattern, food_lower):
                    # Conflict found - add to conflicts list
                    conflicts.append({
                        "restriction": restriction,  # Original restriction name
                        "conflicting_item": item,  # Conflicting food item
                        "severity": severity  # Severity level
                    })
                    
                    # Track maximum severity (block > warning)
                    # Block severity takes precedence over warning
                    if severity == "block" or max_severity is None:
                        max_severity = severity
                    break  # Found conflict for this restriction, move to next
    
    # If no conflicts found, return no conflict
    if not conflicts:
        return {
            "has_conflict": False,
            "severity": None,
            "message": None,
            "conflicting_restrictions": []
        }
    
    # Build conflict information
    # Extract unique restrictions and items from conflicts
    conflicting_restrictions = list(set([c["restriction"] for c in conflicts]))
    conflicting_items = list(set([c["conflicting_item"] for c in conflicts]))
    
    # Build warning message based on severity
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

