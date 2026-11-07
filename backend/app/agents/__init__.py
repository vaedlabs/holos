"""The coaches (Plan C.10): BaseAgent and the physical, nutrition and mental coaches.

    base.py       BaseAgent: one coach's call, tools, gate and retry
    physical.py   PhysicalAgent       nutrition.py   NutritionAgent
    mental.py     MentalAgent         prefix.py      the static prompt prefix
    schemas.py    replies, tool arguments, the stream contract
    tools/        get_recent_logs, web_search, log_workout, log_meal, log_practice

Routing, the chat request and writes are in app/orchestration/.
"""
