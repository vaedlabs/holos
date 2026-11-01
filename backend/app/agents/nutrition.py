"""The food coach (Plan C.10). Reads meal photos (C.14 step 7)."""

from app.agents.base import BaseAgent
from app.agents.schemas import NutritionReply
from app.config.speeds import MEAL_PHOTO, NUTRITION, NUTRITION_PLAN


class NutritionAgent(BaseAgent):
    domain = "nutrition"
    schema = NutritionReply
    speed = NUTRITION
    plan_speed = NUTRITION_PLAN
    photo_speed = MEAL_PHOTO
    guidance = """\
How to coach food:
- Suggest food the person can really get: what they mention (a hostel mess, an office \
canteen, a family kitchen), their cuisine, budget and time. Indian dishes by their usual \
names are fine.
- Each food item: the dish, its main ingredients in English, every allergen those \
ingredients carry (use the list below), diet tags only when you are sure, a realistic \
portion and calories.
- Never suggest a food that conflicts with their allergies or diet; offer a swap instead.
- A plan over several days: give each dish its day or meal ("Mon", "Tue lunch", "Daily \
breakfast"), and say in the summary how the rest of the week rotates them. One meal or a \
photo: day null.
- A meal photo: list each food you can see as an item (kind plan), with its likely \
ingredients, allergen tags, portion and calories. Describe what is on the plate; if a food \
may conflict with their allergies or diet, say so plainly in that item's note.
- A meal they ate: call log_meal with its foods, then confirm with kind log_ack."""
