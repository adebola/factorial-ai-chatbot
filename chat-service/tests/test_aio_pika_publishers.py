"""
Tests for aio-pika publishers in chat-service.

Tests ChatEventPublisher to ensure the migration from pika to aio-pika works correctly.
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch

from app.services.event_publisher import ChatEventPublisher


class TestChatEventPublisher:
    """Test suite for ChatEventPublisher (aio-pika)"""

    @pytest.fixture
    def publisher(self):
        """Create ChatEventPublisher instance for testing"""
        return ChatEventPublisher()

    @pytest.mark.asyncio
    async def test_initialization(self, publisher):
        """Test that ChatEventPublisher initializes correctly"""
        assert publisher.connection is None
        assert publisher.rabbitmq_host == "localhost"
        assert publisher.rabbitmq_port == 5672
        assert publisher.chat_exchange == "chat.events"
        assert publisher.usage_exchange == "usage.events"

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
            assert call_kwargs['host'] == 'localhost'
            assert call_kwargs['port'] == 5672
            assert call_kwargs['reconnect_interval'] == 1.0
            assert call_kwargs['fail_fast'] is False

            # Verify connection is stored
            assert publisher.connection == mock_connection

    @pytest.mark.asyncio
    async def test_publish_message_created_user_message(self, publisher):
        """Test publishing message.created event for user message"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_message_created(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                message_type="user",
                content="Hello, how can you help me?",
                quality_metrics=None
            )

            # Verify result
            assert result is True

            # Verify exchange.publish was called
            mock_exchange.publish.assert_called_once()
            call_args = mock_exchange.publish.call_args

            # Verify routing key for chat exchange
            assert call_args.kwargs['routing_key'] == 'message.created'

            # Verify message body
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['event_type'] == 'message.created'
            assert message_body['tenant_id'] == 'tenant-123'
            assert message_body['session_id'] == 'session-456'
            assert message_body['message_id'] == 'msg-789'
            assert message_body['message_type'] == 'user'
            assert message_body['content_preview'] == 'Hello, how can you help me?'
            assert 'quality_metrics' not in message_body  # User messages don't have metrics

    @pytest.mark.asyncio
    async def test_publish_message_created_assistant_message_with_metrics(self, publisher):
        """Test publishing message.created event for assistant message with quality metrics"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        quality_metrics = {
            "response_time_ms": 1500,
            "token_count": 250,
            "sources_used": 3
        }

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_message_created(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                message_type="assistant",
                content="Based on the documents...",
                quality_metrics=quality_metrics
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify message body includes quality metrics
            call_args = mock_exchange.publish.call_args
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['message_type'] == 'assistant'
            assert message_body['quality_metrics'] == quality_metrics

    @pytest.mark.asyncio
    async def test_publish_message_created_long_content_preview(self, publisher):
        """Test that content is truncated to 200 characters for preview"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        long_content = "A" * 500  # 500 character string

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_message_created(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                message_type="user",
                content=long_content,
                quality_metrics=None
            )

            assert result is True

            # Verify content is truncated to 200 chars
            call_args = mock_exchange.publish.call_args
            message_body = json.loads(call_args.args[0].body.decode())
            assert len(message_body['content_preview']) == 200
            assert message_body['content_preview'] == "A" * 200

    @pytest.mark.asyncio
    async def test_publish_chat_usage_event_success(self, publisher):
        """Test publishing usage.chat.message event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_chat_usage_event(
                tenant_id="tenant-123",
                session_id="session-456",
                message_count=2
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key for usage exchange
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'usage.chat.message'

            # Verify message body
            message_body = json.loads(call_args.args[0].body.decode())
            assert message_body['event_type'] == 'usage.chat.message'
            assert message_body['tenant_id'] == 'tenant-123'
            assert message_body['session_id'] == 'session-456'
            assert message_body['message_count'] == 2
            assert 'event_id' in message_body  # Should have UUID event_id

    @pytest.mark.asyncio
    async def test_publish_message_created_handles_exceptions(self, publisher):
        """Test that publish_message_created handles exceptions gracefully"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_connection.channel.side_effect = Exception("Channel error")

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_message_created(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                message_type="user",
                content="Test message"
            )

            # Should return False on error
            assert result is False

    @pytest.mark.asyncio
    async def test_publish_chat_usage_event_handles_exceptions(self, publisher):
        """Test that publish_chat_usage_event handles exceptions gracefully"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_connection.channel.side_effect = Exception("Channel error")

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_chat_usage_event(
                tenant_id="tenant-123",
                session_id="session-456",
                message_count=1
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

    @pytest.mark.asyncio
    async def test_publish_uses_correct_exchanges(self, publisher):
        """Test that messages are published to correct exchanges"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.event_publisher.connect_robust', return_value=mock_connection):
            # Test message.created uses chat_exchange
            await publisher.publish_message_created(
                tenant_id="tenant-123",
                session_id="session-456",
                message_id="msg-789",
                message_type="user",
                content="test"
            )

            # Verify chat.events exchange was declared
            declare_calls = mock_channel.declare_exchange.call_args_list
            assert declare_calls[-1][0][0] == "chat.events"

            # Test usage.chat.message uses usage_exchange
            await publisher.publish_chat_usage_event(
                tenant_id="tenant-123",
                session_id="session-456"
            )

            # Verify usage.events exchange was declared
            declare_calls = mock_channel.declare_exchange.call_args_list
            assert declare_calls[-1][0][0] == "usage.events"


# Integration tests (require live RabbitMQ - skipped by default)
@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_chat_event_publisher_integration():
    """Integration test for ChatEventPublisher with real RabbitMQ"""
    publisher = ChatEventPublisher()

    try:
        await publisher.connect()

        # Test publishing message.created
        result = await publisher.publish_message_created(
            tenant_id="test-tenant",
            session_id="test-session",
            message_id="test-msg",
            message_type="user",
            content="Integration test message"
        )
        assert result is True

        # Test publishing usage event
        result = await publisher.publish_chat_usage_event(
            tenant_id="test-tenant",
            session_id="test-session",
            message_count=1
        )
        assert result is True

    finally:
        await publisher.close()


@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_chat_event_publisher_reconnection():
    """Integration test for automatic reconnection"""
    publisher = ChatEventPublisher()

    try:
        await publisher.connect()

        # Publish initial message
        result = await publisher.publish_message_created(
            tenant_id="test-tenant",
            session_id="test-session",
            message_id="msg-1",
            message_type="user",
            content="Message before reconnection"
        )
        assert result is True

        # Close connection to simulate failure
        await publisher.close()
        publisher.connection = None

        # Publish again - should auto-reconnect
        result = await publisher.publish_message_created(
            tenant_id="test-tenant",
            session_id="test-session",
            message_id="msg-2",
            message_type="user",
            content="Message after reconnection"
        )
        assert result is True

    finally:
        await publisher.close()