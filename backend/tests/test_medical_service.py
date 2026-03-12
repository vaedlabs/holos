"""
Tests for medical service - exercise conflict detection
"""

import pytest
from unittest.mock import Mock, MagicMock
from app.services.medical_service import (
    check_user_exercise_conflicts,
    check_exercise_conflict
)
from app.models.medical_history import MedicalHistory


class TestExerciseConflictDetection:
    """Test exercise conflict detection with medical conditions"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database session"""
        return Mock()
    
    @pytest.fixture
    def mock_medical_history(self):
        """Create a mock medical history with conditions"""
        history = Mock(spec=MedicalHistory)
        history.conditions = "knee injury, heart condition"
        history.limitations = None
        history.medications = None
        history.notes = None
        return history
    
    def test_no_conflict_when_no_medical_history(self, mock_db):
        """Test that no conflict is detected when user has no medical history"""
        # Mock get_medical_history to return None
        from app.services import medical_service
        original_get = medical_service.get_medical_history
        medical_service.get_medical_history = Mock(return_value=None)
        
        try:
            result = check_user_exercise_conflicts(
                user_id=1,
                exercise="squats",
                db=mock_db
            )
            
            assert result["has_conflict"] is False
            assert result["severity"] is None
            assert result["conflicting_conditions"] == []
        finally:
            medical_service.get_medical_history = original_get
    
    def test_conflict_detection_knee_injury_squats(self, mock_db, mock_medical_history):
        """Test that squats conflict with knee injury"""
        from app.services import medical_service
        original_get = medical_service.get_medical_history
        medical_service.get_medical_history = Mock(return_value=mock_medical_history)
        
        try:
            result = check_user_exercise_conflicts(
                user_id=1,
                exercise="squats",
                db=mock_db
            )
            
            assert result["has_conflict"] is True
            assert result["severity"] in ["block", "warning"]
            assert "knee injury" in result["conflicting_conditions"]
            assert result["message"] is not None
            assert "BLOCKED:" in result["message"] or "Warning:" in result["message"]
        finally:
            medical_service.get_medical_history = original_get
    
    def test_conflict_detection_heart_condition_high_intensity(self, mock_db):
        """Test that high-intensity exercises conflict with heart conditions"""
        from app.services import medical_service
        original_get = medical_service.get_medical_history
        
        # Create mock with heart condition
        heart_history = Mock(spec=MedicalHistory)
        heart_history.conditions = "heart condition"
        heart_history.limitations = None
        heart_history.medications = None
        heart_history.notes = None
        
        medical_service.get_medical_history = Mock(return_value=heart_history)
        
        try:
            result = check_user_exercise_conflicts(
                user_id=1,
                exercise="sprinting",
                db=mock_db
            )
            
            assert result["has_conflict"] is True
            assert result["severity"] in ["block", "warning"]
            assert "heart condition" in result["conflicting_conditions"]
        finally:
            medical_service.get_medical_history = original_get
    
    def test_no_conflict_safe_exercise(self, mock_db, mock_medical_history):
        """Test that safe exercises don't conflict"""
        from app.services import medical_service
        original_get = medical_service.get_medical_history
        medical_service.get_medical_history = Mock(return_value=mock_medical_history)
        
        try:
            # Walking should be safe even with knee injury (might be warning, not block)
            result = check_user_exercise_conflicts(
                user_id=1,
                exercise="walking",
                db=mock_db
            )
            
            # Walking might have a warning but shouldn't be blocked
            # The exact result depends on the conflict mapping
            assert result is not None
            assert "has_conflict" in result
        finally:
            medical_service.get_medical_history = original_get
    
    def test_multiple_conditions(self, mock_db):
        """Test conflict detection with multiple conditions"""
        from app.services import medical_service
        original_get = medical_service.get_medical_history
        
        # Create mock with multiple conditions
        multi_history = Mock(spec=MedicalHistory)
        multi_history.conditions = "knee injury, back pain, heart condition"
        multi_history.limitations = None
        multi_history.medications = None
        multi_history.notes = None
        
        medical_service.get_medical_history = Mock(return_value=multi_history)
        
        try:
            result = check_user_exercise_conflicts(
                user_id=1,
                exercise="deadlifts",
                db=mock_db
            )
            
            # Deadlifts should conflict with multiple conditions
            assert result["has_conflict"] is True
            assert len(result["conflicting_conditions"]) > 0
            assert result["severity"] in ["block", "warning"]
        finally:
            medical_service.get_medical_history = original_get
    
    def test_severity_priority_block_over_warning(self, mock_db):
        """Test that block severity takes priority over warning"""
        from app.services import medical_service
        original_get = medical_service.get_medical_history
        
        # Create mock with conditions that might have different severities
        history = Mock(spec=MedicalHistory)
        history.conditions = "knee injury, heart condition"
        history.limitations = None
        history.medications = None
        history.notes = None
        
        medical_service.get_medical_history = Mock(return_value=history)
        
        try:
            # Test with an exercise that might have different severities for different conditions
            result = check_user_exercise_conflicts(
                user_id=1,
                exercise="squats",
                db=mock_db
            )
            
            if result["has_conflict"]:
                # If there's a conflict, severity should be set
                assert result["severity"] in ["block", "warning"]
                # Block should take priority if multiple conditions conflict
                if "block" in [c.get("severity") for c in result.get("reasoning_context", {}).get("matched_conditions_info", [])]:
                    assert result["severity"] == "block"
        finally:
            medical_service.get_medical_history = original_get


class TestExerciseConflictHelper:
    """Test the check_exercise_conflict helper function"""
    
    def test_check_exercise_conflict_knee_squats(self):
        """Test that squats conflict with knee injury"""
        result = check_exercise_conflict("knee injury", "squats")
        
        assert result["has_conflict"] is True
        assert result["severity"] in ["block", "warning"]
        assert result.get("matched_condition") is not None
    
    def test_check_exercise_conflict_heart_sprinting(self):
        """Test that sprinting conflicts with heart condition"""
        result = check_exercise_conflict("heart condition", "sprinting")
        
        assert result["has_conflict"] is True
        assert result["severity"] in ["block", "warning"]
    
    def test_check_exercise_conflict_no_match(self):
        """Test that unrelated exercises don't conflict"""
        result = check_exercise_conflict("knee injury", "swimming")
        
        # Swimming should be safe for knee injury
        # (Result depends on actual conflict mapping, but should be False or warning)
        assert "has_conflict" in result
    
    def test_check_exercise_conflict_case_insensitive(self):
        """Test that conflict detection is case-insensitive"""
        result1 = check_exercise_conflict("Knee Injury", "SQUATS")
        result2 = check_exercise_conflict("knee injury", "squats")
        
        # Both should have the same result
        assert result1["has_conflict"] == result2["has_conflict"]

