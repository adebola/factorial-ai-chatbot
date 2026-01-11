"""
Tests for aio-pika RabbitMQ consumer in communications-service.

Tests RabbitMQConsumer to ensure the migration from pika to aio-pika
works correctly with proper async patterns, retry logic, and field mapping.
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from datetime import datetime

from app.services.rabbitmq_consumer import RabbitMQConsumer


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
        assert consumer.consume_tasks == []
        assert consumer.exchange == "communications-exchange"
        assert consumer.email_queue == "email.send"
        assert consumer.sms_queue == "sms.send"

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
            assert call_kwargs['reconnect_interval'] == 1.0
            assert call_kwargs['fail_fast'] is False

            # Verify connection is stored
            assert consumer.connection == mock_connection

    @pytest.mark.asyncio
    async def test_start_consuming_sets_up_two_queues(self, consumer):
        """Test that start_consuming() sets up both email and SMS queues"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_email_queue = AsyncMock()
        mock_sms_queue = AsyncMock()

        mock_channel.set_qos = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)

        # Mock declare_queue to return different queues
        async def mock_declare_queue(queue_name, **kwargs):
            if queue_name == "email.send":
                return mock_email_queue
            else:
                return mock_sms_queue

        mock_channel.declare_queue = mock_declare_queue
        mock_email_queue.bind = AsyncMock()
        mock_sms_queue.bind = AsyncMock()
        mock_email_queue.consume = AsyncMock()
        mock_sms_queue.consume = AsyncMock()

        mock_connection.channel = AsyncMock(return_value=mock_channel)

        with patch('app.services.rabbitmq_consumer.connect_robust', return_value=mock_connection):
            with patch('asyncio.create_task') as mock_create_task:
                await consumer.start_consuming()

                # Verify QoS was set
                mock_channel.set_qos.assert_called_once_with(prefetch_count=1)

                # Verify email queue was bound to TWO routing keys
                assert mock_email_queue.bind.call_count == 2
                email_routing_keys = [call.kwargs['routing_key'] for call in mock_email_queue.bind.call_args_list]
                assert "email.send" in email_routing_keys
                assert "email.notification" in email_routing_keys

                # Verify SMS queue was bound
                assert mock_sms_queue.bind.call_count == 1

                # Verify two consume tasks were created
                assert mock_create_task.call_count == 2

    @pytest.mark.asyncio
    async def test_process_email_message_success(self, consumer):
        """Test successful email message processing"""
        message_data = {
            "message_id": "email-123",
            "tenant_id": "tenant-456",
            "to_email": "test@example.com",
            "subject": "Test Email",
            "html_content": "<p>Hello</p>",
            "to_name": "Test User"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.headers = None
        mock_message.routing_key = "email.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock database and email service
        mock_db = MagicMock()
        mock_email_service = MagicMock()
        mock_email_service.send_email.return_value = ("msg-123", True)

        with patch.object(consumer, 'SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.EmailService', return_value=mock_email_service):
                await consumer._process_email_message(mock_message)

                # Verify email service was called
                mock_email_service.send_email.assert_called_once()
                call_kwargs = mock_email_service.send_email.call_args.kwargs
                assert call_kwargs['tenant_id'] == "tenant-456"
                assert call_kwargs['to_email'] == "test@example.com"
                assert call_kwargs['subject'] == "Test Email"

    @pytest.mark.asyncio
    async def test_process_email_with_double_encoded_json(self, consumer):
        """Test email processing with double-encoded JSON"""
        message_data = {
            "message_id": "email-123",
            "tenant_id": "tenant-456",
            "to_email": "test@example.com",
            "subject": "Test",
            "html_content": "<p>Test</p>"
        }

        # Double-encode the JSON
        double_encoded = json.dumps(json.dumps(message_data))

        mock_message = AsyncMock()
        mock_message.body = double_encoded.encode()
        mock_message.headers = None
        mock_message.routing_key = "email.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock services
        mock_db = MagicMock()
        mock_email_service = MagicMock()
        mock_email_service.send_email.return_value = ("msg-123", True)

        with patch.object(consumer, 'SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.EmailService', return_value=mock_email_service):
                await consumer._process_email_message(mock_message)

                # Should still work despite double encoding
                mock_email_service.send_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_email_with_authorization_server_format(self, consumer):
        """Test email processing with authorization server field names (camelCase)"""
        message_data = {
            "message_id": "email-123",
            "tenantId": "tenant-456",  # camelCase
            "toEmail": "test@example.com",  # camelCase
            "toName": "Test User",  # camelCase
            "subject": "Test",
            "htmlContent": "<p>Test</p>",  # camelCase
            "textContent": "Test"  # camelCase
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.headers = None
        mock_message.routing_key = "email.notification"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock services
        mock_db = MagicMock()
        mock_email_service = MagicMock()
        mock_email_service.send_email.return_value = ("msg-123", True)

        with patch.object(consumer, 'SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.EmailService', return_value=mock_email_service):
                await consumer._process_email_message(mock_message)

                # Verify field mapping worked
                call_kwargs = mock_email_service.send_email.call_args.kwargs
                assert call_kwargs['tenant_id'] == "tenant-456"
                assert call_kwargs['to_email'] == "test@example.com"
                assert call_kwargs['to_name'] == "Test User"
                assert call_kwargs['html_content'] == "<p>Test</p>"

    @pytest.mark.asyncio
    async def test_process_email_retry_on_failure(self, consumer):
        """Test that failed email triggers retry with incremented count"""
        message_data = {
            "message_id": "email-123",
            "tenant_id": "tenant-456",
            "to_email": "test@example.com",
            "subject": "Test"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.headers = {'x-retry-count': 0}
        mock_message.routing_key = "email.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock services - email send fails
        mock_db = MagicMock()
        mock_email_service = MagicMock()
        mock_email_service.send_email.return_value = ("msg-123", False)  # Failure

        with patch.object(consumer, 'SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.EmailService', return_value=mock_email_service):
                with patch.object(consumer, '_republish_with_retry', new_callable=AsyncMock) as mock_republish:
                    await consumer._process_email_message(mock_message)

                    # Verify republish was called with incremented retry count
                    mock_republish.assert_called_once_with(mock_message, 1)

    @pytest.mark.asyncio
    async def test_process_email_max_retries_exceeded(self, consumer):
        """Test that message is discarded after max retries"""
        message_data = {
            "message_id": "email-123",
            "tenant_id": "tenant-456",
            "to_email": "test@example.com",
            "subject": "Test"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.headers = {'x-retry-count': 3}  # Already at max
        mock_message.routing_key = "email.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock services
        mock_db = MagicMock()

        with patch.object(consumer, 'SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.EmailService') as mock_email_service_class:
                await consumer._process_email_message(mock_message)

                # Email service should NOT be called (message discarded)
                mock_email_service_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_email_missing_required_field(self, consumer):
        """Test email processing with missing required field"""
        message_data = {
            "message_id": "email-123",
            "tenant_id": "tenant-456"
            # Missing to_email and subject
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.headers = None
        mock_message.routing_key = "email.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Should not raise (error is caught)
        await consumer._process_email_message(mock_message)

    @pytest.mark.asyncio
    async def test_process_email_json_decode_error(self, consumer):
        """Test handling of malformed JSON in email message"""
        mock_message = AsyncMock()
        mock_message.body = b"invalid-json{{"
        mock_message.headers = None
        mock_message.routing_key = "email.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Should not raise (error is caught and logged)
        await consumer._process_email_message(mock_message)

    @pytest.mark.asyncio
    async def test_process_sms_message_success(self, consumer):
        """Test successful SMS message processing"""
        message_data = {
            "message_id": "sms-123",
            "tenant_id": "tenant-456",
            "to_phone": "+1234567890",
            "message": "Test SMS"
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.headers = None
        mock_message.routing_key = "sms.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock services
        mock_db = MagicMock()
        mock_sms_service = MagicMock()
        mock_sms_service.send_sms.return_value = ("msg-123", True)

        with patch.object(consumer, 'SessionLocal', return_value=mock_db):
            with patch('app.services.rabbitmq_consumer.SMSService', return_value=mock_sms_service):
                await consumer._process_sms_message(mock_message)

                # Verify SMS service was called
                mock_sms_service.send_sms.assert_called_once()
                call_kwargs = mock_sms_service.send_sms.call_args.kwargs
                assert call_kwargs['tenant_id'] == "tenant-456"
                assert call_kwargs['to_phone'] == "+1234567890"
                assert call_kwargs['message'] == "Test SMS"

    @pytest.mark.asyncio
    async def test_process_sms_missing_required_field(self, consumer):
        """Test SMS processing with missing required field"""
        message_data = {
            "message_id": "sms-123",
            "tenant_id": "tenant-456"
            # Missing to_phone and message
        }

        mock_message = AsyncMock()
        mock_message.body = json.dumps(message_data).encode()
        mock_message.headers = None
        mock_message.routing_key = "sms.send"

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Should not raise (error is caught)
        await consumer._process_sms_message(mock_message)

    @pytest.mark.asyncio
    async def test_stop_consuming_cancels_tasks(self, consumer):
        """Test that stop_consuming cancels both email and SMS tasks"""
        import asyncio

        # Create real async tasks that can be cancelled
        async def dummy_consume():
            await asyncio.sleep(100)

        email_task = asyncio.create_task(dummy_consume())
        sms_task = asyncio.create_task(dummy_consume())
        consumer.consume_tasks = [email_task, sms_task]

        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        consumer.connection = mock_connection

        await consumer.stop_consuming()

        # Verify both tasks were cancelled
        assert email_task.cancelled()
        assert sms_task.cancelled()

        # Verify connection was closed
        mock_connection.close.assert_called_once()


# Integration tests (require live RabbitMQ - skipped by default)
@pytest.mark.skip(reason="Requires live RabbitMQ connection and database")
@pytest.mark.asyncio
async def test_rabbitmq_consumer_integration():
    """Integration test for RabbitMQConsumer with real RabbitMQ"""
    consumer = RabbitMQConsumer()

    try:
        await consumer.connect()
        await consumer.start_consuming()

        # Wait a bit for consumers to start
        import asyncio
        await asyncio.sleep(2)

        # Verify consumers are running
        assert len(consumer.consume_tasks) == 2
        assert all(not task.done() for task in consumer.consume_tasks)

    finally:
        await consumer.stop_consuming()
