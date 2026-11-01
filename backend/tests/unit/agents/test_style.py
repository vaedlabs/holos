"""writing_style: what the coach is told about the person's language (Part D)."""

import pytest

from app.agents.style import writing_style

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(("text", "style"), [
    ("मुझे तनाव है, नींद नहीं आती", "hindi"),
    ("सुबह की walk से पहले चाय ठीक है?", "hindi"),
    ("neend nahi aati", "hinglish"),
    ("abhi mess me 2 roti khaya", "hinglish"),
    ("Bro summer tak abs chahiye 😭 Can you help me figure out workouts", "hinglish"),
    ("haan", "hinglish"),
    ("Could you do me a 10 min workout plan that won't make my back worse?", "english"),
    ("What do you do with my data? Give me a plan.", "english"),
    ("Can I have a koi fish recipe?", "english"),
    ("👍", "english"),
])
def test_writing_style(text, style):
    assert writing_style(text) == style


def test_devanagari_vowel_signs_count_as_letters():
    # Without the vowel signs the Hindi looks shorter than the one English word
    assert writing_style("आज कौन सी exercise करूँ?") == "hindi"
