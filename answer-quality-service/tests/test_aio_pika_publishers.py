"""
Tests for aio-pika publishers in answer-quality-service.

Tests EventPublisher to ensure the migration from pika to aio-pika works correctly.
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch

from app.services.event_publisher import EventPublisher


class TestEventPublisher:
    """Test suite for EventPublisher (aio-pika)"""

    @pytest.fixture
    def publisher(self):
        """Create EventPublisher instance for testing"""
        return EventPublisher()

    @pytest.mark.asyncio
    async def test_initialization(self, publisher):
        """Test that EventPublisher initializes correctly"""
        assert publisher.connection is None

    @pytest.mark.asyncio
    async def test_connect_creates_robust_connection(self, publisher):
        """Test that connect() creates a robust connection"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection) as mock_connect:
            await publisher.connect()

            # Verify connect_robust was called with correct parameters
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            assert 'host' in call_kwargs
            assert 'port' in call_kwargs
            assert call_kwargs['reconnect_interval'] == 1.0
            assert call_kwargs['fail_fast'] is False

            # Verify connection is stored
            assert publisher.connection == mock_connection

    @pytest.mark.asyncio
    async def test_publish_feedback_submitted_success(self, publisher):
        """Test publishing feedback.submitted event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_feedback_submitted(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                feedback_type="helpful",
                has_comment=True
            )

            # Verify result
            assert result is True

            # Verify exchange.publish was called
            mock_exchange.publish.assert_called_once()
            call_args = mock_exchange.publish.call_args

            # Verify routing key
            assert call_args.kwargs['routing_key'] == 'feedback.submitted'

            # Verify message body
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['event_type'] == 'feedback.submitted'
            assert message_body['tenant_id'] == 'tenant-123'
            assert message_body['session_id'] == 'session-456'
            assert message_body['message_id'] == 'msg-789'
            assert message_body['feedback_type'] == 'helpful'
            assert message_body['has_comment'] is True

    @pytest.mark.asyncio
    async def test_publish_feedback_submitted_not_helpful(self, publisher):
        """Test publishing not_helpful feedback"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_feedback_submitted(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                feedback_type="not_helpful",
                has_comment=False
            )

            assert result is True

            # Verify message body
            call_args = mock_exchange.publish.call_args
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['feedback_type'] == 'not_helpful'
            assert message_body['has_comment'] is False

    @pytest.mark.asyncio
    async def test_publish_knowledge_gap_detected_success(self, publisher):
        """Test publishing knowledge.gap.detected event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_knowledge_gap_detected(
                tenant_id="tenant-123",
                gap_id="gap-456",
                pattern="pricing questions",
                occurrence_count=15,
                avg_confidence=0.45,
                example_questions=["How much does it cost?", "What is the price?", "Pricing info?"]
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'knowledge.gap.detected'

            # Verify message body
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['event_type'] == 'knowledge.gap.detected'
            assert message_body['tenant_id'] == 'tenant-123'
            assert message_body['gap_id'] == 'gap-456'
            assert message_body['pattern'] == 'pricing questions'
            assert message_body['occurrence_count'] == 15
            assert message_body['avg_confidence'] == 0.45
            assert len(message_body['example_questions']) == 3

    @pytest.mark.asyncio
    async def test_publish_knowledge_gap_limits_examples(self, publisher):
        """Test that knowledge gap event limits example questions to 3"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            # Pass 10 example questions
            many_questions = [f"Question {i}" for i in range(10)]

            result = await publisher.publish_knowledge_gap_detected(
                tenant_id="tenant-123",
                gap_id="gap-456",
                pattern="test pattern",
                occurrence_count=10,
                avg_confidence=0.5,
                example_questions=many_questions
            )

            assert result is True

            # Verify only 3 examples are included
            call_args = mock_exchange.publish.call_args
            message_body = json.loads(call_args.args[0].body.decode())
            assert len(message_body['example_questions']) == 3
            assert message_body['example_questions'] == ["Question 0", "Question 1", "Question 2"]

    @pytest.mark.asyncio
    async def test_publish_session_quality_updated_success(self, publisher):
        """Test publishing session.quality.updated event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_session_quality_updated(
                tenant_id="tenant-123",
                session_id="session-456",
                session_success=True,
                helpful_count=8,
                not_helpful_count=2
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'session.quality.updated'

            # Verify message body
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['event_type'] == 'session.quality.updated'
            assert message_body['tenant_id'] == 'tenant-123'
            assert message_body['session_id'] == 'session-456'
            assert message_body['session_success'] is True
            assert message_body['helpful_count'] == 8
            assert message_body['not_helpful_count'] == 2

    @pytest.mark.asyncio
    async def test_publish_session_quality_unsuccessful(self, publisher):
        """Test publishing unsuccessful session quality"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_session_quality_updated(
                tenant_id="tenant-123",
                session_id="session-456",
                session_success=False,
                helpful_count=1,
                not_helpful_count=7
            )

            assert result is True

            # Verify message body
            call_args = mock_exchange.publish.call_args
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['session_success'] is False
            assert message_body['helpful_count'] == 1
            assert message_body['not_helpful_count'] == 7

    @pytest.mark.asyncio
    async def test_publish_feedback_handles_exceptions(self, publisher):
        """Test that publish_feedback_submitted handles exceptions gracefully"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_connection.channel.side_effect = Exception("Channel error")

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_feedback_submitted(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                feedback_type="helpful",
                has_comment=False
            )

            # Should return False on error
            assert result is False

    @pytest.mark.asyncio
    async def test_publish_knowledge_gap_handles_exceptions(self, publisher):
        """Test that publish_knowledge_gap_detected handles exceptions gracefully"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_connection.channel.side_effect = Exception("Channel error")

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_knowledge_gap_detected(
                tenant_id="tenant-123",
                gap_id="gap-456",
                pattern="test",
                occurrence_count=5,
                avg_confidence=0.5,
                example_questions=[]
            )

            # Should return False on error
            assert result is False

    @pytest.mark.asyncio
    async def test_publish_session_quality_handles_exceptions(self, publisher):
        """Test that publish_session_quality_updated handles exceptions gracefully"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_connection.channel.side_effect = Exception("Channel error")

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_session_quality_updated(
                tenant_id="tenant-123",
                session_id="session-456",
                session_success=True,
                helpful_count=5,
                not_helpful_count=0
            )

            # Should return False on error
            assert result is False

    @pytest.mark.asyncio
    async def test_close_connection(self, publisher):
        """Test closing connection"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        publisher.connection = mock_connection

        await publisher.close()

        # Verify close was called
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_skips_if_already_connected(self, publisher):
        """Test that connect() skips if already connected"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        publisher.connection = mock_connection

        with patch('app.services.event_publisher.connect_robust') as mock_connect:
            await publisher.connect()

            # Should not call connect_robust if already connected
            mock_connect.assert_not_called()


# Integration tests (require live RabbitMQ - skipped by default)
@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_event_publisher_integration():
    """Integration test for EventPublisher with real RabbitMQ"""
    publisher = EventPublisher()

    try:
        await publisher.connect()

        # Test publishing feedback
        result = await publisher.publish_feedback_submitted(
            tenant_id="test-tenant",
            session_id="test-session",
            message_id="test-msg",
            feedback_type="helpful",
            has_comment=True
        )
        assert result is True

        # Test publishing knowledge gap
        result = await publisher.publish_knowledge_gap_detected(
            tenant_id="test-tenant",
            gap_id="test-gap",
            pattern="test pattern",
            occurrence_count=5,
            avg_confidence=0.5,
            example_questions=["Q1", "Q2", "Q3"]
        )
        assert result is True

        # Test publishing session quality
        result = await publisher.publish_session_quality_updated(
            tenant_id="test-tenant",
            session_id="test-session",
            session_success=True,
            helpful_count=3,
            not_helpful_count=1
        )
        assert result is True

    finally:
        await publisher.close()


@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_event_publisher_reconnection():
    """Integration test for automatic reconnection"""
    publisher = EventPublisher()

    try:
        await publisher.connect()

        # Publish initial message
        result = await publisher.publish_feedback_submitted(
            tenant_id="test-tenant",
            session_id="test-session",
            message_id="msg-1",
            feedback_type="helpful",
            has_comment=False
        )
        assert result is True

        # Close connection to simulate failure
        await publisher.close()
        publisher.connection = None

        # Publish again - should auto-reconnect
        result = await publisher.publish_feedback_submitted(
            tenant_id="test-tenant",
            session_id="test-session",
            message_id="msg-2",
            feedback_type="not_helpful",
            has_comment=True
        )
        assert result is True

    finally:
        await publisher.close()
