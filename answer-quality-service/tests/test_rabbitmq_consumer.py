"""
Tests for aio-pika RabbitMQ consumer in answer-quality-service.

Tests RabbitMQConsumer to ensure the migration from pika to aio-pika
works correctly with proper async patterns and quality analysis.
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime

from app.services.rabbitmq_consumer import RabbitMQConsumer
from app.schemas.quality import ChatMessageEvent


class TestRabbitMQConsumer:
    """Test suite for RabbitMQConsumer (aio-pika)"""

    @pytest.fixture
    def consumer(self):
        """Create RabbitMQConsumer instance for testing"""
        return RabbitMQConsumer()

    @pytest.mark.asyncio
    async def test_initialization(self, consumer):
        """Test that RabbitMQConsumer initializes correctly"""
        assert consumer.connection is None
        assert consumer.consume_task is None

    @pytest.mark.asyncio
    async def test_connect_creates_robust_connection(self, consumer):
        """Test that connect() creates a robust connection"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False

        with patch('app.services.rabbitmq_consumer.connect_robust', return_value=mock_connection) as mock_connect:
            await consumer.connect()

            # Verify connect_robust was called with correct parameters
            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args.kwargs
            assert 'host' in call_kwargs
            assert 'port' in call_kwargs
            assert 'login' in call_kwargs
            assert 'password' in call_kwargs
            assert call_kwargs['reconnect_interval'] == 1.0
            assert call_kwargs['fail_fast'] is False

            # Verify connection is stored
            assert consumer.connection == mock_connection

    @pytest.mark.asyncio
    async def test_start_consuming_sets_up_queue(self, consumer):
        """Test that start_consuming() sets up the quality analysis queue"""
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

        with patch('app.services.rabbitmq_consumer.connect_robust', return_value=mock_connection):
            with patch('asyncio.create_task') as mock_create_task:
                await consumer.start_consuming()

                # Verify QoS was set
                mock_channel.set_qos.assert_called_once_with(prefetch_count=1)

                # Verify queue was bound to message.created routing key
                assert mock_queue.bind.call_count == 1
                bind_call_kwargs = mock_queue.bind.call_args.kwargs
                assert bind_call_kwargs['routing_key'] == "message.created"

                # Verify consume task was created
                mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_assistant_message_success(self, consumer):
        """Test successful processing of assistant message"""
        message_data = {
            "event_type": "message.created",
            "tenant_id": "tenant-123",
            "message_id": "msg-456",
            "session_id": "session-789",
            "message_type": "assistant",
            "content_preview": "This is an AI response.",
            "timestamp": "2024-01-01T12:00:00Z",
            "quality_metrics": {
                "sources_found": 3,
                "confidence_score": 0.85
            }
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock database and quality analyzer
        mock_quality_record = Mock()
        mock_quality_record.answer_confidence = 0.85
        mock_quality_record.basic_sentiment = "positive"

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze_message_quality = AsyncMock(return_value=mock_quality_record)

        with patch('app.services.rabbitmq_consumer.SessionLocal') as mock_session:
            with patch('app.services.rabbitmq_consumer.QualityAnalyzer', return_value=mock_analyzer):
                await consumer._on_message(mock_message)

                # Verify analyzer was called with correct parameters
                mock_analyzer.analyze_message_quality.assert_called_once()
                call_kwargs = mock_analyzer.analyze_message_quality.call_args.kwargs
                assert call_kwargs['tenant_id'] == "tenant-123"
                assert call_kwargs['message_id'] == "msg-456"
                assert call_kwargs['session_id'] == "session-789"
                assert call_kwargs['metrics']['sources_found'] == 3

    @pytest.mark.asyncio
    async def test_skip_user_message(self, consumer):
        """Test that user messages are skipped (only assistant messages processed)"""
        message_data = {
            "event_type": "message.created",
            "tenant_id": "tenant-123",
            "message_id": "msg-456",
            "session_id": "session-789",
            "message_type": "user",  # User message, should be skipped
            "content_preview": "This is a user question.",
            "timestamp": "2024-01-01T12:00:00Z"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        with patch('app.services.rabbitmq_consumer.SessionLocal'):
            with patch('app.services.rabbitmq_consumer.QualityAnalyzer') as mock_analyzer_class:
                await consumer._on_message(mock_message)

                # Verify analyzer was NOT called (user message skipped)
                mock_analyzer_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_with_empty_metrics(self, consumer):
        """Test processing message with no quality metrics"""
        message_data = {
            "event_type": "message.created",
            "tenant_id": "tenant-123",
            "message_id": "msg-456",
            "session_id": "session-789",
            "message_type": "assistant",
            "content_preview": "AI response without metrics.",
            "timestamp": "2024-01-01T12:00:00Z"
            # No quality_metrics field
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock analyzer
        mock_quality_record = Mock()
        mock_quality_record.answer_confidence = None
        mock_quality_record.basic_sentiment = "neutral"

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze_message_quality = AsyncMock(return_value=mock_quality_record)

        with patch('app.services.rabbitmq_consumer.SessionLocal'):
            with patch('app.services.rabbitmq_consumer.QualityAnalyzer', return_value=mock_analyzer):
                await consumer._on_message(mock_message)

                # Should still process with empty metrics dict
                mock_analyzer.analyze_message_quality.assert_called_once()
                call_kwargs = mock_analyzer.analyze_message_quality.call_args.kwargs
                assert call_kwargs['metrics'] == {}

    @pytest.mark.asyncio
    async def test_process_message_json_decode_error(self, consumer):
        """Test handling of malformed JSON"""
        mock_message = AsyncMock()
        mock_message.body = b"invalid-json{{"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Should not raise (error is caught and logged)
        await consumer._on_message(mock_message)

    @pytest.mark.asyncio
    async def test_process_message_analyzer_error_triggers_requeue(self, consumer):
        """Test that analyzer errors trigger message requeue"""
        message_data = {
            "event_type": "message.created",
            "tenant_id": "tenant-123",
            "message_id": "msg-456",
            "session_id": "session-789",
            "message_type": "assistant",
            "content_preview": "AI response.",
            "timestamp": "2024-01-01T12:00:00Z"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock analyzer to raise error
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze_message_quality = AsyncMock(side_effect=Exception("Database error"))

        with patch('app.services.rabbitmq_consumer.SessionLocal'):
            with patch('app.services.rabbitmq_consumer.QualityAnalyzer', return_value=mock_analyzer):
                # Error should be raised to trigger nack+requeue
                with pytest.raises(Exception, match="Database error"):
                    await consumer._on_message(mock_message)

    @pytest.mark.asyncio
    async def test_process_message_closes_db_session(self, consumer):
        """Test that database session is always closed"""
        event = ChatMessageEvent(
            event_type="message.created",
            tenant_id="tenant-123",
            message_id="msg-456",
            session_id="session-789",
            message_type="assistant",
            content_preview="AI response.",
            timestamp="2024-01-01T12:00:00Z"
        )

        mock_db = Mock()
        mock_quality_record = Mock()
        mock_quality_record.answer_confidence = 0.9
        mock_quality_record.basic_sentiment = "positive"

        mock_analyzer = AsyncMock()
        mock_analyzer.analyze_message_quality = AsyncMock(return_value=mock_quality_record)

        with patch('app.services.rabbitmq_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.QualityAnalyzer', return_value=mock_analyzer):
                await consumer._process_message(event)

                # Verify database session was closed
                mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_closes_db_on_error(self, consumer):
        """Test that database session is closed even on error"""
        event = ChatMessageEvent(
            event_type="message.created",
            tenant_id="tenant-123",
            message_id="msg-456",
            session_id="session-789",
            message_type="assistant",
            content_preview="AI response.",
            timestamp="2024-01-01T12:00:00Z"
        )

        mock_db = Mock()
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze_message_quality = AsyncMock(side_effect=Exception("Analyzer failed"))

        with patch('app.services.rabbitmq_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.QualityAnalyzer', return_value=mock_analyzer):
                with pytest.raises(Exception, match="Analyzer failed"):
                    await consumer._process_message(event)

                # Verify database session was still closed
                mock_db.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_consuming_cancels_task(self, consumer):
        """Test that stop_consuming cancels the consume task"""
        import asyncio

        # Create real async task that can be cancelled
        async def dummy_consume():
            await asyncio.sleep(100)

        consume_task = asyncio.create_task(dummy_consume())
        consumer.consume_task = consume_task

        await consumer.stop_consuming()

        # Verify task was cancelled
        assert consume_task.cancelled()

    @pytest.mark.asyncio
    async def test_close_stops_consuming_and_closes_connection(self, consumer):
        """Test that close() stops consuming and closes connection"""
        import asyncio

        # Create mock consume task
        async def dummy_consume():
            await asyncio.sleep(100)

        consume_task = asyncio.create_task(dummy_consume())
        consumer.consume_task = consume_task

        # Create mock connection
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        consumer.connection = mock_connection

        await consumer.close()

        # Verify task was cancelled
        assert consume_task.cancelled()

        # Verify connection was closed
        mock_connection.close.assert_called_once()


# Integration tests (require live RabbitMQ - skipped by default)
@pytest.mark.skip(reason="Requires live RabbitMQ connection and database")
@pytest.mark.asyncio
async def test_rabbitmq_consumer_integration():
    """Integration test for RabbitMQConsumer with real RabbitMQ"""
    consumer = RabbitMQConsumer()

    try:
        await consumer.start_consuming()

        # Wait a bit for consumer to start
        import asyncio
        await asyncio.sleep(2)

        # Verify consumer is running
        assert consumer.consume_task is not None
        assert not consumer.consume_task.done()

    finally:
        await consumer.close()
