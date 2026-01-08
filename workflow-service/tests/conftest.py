"""
Pytest configuration and shared fixtures for workflow-service tests
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_variables():
    """Sample workflow variables for testing"""
    return {
        "user_name": "John Doe",
        "user_email": "john@example.com",
        "age": 25,
        "country": "USA"
    }


@pytest.fixture
def execution_context():
    """Sample execution context for testing"""
    return {
        "workflow_id": "test-workflow-123",
        "execution_id": "test-exec-456",
        "tenant_id": "test-tenant-789",
        "session_id": "test-session-abc",
        "user_identifier": "test-user-def"
    }


@pytest.fixture
def mock_workflow_definition():
    """Mock workflow definition with steps attribute"""
    mock_def = Mock()
    mock_def.steps = []  # Empty steps list by default
    return mock_def
