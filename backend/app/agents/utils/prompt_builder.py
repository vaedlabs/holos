"""
Shared prompt builder for all agents.

Replaces the three separate copies of _build_enhanced_system_prompt() that existed
in BaseAgent, NutritionAgent, and MentalFitnessAgent. All four agents call this
function so the profile context block, identity block, and directive blocks are
generated from a single source of truth.
"""

from typing import Dict, Optional, List


def build_enhanced_prompt(
    base_prompt: str,
    shared_context: Optional[Dict],
    conversation_message_count: int = 0,
) -> str:
    """
    Build the enhanced system prompt by appending user profile context and
    session-state directives to the agent's base role prompt.

    Args:
        base_prompt: The agent-specific role prompt (nutrition, fitness, etc.)
        shared_context: Dict from ContextManager with keys:
            "username", "medical_history", "preferences"
        conversation_message_count: Number of existing conversation messages
            for this user. Used to decide whether to inject a greeting directive.

    Returns:
        Complete system prompt with profile context and directives appended.
    """
    if not shared_context:
        return base_prompt + "\n\nUse get_medical_history and get_user_preferences tools to fetch user information when needed."

    context_parts = []
    username = shared_context.get("username")

    # --- Identity block ---
    if username:
        context_parts.append(
            f"## User Profile\n"
            f"Name: {username}\n"
            f"Address this person by name when it feels natural. Do not repeat it on every message."
        )

    # --- Medical history block ---
    medical_history = shared_context.get("medical_history")
    if medical_history:
        medical_parts = []
        if medical_history.get("conditions"):
            medical_parts.append(f"Medical Conditions: {medical_history['conditions']}")
        if medical_history.get("limitations"):
            medical_parts.append(f"Physical Limitations: {medical_history['limitations']}")
        if medical_history.get("medications"):
            medical_parts.append(f"Medications: {medical_history['medications']}")
        if medical_history.get("notes"):
            medical_parts.append(f"Medical Notes: {medical_history['notes']}")
        if medical_parts:
            context_parts.append("## Medical History\n" + "\n".join(medical_parts))

    # --- Preferences block ---
    preferences = shared_context.get("preferences")
    if preferences:
        pref_parts = []
        if preferences.get("goals"):
            pref_parts.append(f"Fitness Goals: {preferences['goals']}")
        if preferences.get("dietary_restrictions"):
            pref_parts.append(f"Dietary Restrictions: {preferences['dietary_restrictions']}")
        if preferences.get("exercise_types"):
            pref_parts.append(f"Preferred Exercise Types: {preferences['exercise_types']}")
        if preferences.get("activity_level"):
            pref_parts.append(f"Activity Level: {preferences['activity_level']}")
        if preferences.get("lifestyle"):
            pref_parts.append(f"Lifestyle: {preferences['lifestyle']}")
        if preferences.get("age"):
            pref_parts.append(f"Age: {preferences['age']}")
        if preferences.get("gender"):
            pref_parts.append(f"Gender: {preferences['gender']}")
        if preferences.get("location"):
            pref_parts.append(f"Location: {preferences['location']}")
        if pref_parts:
            context_parts.append("## User Preferences\n" + "\n".join(pref_parts))

    if not context_parts:
        return base_prompt + "\n\n**Note**: No user context available. Use get_medical_history and get_user_preferences tools to fetch user information when needed."

    context_section = "\n\n".join(context_parts)
    enhanced = base_prompt + f"\n\n## User Context\n{context_section}"

    # --- Tool-use directive ---
    enhanced += (
        "\n\n**IMPORTANT**: You have full user context above. "
        "Only call tools (get_medical_history, get_user_preferences) if you need information "
        "NOT provided above or if the context seems outdated. "
        "For real-time information (web search) or actions (creating logs), use tools as needed."
    )

    # --- Greeting directive based on conversation state ---
    if conversation_message_count > 0:
        enhanced += (
            "\n\nSESSION STATE: This is a continuing conversation. "
            "Do NOT give an introductory greeting. Respond directly to the user's message."
        )
    # If conversation_message_count == 0 this is the first message — no directive, let the agent greet naturally.

    return enhanced
