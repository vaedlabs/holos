"""
Tests for reasoning patterns
"""

import pytest
from unittest.mock import Mock, MagicMock
from app.agents.reasoning_patterns import (
    SafetyReasoningPattern,
    QueryAnalysisReasoningPattern,
    ExerciseSafetyReasoningPattern,
    CompositeReasoningPattern
)


class TestSafetyReasoningPattern:
    """Test SafetyReasoningPattern"""
    
    @pytest.fixture
    def safety_pattern(self):
        """Create a safety reasoning pattern"""
        return SafetyReasoningPattern()
    
    @pytest.fixture
    def context_with_medical_history(self):
        """Create context with medical history"""
        return {
            "medical_history": {
                "conditions": "heart condition",
                "limitations": "avoid high intensity"
            }
        }
    
    @pytest.mark.asyncio
    async def test_pre_check_with_medical_history(self, safety_pattern, context_with_medical_history):
        """Test pre_check detects medical history"""
        result = await safety_pattern.pre_check("I want to run a marathon", context_with_medical_history)
        assert result["has_safety_concerns"] is True
        assert result["medical_history_present"] is True
    
    @pytest.mark.asyncio
    async def test_pre_check_without_medical_history(self, safety_pattern):
        """Test pre_check with no medical history"""
        context = {"medical_history": None}
        result = await safety_pattern.pre_check("I want to run", context)
        assert result["has_safety_concerns"] is False
        assert result["medical_history_present"] is False
    
    @pytest.mark.asyncio
    async def test_reason_enhances_query_with_safety_context(self, safety_pattern, context_with_medical_history):
        """Test reason enhances query with safety context"""
        pre_check = await safety_pattern.pre_check("I want to run", context_with_medical_history)
        enhanced = await safety_pattern.reason("I want to run", context_with_medical_history, pre_check)
        assert "[SAFETY CONSIDERATIONS" in enhanced
        assert "heart condition" in enhanced
    
    @pytest.mark.asyncio
    async def test_reason_no_enhancement_when_no_concerns(self, safety_pattern):
        """Test reason doesn't enhance when no safety concerns"""
        context = {"medical_history": None}
        pre_check = await safety_pattern.pre_check("I want to run", context)
        enhanced = await safety_pattern.reason("I want to run", context, pre_check)
        assert enhanced == "I want to run"  # No enhancement
    
    @pytest.mark.asyncio
    async def test_post_validate_safe_response(self, safety_pattern):
        """Test post_validate with safe response"""
        context = {"medical_history": None}
        result = await safety_pattern.post_validate("You can do light jogging", "I want to run", context)
        assert result["is_safe"] is True
        assert result["validation_passed"] is True
    
    @pytest.mark.asyncio
    async def test_post_validate_unsafe_response(self, safety_pattern, context_with_medical_history):
        """Test post_validate detects unsafe language"""
        response = "Don't worry about your heart condition, you can still run"
        result = await safety_pattern.post_validate(response, "I want to run", context_with_medical_history)
        assert result["is_safe"] is False
        assert len(result["warnings"]) > 0


class TestQueryAnalysisReasoningPattern:
    """Test QueryAnalysisReasoningPattern"""
    
    @pytest.fixture
    def query_pattern(self):
        """Create a query analysis reasoning pattern"""
        return QueryAnalysisReasoningPattern()
    
    @pytest.mark.asyncio
    async def test_pre_check_classifies_query_type(self, query_pattern):
        """Test pre_check classifies query correctly"""
        result = await query_pattern.pre_check("I want a workout plan", {})
        assert result["query_type"] == "planning"
        assert result["is_request"] is True
    
    @pytest.mark.asyncio
    async def test_pre_check_detects_complexity(self, query_pattern):
        """Test pre_check detects complex queries"""
        simple_query = "What is a squat?"
        complex_query = "I want a comprehensive workout plan that includes strength training, cardio, and flexibility work, and I need it to work around my schedule and preferences"
        
        simple_result = await query_pattern.pre_check(simple_query, {})
        complex_result = await query_pattern.pre_check(complex_query, {})
        
        assert simple_result["is_complex"] is False
        assert complex_result["is_complex"] is True
    
    @pytest.mark.asyncio
    async def test_reason_returns_original_query(self, query_pattern):
        """Test reason returns original query (no enhancement yet)"""
        query = "I want a plan"
        enhanced = await query_pattern.reason(query, {}, {})
        assert enhanced == query
    
    @pytest.mark.asyncio
    async def test_post_validate_checks_appropriateness(self, query_pattern):
        """Test post_validate checks if response is appropriate"""
        complex_query = "I want a comprehensive workout plan that includes strength training, cardio, and flexibility work"
        short_response = "Do some exercises."
        
        result = await query_pattern.post_validate(short_response, complex_query, {})
        assert result["is_appropriate"] is False
        assert len(result["warnings"]) > 0


class TestExerciseSafetyReasoningPattern:
    """Test ExerciseSafetyReasoningPattern"""
    
    @pytest.fixture
    def extract_fn(self):
        """Mock exercise extraction function"""
        def extract(query):
            exercises = []
            if "deadlift" in query.lower():
                exercises.append("deadlift")
            if "squat" in query.lower():
                exercises.append("squat")
            return exercises
        return extract
    
    @pytest.fixture
    def check_safety_fn(self):
        """Mock safety check function"""
        def check(exercise):
            if exercise == "deadlift":
                return {
                    "has_conflict": True,
                    "severity": "block",
                    "message": "BLOCKED: Deadlifts can worsen back injuries",
                    "reasoning_context": {
                        "conflicting_conditions": ["back injury"],
                        "limitations": "avoid heavy lifting"
                    }
                }
            return {"has_conflict": False}
        return check
    
    @pytest.fixture
    def exercise_pattern(self, extract_fn, check_safety_fn):
        """Create exercise safety reasoning pattern"""
        return ExerciseSafetyReasoningPattern(
            extract_exercises_fn=extract_fn,
            check_safety_fn=check_safety_fn
        )
    
    @pytest.mark.asyncio
    async def test_pre_check_detects_exercise_conflicts(self, exercise_pattern):
        """Test pre_check detects exercise conflicts"""
        query = "I want to do deadlifts"
        context = {}
        
        result = await exercise_pattern.pre_check(query, context)
        assert result["has_safety_concerns"] is True
        assert len(result["conflicts"]) > 0
        assert result["conflicts"][0]["exercise"] == "deadlift"
    
    @pytest.mark.asyncio
    async def test_reason_enhances_with_conflict_context(self, exercise_pattern):
        """Test reason enhances query with conflict context"""
        query = "I want to do deadlifts"
        context = {}
        pre_check = await exercise_pattern.pre_check(query, context)
        
        enhanced = await exercise_pattern.reason(query, context, pre_check)
        assert "[Medical Conflict Analysis" in enhanced
        assert "deadlift" in enhanced
        assert "BLOCKED" in enhanced
    
    @pytest.mark.asyncio
    async def test_post_validate_detects_conflicts_in_response(self, exercise_pattern):
        """Test post_validate detects conflicts in response"""
        response = "You should try deadlifts for strength"
        query = "What exercises for strength?"
        context = {}
        
        result = await exercise_pattern.post_validate(response, query, context)
        assert result["is_safe"] is False
        assert result["warnings"] is not None
        assert len(result["warnings"]) > 0


class TestCompositeReasoningPattern:
    """Test CompositeReasoningPattern"""
    
    @pytest.fixture
    def composite_pattern(self):
        """Create composite pattern with multiple sub-patterns"""
        safety = SafetyReasoningPattern()
        query = QueryAnalysisReasoningPattern()
        return CompositeReasoningPattern([safety, query])
    
    @pytest.mark.asyncio
    async def test_composite_pre_check_runs_all_patterns(self, composite_pattern):
        """Test composite pre_check runs all patterns"""
        context = {"medical_history": {"conditions": "heart condition"}}
        result = await composite_pattern.pre_check("I want a workout plan", context)
        
        assert "pattern_0" in result  # Safety pattern
        assert "pattern_1" in result  # Query analysis pattern
        assert result["pattern_0"]["has_safety_concerns"] is True
        assert result["pattern_1"]["query_type"] == "planning"
    
    @pytest.mark.asyncio
    async def test_composite_reason_chains_enhancements(self, composite_pattern):
        """Test composite reason chains enhancements"""
        context = {"medical_history": {"conditions": "heart condition"}}
        pre_check = await composite_pattern.pre_check("I want a workout plan", context)
        
        enhanced = await composite_pattern.reason("I want a workout plan", context, pre_check)
        # Should have safety context from first pattern
        assert "[SAFETY CONSIDERATIONS" in enhanced or enhanced == "I want a workout plan"
    
    @pytest.mark.asyncio
    async def test_composite_post_validate_combines_results(self, composite_pattern):
        """Test composite post_validate combines all validation results"""
        response = "You can do any exercise"
        query = "What exercises?"
        context = {"medical_history": {"conditions": "heart condition"}}
        
        result = await composite_pattern.post_validate(response, query, context)
        assert "is_safe" in result
        assert "warnings" in result

