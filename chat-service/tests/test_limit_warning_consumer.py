"""
Tests for aio-pika limit warning consumer in chat-service.

Tests LimitWarningConsumer to ensure the migration from pika to aio-pika
works correctly with proper async patterns.
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch

from app.services.limit_warning_consumer import LimitWarningConsumer


class TestLimitWarningConsumer:
    """Test suite for LimitWarningConsumer (aio-pika)"""

    @pytest.fixture
    def consumer(self):
        """Create LimitWarningConsumer instance for testing"""
        return LimitWarningConsumer()

    @pytest.mark.asyncio
    async def test_initialization(self, consumer):
        """Test that LimitWarningConsumer initializes correctly"""
        assert consumer.connection is None
        assert consumer.consume_task is None
        assert consumer.exchange == "usage.events"
        assert consumer.queue_name == "chat-service.limit-warnings"

    @pytest.mark.asyncio
    async def test_connect_creates_robust_connection(self, consumer):
        """Test that connect() creates a robust connection"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False

        with patch('app.services.limit_warning_consumer.connect_robust', return_value=mock_connection) as mock_connect:
            await consumer.connect()

            # Verify connect_robust was called with correct parameters
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            assert 'host' in call_kwargs
            assert 'port' in call_kwargs
            assert call_kwargs['reconnect_interval'] == 1.0
            assert call_kwargs['fail_fast'] is False

            # Verify connection is stored
            assert consumer.connection == mock_connection

    @pytest.mark.asyncio
    async def test_connect_skips_if_already_connected(self, consumer):
        """Test that connect() skips if already connected"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        consumer.connection = mock_connection

        with patch('app.services.limit_warning_consumer.connect_robust') as mock_connect:
            await consumer.connect()

            # Should not call connect_robust if already connected
            mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_sets_up_queue_with_routing_keys(self, consumer):
        """Test that start() sets up queue and binds both routing keys"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_queue = AsyncMock()

        mock_channel.set_qos = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.declare_queue = AsyncMock(return_value=mock_queue)
        mock_queue.bind = AsyncMock()
        mock_queue.consume = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)

        with patch('app.services.limit_warning_consumer.connect_robust', return_value=mock_connection):
            with patch('asyncio.create_task') as mock_create_task:
                await consumer.start()

                # Verify QoS was set
                mock_channel.set_qos.assert_called_once_with(prefetch_count=10)

                # Verify exchange was declared
                mock_channel.declare_exchange.assert_called_once()

                # Verify queue was declared
                mock_channel.declare_queue.assert_called_once()

                # Verify queue was bound to BOTH routing keys
                assert mock_queue.bind.call_count == 2
                routing_keys = [call.kwargs['routing_key'] for call in mock_queue.bind.call_args_list]
                assert "usage.limit.warning" in routing_keys
                assert "usage.limit.exceeded" in routing_keys

                # Verify consume task was created
                mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_message_invalidates_cache_for_tenant(self, consumer):
        """Test that message handling invalidates cache for the tenant"""
        message_data = {
            "tenant_id": "tenant-123",
            "usage_type": "daily_chats",
            "current_usage": 95,
            "limit": 100,
            "warning_type": "approaching"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.routing_key = "usage.limit.warning"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock usage_cache
        with patch('app.services.limit_warning_consumer.usage_cache') as mock_cache:
            await consumer._on_message(mock_message)

            # Verify cache was invalidated for the tenant
            mock_cache.invalidate_cache.assert_called_once_with("tenant-123")

    @pytest.mark.asyncio
    async def test_on_message_handles_limit_exceeded(self, consumer):
        """Test handling of usage.limit.exceeded event"""
        message_data = {
            "tenant_id": "tenant-456",
            "usage_type": "monthly_chats",
            "current_usage": 105,
            "limit": 100,
            "warning_type": "exceeded"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.routing_key = "usage.limit.exceeded"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock usage_cache
        with patch('app.services.limit_warning_consumer.usage_cache') as mock_cache:
            await consumer._on_message(mock_message)

            # Verify cache was invalidated
            mock_cache.invalidate_cache.assert_called_once_with("tenant-456")

    @pytest.mark.asyncio
    async def test_on_message_handles_missing_tenant_id(self, consumer):
        """Test that message without tenant_id doesn't crash"""
        message_data = {
            "usage_type": "daily_chats",
            "current_usage": 95,
            "limit": 100
            # Missing tenant_id
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.routing_key = "usage.limit.warning"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock usage_cache
        with patch('app.services.limit_warning_consumer.usage_cache') as mock_cache:
            # Should not raise
            await consumer._on_message(mock_message)

            # Cache should NOT be invalidated (no tenant_id)
            mock_cache.invalidate_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_handles_json_decode_error(self, consumer):
        """Test handling of malformed JSON"""
        mock_message = AsyncMock()
        mock_message.body = b"invalid-json{{"
        mock_message.routing_key = "usage.limit.warning"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Should not raise (error is caught)
        await consumer._on_message(mock_message)

    @pytest.mark.asyncio
    async def test_on_message_handles_cache_error_gracefully(self, consumer):
        """Test that cache invalidation errors don't crash the consumer"""
        message_data = {
            "tenant_id": "tenant-789",
            "usage_type": "documents",
            "warning_type": "exceeded"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.routing_key = "usage.limit.exceeded"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock usage_cache to raise error
        with patch('app.services.limit_warning_consumer.usage_cache') as mock_cache:
            mock_cache.invalidate_cache.side_effect = Exception("Redis connection error")

            # Should not raise (error is caught and logged)
            await consumer._on_message(mock_message)

            # Verify cache invalidation was attempted
            mock_cache.invalidate_cache.assert_called_once_with("tenant-789")

    @pytest.mark.asyncio
    async def test_stop_cancels_task_and_closes_connection(self, consumer):
        """Test that stop() cancels task and closes connection"""
        import asyncio

        # Create a real async task that can be cancelled
        async def dummy_consume():
            await asyncio.sleep(100)

        mock_task = asyncio.create_task(dummy_consume())
        consumer.consume_task = mock_task

        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        consumer.connection = mock_connection

        await consumer.stop()

        # Verify task was cancelled
        assert mock_task.cancelled()

        # Verify connection was closed
        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_message_different_routing_keys(self, consumer):
        """Test that both routing keys are handled correctly"""
        routing_keys = ["usage.limit.warning", "usage.limit.exceeded"]

        for routing_key in routing_keys:
            message_data = {
                "tenant_id": f"tenant-{routing_key}",
                "usage_type": "daily_chats"
            }

            mock_message = AsyncMock()
            mock_message.body = json.dumps(message_data).encode()
            mock_message.routing_key = routing_key

            # Create proper async context manager
            class AsyncContextManagerMock:
                async def __aenter__(self):
                    return None
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None

            mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

            # Mock usage_cache
            with patch('app.services.limit_warning_consumer.usage_cache') as mock_cache:
                await consumer._on_message(mock_message)

                # Verify cache was invalidated
                mock_cache.invalidate_cache.assert_called_once_with(f"tenant-{routing_key}")


# Integration tests (require live RabbitMQ - skipped by default)
@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_limit_warning_consumer_integration():
    """Integration test for LimitWarningConsumer with real RabbitMQ"""
    consumer = LimitWarningConsumer()

    try:
        await consumer.connect()
        await consumer.start()

        # Wait a bit for consumer to start
        import asyncio
        await asyncio.sleep(2)

        # Verify consumer is running
        assert consumer.consume_task is not None
        assert not consumer.consume_task.done()

    finally:
        await consumer.stop()


@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_limit_warning_consumer_reconnection():
    """Integration test for automatic reconnection"""
    consumer = LimitWarningConsumer()

    try:
        await consumer.connect()
        await consumer.start()

        # Verify initial connection
        assert consumer.connection is not None
        assert not consumer.connection.is_closed

        # Close connection to simulate failure
        await consumer.connection.close()

        # Wait for automatic reconnection
        import asyncio
        await asyncio.sleep(3)

        # Connection should be restored automatically
        # (aio-pika's connect_robust handles this)

    finally:
        await consumer.stop()
