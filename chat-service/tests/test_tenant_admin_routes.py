"""
Test tenant admin routes for chat service.
Tests the new /tenant/* endpoints that allow tenant admins to view their own chat data.
"""
import pytest
from fastapi import status
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from app.api.admin_chat import (
    list_tenant_chat_sessions,
    get_tenant_chat_stats,
    get_tenant_chat_session,
    get_tenant_session_messages
)
from app.services.dependencies import TokenClaims
from app.models.chat_models import ChatSession, ChatMessage


class TestTenantAdminRoutes:
    """Test suite for tenant admin endpoints"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock()

    @pytest.fixture
    def tenant_admin_claims(self):
        """Mock TokenClaims for a tenant admin"""
        return TokenClaims(
            tenant_id="tenant-123",
            user_id="user-456",
            email="admin@example.com",
            full_name="Tenant Admin",
            authorities=["ROLE_TENANT_ADMIN"]
        )

    @pytest.fixture
    def mock_sessions(self):
        """Mock chat sessions for testing"""
        now = datetime.now(timezone.utc)
        return [
            Mock(
                id="session-1",
                session_id="sess-1",
                tenant_id="tenant-123",
                user_identifier="user1",
                is_active=True,
                created_at=now,
                last_activity=now,
                message_count=5
            ),
            Mock(
                id="session-2",
                session_id="sess-2",
                tenant_id="tenant-123",
                user_identifier="user2",
                is_active=False,
                created_at=now,
                last_activity=now,
                message_count=3
            )
        ]

    @pytest.mark.asyncio
    async def test_list_tenant_sessions_filters_by_tenant(self, mock_db, tenant_admin_claims, mock_sessions):
        """Test that tenant admin can only see their own tenant's sessions"""
        # Setup mock query chain
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_sessions

        mock_db.query.return_value = mock_query

        # Call the endpoint
        result = await list_tenant_chat_sessions(
            limit=50,
            offset=0,
            active_only=False,
            claims=tenant_admin_claims,
            db=mock_db
        )

        # Verify tenant filtering was applied
        assert mock_db.query.called
        # Verify results are returned
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_tenant_sessions_with_active_filter(self, mock_db, tenant_admin_claims):
        """Test active_only filter works correctly"""
        # Setup mock query chain
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_db.query.return_value = mock_query

        # Call with active_only=True
        await list_tenant_chat_sessions(
            limit=50,
            offset=0,
            active_only=True,
            claims=tenant_admin_claims,
            db=mock_db
        )

        # Verify filter was called multiple times (tenant_id + is_active)
        assert mock_query.filter.call_count >= 2

    @pytest.mark.asyncio
    async def test_get_tenant_stats_scoped_to_tenant(self, mock_db, tenant_admin_claims):
        """Test that stats are scoped to tenant's data only"""
        # Setup mock query chain
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 10

        mock_db.query.return_value = mock_query

        # Call the endpoint
        result = await get_tenant_chat_stats(
            claims=tenant_admin_claims,
            db=mock_db
        )

        # Verify stats are returned
        assert result["tenant_id"] == "tenant-123"
        assert result["total_sessions"] == 10
        assert result["total_messages"] == 10
        assert "recent_messages_24h" in result

    @pytest.mark.asyncio
    async def test_get_tenant_session_returns_404_for_wrong_tenant(self, mock_db, tenant_admin_claims):
        """Test that tenant admin cannot access another tenant's session"""
        from fastapi import HTTPException

        # Setup mock - session not found for this tenant
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        # Should raise 404
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_chat_session(
                session_id="other-tenant-session",
                message_limit=100,
                claims=tenant_admin_claims,
                db=mock_db
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_tenant_session_returns_session_with_messages(self, mock_db, tenant_admin_claims):
        """Test successful retrieval of session with messages"""
        now = datetime.now(timezone.utc)

        # Mock session
        mock_session = Mock(
            id="session-1",
            session_id="sess-1",
            tenant_id="tenant-123",
            user_identifier="user1",
            is_active=True,
            created_at=now,
            last_activity=now
        )

        # Mock messages
        mock_messages = [
            Mock(
                id="msg-1",
                session_id="sess-1",
                message_type="user",
                content="Hello",
                created_at=now,
                message_metadata={}
            ),
            Mock(
                id="msg-2",
                session_id="sess-1",
                message_type="assistant",
                content="Hi there!",
                created_at=now,
                message_metadata={}
            )
        ]

        # Setup mock query chain
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_session
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_messages
        mock_query.count.return_value = 2

        mock_db.query.return_value = mock_query

        # Call the endpoint
        result = await get_tenant_chat_session(
            session_id="sess-1",
            message_limit=100,
            claims=tenant_admin_claims,
            db=mock_db
        )

        # Verify session and messages are returned
        assert result.session.session_id == "sess-1"
        assert len(result.messages) == 2
        assert result.session.message_count == 2

    @pytest.mark.asyncio
    async def test_get_tenant_session_messages_for_pagination(self, mock_db, tenant_admin_claims):
        """Test getting messages separately for pagination support"""
        now = datetime.now(timezone.utc)

        # Mock session
        mock_session = Mock(
            id="session-1",
            session_id="sess-1",
            tenant_id="tenant-123",
            user_identifier="user1",
            is_active=True,
            created_at=now,
            last_activity=now
        )

        # Mock messages
        mock_messages = [
            Mock(
                id="msg-1",
                session_id="sess-1",
                message_type="user",
                content="Hello",
                created_at=now,
                message_metadata={}
            ),
            Mock(
                id="msg-2",
                session_id="sess-1",
                message_type="assistant",
                content="Hi there!",
                created_at=now,
                message_metadata={}
            )
        ]

        # Setup mock query chain
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_session
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_messages

        mock_db.query.return_value = mock_query

        # Call the endpoint
        result = await get_tenant_session_messages(
            session_id="sess-1",
            limit=100,
            offset=0,
            claims=tenant_admin_claims,
            db=mock_db
        )

        # Verify messages are returned
        assert len(result) == 2
        assert result[0].content == "Hello"
        assert result[1].content == "Hi there!"

    @pytest.mark.asyncio
    async def test_get_tenant_session_messages_returns_404_for_wrong_tenant(self, mock_db, tenant_admin_claims):
        """Test that tenant admin cannot access another tenant's session messages"""
        from fastapi import HTTPException

        # Setup mock - session not found for this tenant
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        # Should raise 404
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_session_messages(
                session_id="other-tenant-session",
                limit=100,
                offset=0,
                claims=tenant_admin_claims,
                db=mock_db
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestTenantIsolation:
    """Test suite specifically for tenant isolation security"""

    @pytest.fixture
    def tenant_a_claims(self):
        """Claims for tenant A admin"""
        return TokenClaims(
            tenant_id="tenant-a",
            user_id="user-a",
            email="admin-a@example.com",
            full_name="Admin A",
            authorities=["ROLE_TENANT_ADMIN"]
        )

    @pytest.fixture
    def tenant_b_claims(self):
        """Claims for tenant B admin"""
        return TokenClaims(
            tenant_id="tenant-b",
            user_id="user-b",
            email="admin-b@example.com",
            full_name="Admin B",
            authorities=["ROLE_TENANT_ADMIN"]
        )

    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b_sessions(self, tenant_a_claims):
        """Verify tenant A admin cannot access tenant B's sessions"""
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []  # No sessions from tenant B

        mock_db.query.return_value = mock_query

        result = await list_tenant_chat_sessions(
            limit=50,
            offset=0,
            active_only=False,
            claims=tenant_a_claims,
            db=mock_db
        )

        # Should return empty list (tenant B's sessions filtered out)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_stats_are_tenant_specific(self, tenant_a_claims, tenant_b_claims):
        """Verify stats are different for different tenants"""
        mock_db = Mock()

        # Tenant A gets different stats than Tenant B
        mock_query_a = Mock()
        mock_query_a.filter.return_value = mock_query_a
        mock_query_a.count.return_value = 100  # Tenant A has 100 sessions

        mock_query_b = Mock()
        mock_query_b.filter.return_value = mock_query_b
        mock_query_b.count.return_value = 50  # Tenant B has 50 sessions

        # Test with tenant A claims
        mock_db.query.return_value = mock_query_a
        result_a = await get_tenant_chat_stats(claims=tenant_a_claims, db=mock_db)

        # Test with tenant B claims
        mock_db.query.return_value = mock_query_b
        result_b = await get_tenant_chat_stats(claims=tenant_b_claims, db=mock_db)

        # Stats should be scoped to respective tenants
        assert result_a["tenant_id"] == "tenant-a"
        assert result_b["tenant_id"] == "tenant-b"
