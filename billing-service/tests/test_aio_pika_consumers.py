"""
Tests for aio-pika consumers in billing-service.

Tests both UsageEventConsumer and UserEventConsumer to ensure the migration
from pika to aio-pika works correctly with proper async patterns.
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone

from app.services.usage_consumer import UsageEventConsumer
from app.messaging.user_consumer import UserEventConsumer


class TestUsageEventConsumer:
    """Test suite for UsageEventConsumer (aio-pika)"""

    @pytest.fixture
    def consumer(self):
        """Create UsageEventConsumer instance for testing"""
        return UsageEventConsumer()

    @pytest.mark.asyncio
    async def test_initialization(self, consumer):
        """Test that UsageEventConsumer initializes correctly"""
        assert consumer.connection is None
        assert consumer.consume_task is None
        assert consumer.processed_event_ids == set()
        assert consumer.max_tracked_events == 10000

    @pytest.mark.asyncio
    async def test_connect_creates_robust_connection(self, consumer):
        """Test that connect() creates a robust connection"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False

        with patch('app.services.usage_consumer.connect_robust', return_value=mock_connection) as mock_connect:
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

        with patch('app.services.usage_consumer.connect_robust') as mock_connect:
            await consumer.connect()

            # Should not call connect_robust if already connected
            mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_consuming_sets_up_queue(self, consumer):
        """Test that start_consuming() sets up queue and consumer correctly"""
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

        with patch('app.services.usage_consumer.connect_robust', return_value=mock_connection):
            with patch('asyncio.create_task') as mock_create_task:
                await consumer.start_consuming()

                # Verify QoS was set
                mock_channel.set_qos.assert_called_once_with(prefetch_count=1)

                # Verify exchange was declared
                mock_channel.declare_exchange.assert_called_once()

                # Verify queue was declared and bound
                mock_channel.declare_queue.assert_called_once()
                mock_queue.bind.assert_called_once()

                # Verify consume task was created
                mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_document_created_event(self, consumer):
        """Test processing usage.document.created event"""
        event_data = {
            "event_id": "evt-123",
            "tenant_id": "tenant-456",
            "document_id": "doc-789",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Mock database and services
        mock_db = MagicMock()
        mock_subscription = MagicMock()
        mock_subscription.id = "sub-123"
        mock_usage = MagicMock()
        mock_usage.documents_used = 5
        mock_usage.websites_used = 2
        mock_usage.daily_chats_used = 10
        mock_usage.monthly_chats_used = 100

        mock_subscription_service = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = mock_subscription

        with patch('app.services.usage_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.usage_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch.object(mock_db, 'query') as mock_query:
                    mock_query.return_value.filter.return_value.first.return_value = mock_usage

                    result = await consumer._process_event("usage.document.created", event_data)

                    assert result is True
                    # Verify documents_used was incremented
                    assert mock_usage.documents_used == 6

    @pytest.mark.asyncio
    async def test_process_document_deleted_event(self, consumer):
        """Test processing usage.document.deleted event"""
        event_data = {
            "event_id": "evt-123",
            "tenant_id": "tenant-456",
            "document_id": "doc-789"
        }

        mock_db = MagicMock()
        mock_subscription = MagicMock()
        mock_subscription.id = "sub-123"
        mock_usage = MagicMock()
        mock_usage.documents_used = 5

        mock_subscription_service = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = mock_subscription

        with patch('app.services.usage_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.usage_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch.object(mock_db, 'query') as mock_query:
                    mock_query.return_value.filter.return_value.first.return_value = mock_usage

                    result = await consumer._process_event("usage.document.deleted", event_data)

                    assert result is True
                    # Verify documents_used was decremented
                    assert mock_usage.documents_used == 4

    @pytest.mark.asyncio
    async def test_process_document_deleted_protects_zero(self, consumer):
        """Test that document deletion doesn't go below zero"""
        event_data = {
            "event_id": "evt-123",
            "tenant_id": "tenant-456",
            "document_id": "doc-789"
        }

        mock_db = MagicMock()
        mock_subscription = MagicMock()
        mock_subscription.id = "sub-123"
        mock_usage = MagicMock()
        mock_usage.documents_used = 0  # Already at zero

        mock_subscription_service = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = mock_subscription

        with patch('app.services.usage_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.usage_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch.object(mock_db, 'query') as mock_query:
                    mock_query.return_value.filter.return_value.first.return_value = mock_usage

                    result = await consumer._process_event("usage.document.deleted", event_data)

                    assert result is True
                    # Verify it stayed at zero
                    assert mock_usage.documents_used == 0

    @pytest.mark.asyncio
    async def test_process_website_created_event(self, consumer):
        """Test processing usage.website.created event"""
        event_data = {
            "event_id": "evt-123",
            "tenant_id": "tenant-456",
            "website_id": "web-789"
        }

        mock_db = MagicMock()
        mock_subscription = MagicMock()
        mock_subscription.id = "sub-123"
        mock_usage = MagicMock()
        mock_usage.websites_used = 3

        mock_subscription_service = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = mock_subscription

        with patch('app.services.usage_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.usage_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch.object(mock_db, 'query') as mock_query:
                    mock_query.return_value.filter.return_value.first.return_value = mock_usage

                    result = await consumer._process_event("usage.website.created", event_data)

                    assert result is True
                    assert mock_usage.websites_used == 4

    @pytest.mark.asyncio
    async def test_process_chat_message_event(self, consumer):
        """Test processing usage.chat.message event"""
        event_data = {
            "event_id": "evt-123",
            "tenant_id": "tenant-456",
            "message_count": 2
        }

        mock_db = MagicMock()
        mock_subscription = MagicMock()
        mock_subscription.id = "sub-123"
        mock_usage = MagicMock()
        mock_usage.daily_chats_used = 10
        mock_usage.monthly_chats_used = 100
        mock_usage.daily_reset_at = datetime.now(timezone.utc) + timedelta(days=1)
        mock_usage.monthly_reset_at = datetime.now(timezone.utc) + timedelta(days=30)

        mock_subscription_service = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = mock_subscription

        with patch('app.services.usage_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.usage_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch.object(mock_db, 'query') as mock_query:
                    mock_query.return_value.filter.return_value.first.return_value = mock_usage
                    with patch.object(consumer, '_check_and_publish_limit_warning', new_callable=AsyncMock):
                        result = await consumer._process_event("usage.chat.message", event_data)

                        assert result is True
                        assert mock_usage.daily_chats_used == 12
                        assert mock_usage.monthly_chats_used == 102

    @pytest.mark.asyncio
    async def test_idempotency_check_skips_duplicate(self, consumer):
        """Test that duplicate event IDs are skipped"""
        # Add event ID to processed set
        consumer.processed_event_ids.add("evt-duplicate")

        mock_message = AsyncMock()
        mock_message.body = json.dumps({
            "event_id": "evt-duplicate",
            "tenant_id": "tenant-123"
        }).encode()
        mock_message.routing_key = "usage.document.created"

        # Create a proper async context manager mock
        from unittest.mock import MagicMock
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        with patch.object(consumer, '_process_event', new_callable=AsyncMock) as mock_process:
            await consumer._on_message(mock_message)

            # Should not have called _process_event
            mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotency_memory_management(self, consumer):
        """Test that processed event IDs are pruned when exceeding max"""
        # Add more than max_tracked_events
        for i in range(consumer.max_tracked_events + 100):
            consumer.processed_event_ids.add(f"evt-{i}")

        # Create a new message that will be processed successfully
        mock_message = AsyncMock()
        mock_message.body = json.dumps({
            "event_id": "evt-new",
            "tenant_id": "tenant-456"
        }).encode()
        mock_message.routing_key = "usage.document.created"

        # Create async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        # Mock _process_event to return success
        with patch.object(consumer, '_process_event', new_callable=AsyncMock) as mock_process:
            mock_process.return_value = True

            await consumer._on_message(mock_message)

            # Verify set was pruned to max_tracked_events
            assert len(consumer.processed_event_ids) <= consumer.max_tracked_events

    @pytest.mark.asyncio
    async def test_handles_missing_tenant_id(self, consumer):
        """Test handling of event without tenant_id"""
        event_data = {
            "event_id": "evt-123"
            # Missing tenant_id
        }

        result = await consumer._process_event("usage.document.created", event_data)
        assert result is False

    @pytest.mark.asyncio
    async def test_handles_unknown_event_type(self, consumer):
        """Test handling of unknown event type"""
        event_data = {
            "event_id": "evt-123",
            "tenant_id": "tenant-456"
        }

        mock_db = MagicMock()
        mock_subscription = MagicMock()
        mock_usage = MagicMock()

        mock_subscription_service = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = mock_subscription

        with patch('app.services.usage_consumer.SessionLocal', return_value=mock_db):
            with patch('app.services.usage_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch.object(mock_db, 'query') as mock_query:
                    mock_query.return_value.filter.return_value.first.return_value = mock_usage

                    result = await consumer._process_event("usage.unknown.type", event_data)

                    # Should acknowledge unknown events
                    assert result is True

    @pytest.mark.asyncio
    async def test_stop_consuming_cancels_task(self, consumer):
        """Test that stop_consuming cancels the consume task"""
        import asyncio

        # Create a real async task that can be cancelled
        async def dummy_consume():
            await asyncio.sleep(100)

        mock_task = asyncio.create_task(dummy_consume())
        consumer.consume_task = mock_task

        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        consumer.connection = mock_connection

        await consumer.stop_consuming()

        # Verify task was cancelled
        assert mock_task.cancelled()

        # Verify connection was closed
        mock_connection.close.assert_called_once()


class TestUserEventConsumer:
    """Test suite for UserEventConsumer (aio-pika)"""

    @pytest.fixture
    def consumer(self):
        """Create UserEventConsumer instance for testing"""
        return UserEventConsumer()

    @pytest.mark.asyncio
    async def test_initialization(self, consumer):
        """Test that UserEventConsumer initializes correctly"""
        assert consumer.connection is None
        assert consumer.consume_task is None
        assert consumer.exchange_name == "billing.events"
        assert consumer.queue_name == "billing.user.events"
        assert consumer.routing_key == "user.created"

    @pytest.mark.asyncio
    async def test_connect_creates_robust_connection(self, consumer):
        """Test that connect() creates a robust connection"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False

        with patch('app.messaging.user_consumer.connect_robust', return_value=mock_connection) as mock_connect:
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
    async def test_handle_user_created_success(self, consumer):
        """Test successful handling of user.created event"""
        message_data = {
            "tenant_id": "tenant-123",
            "created_at": "2024-01-15T10:30:00Z"
        }

        # Mock database and services
        mock_db = MagicMock()
        mock_subscription_service = MagicMock()
        mock_plan_service = MagicMock()

        # No existing subscription (idempotency check passes)
        mock_subscription_service.get_subscription_by_tenant.return_value = None

        # Mock Basic plan
        mock_basic_plan = MagicMock()
        mock_basic_plan.id = "plan-basic"
        mock_basic_plan.name = "Basic"
        mock_basic_plan.is_active = True
        mock_plan_service.get_plan_by_name.return_value = mock_basic_plan

        # Mock created subscription
        mock_subscription = MagicMock()
        mock_subscription.id = "sub-123"
        mock_subscription.status = "trialing"
        mock_subscription_service.create_subscription.return_value = mock_subscription

        with patch('app.messaging.user_consumer.get_db') as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            with patch('app.messaging.user_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch('app.messaging.user_consumer.PlanService', return_value=mock_plan_service):
                    with patch('app.messaging.user_consumer.rabbitmq_service') as mock_rabbitmq:
                        mock_rabbitmq.publish_plan_update = AsyncMock(return_value=True)

                        result = await consumer.handle_user_created(message_data)

                        assert result is True

                        # Verify Basic plan was fetched
                        mock_plan_service.get_plan_by_name.assert_called_once_with("Basic")

                        # Verify subscription was created
                        mock_subscription_service.create_subscription.assert_called_once()
                        call_kwargs = mock_subscription_service.create_subscription.call_args.kwargs
                        assert call_kwargs['tenant_id'] == "tenant-123"
                        assert call_kwargs['plan_id'] == "plan-basic"
                        assert call_kwargs['start_trial'] is False
                        assert 'custom_trial_end' in call_kwargs

                        # Verify RabbitMQ event was published
                        mock_rabbitmq.publish_plan_update.assert_called_once_with(
                            tenant_id="tenant-123",
                            subscription_id="sub-123",
                            plan_id="plan-basic",
                            action="subscription_created"
                        )

    @pytest.mark.asyncio
    async def test_handle_user_created_idempotency(self, consumer):
        """Test that duplicate user.created events are skipped"""
        message_data = {
            "tenant_id": "tenant-123",
            "created_at": "2024-01-15T10:30:00Z"
        }

        mock_db = MagicMock()
        mock_subscription_service = MagicMock()

        # Existing subscription found (idempotency check)
        mock_existing_subscription = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = mock_existing_subscription

        with patch('app.messaging.user_consumer.get_db') as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            with patch('app.messaging.user_consumer.SubscriptionService', return_value=mock_subscription_service):
                result = await consumer.handle_user_created(message_data)

                assert result is True

                # Verify create_subscription was NOT called
                mock_subscription_service.create_subscription.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_user_created_missing_tenant_id(self, consumer):
        """Test handling of message without tenant_id"""
        message_data = {
            "created_at": "2024-01-15T10:30:00Z"
            # Missing tenant_id
        }

        result = await consumer.handle_user_created(message_data)
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_user_created_missing_created_at(self, consumer):
        """Test handling of message without created_at"""
        message_data = {
            "tenant_id": "tenant-123"
            # Missing created_at
        }

        result = await consumer.handle_user_created(message_data)
        assert result is False

    @pytest.mark.asyncio
    async def test_handle_user_created_invalid_date_format(self, consumer):
        """Test handling of invalid created_at date format"""
        message_data = {
            "tenant_id": "tenant-123",
            "created_at": "invalid-date-format"
        }

        mock_db = MagicMock()
        mock_subscription_service = MagicMock()
        mock_subscription_service.get_subscription_by_tenant.return_value = None

        with patch('app.messaging.user_consumer.get_db') as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            with patch('app.messaging.user_consumer.SubscriptionService', return_value=mock_subscription_service):
                result = await consumer.handle_user_created(message_data)

                assert result is False

    @pytest.mark.asyncio
    async def test_handle_user_created_basic_plan_not_found(self, consumer):
        """Test handling when Basic plan doesn't exist"""
        message_data = {
            "tenant_id": "tenant-123",
            "created_at": "2024-01-15T10:30:00Z"
        }

        mock_db = MagicMock()
        mock_subscription_service = MagicMock()
        mock_plan_service = MagicMock()

        mock_subscription_service.get_subscription_by_tenant.return_value = None
        mock_plan_service.get_plan_by_name.return_value = None  # No Basic plan

        with patch('app.messaging.user_consumer.get_db') as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            with patch('app.messaging.user_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch('app.messaging.user_consumer.PlanService', return_value=mock_plan_service):
                    result = await consumer.handle_user_created(message_data)

                    assert result is False

    @pytest.mark.asyncio
    async def test_handle_user_created_basic_plan_inactive(self, consumer):
        """Test handling when Basic plan is inactive"""
        message_data = {
            "tenant_id": "tenant-123",
            "created_at": "2024-01-15T10:30:00Z"
        }

        mock_db = MagicMock()
        mock_subscription_service = MagicMock()
        mock_plan_service = MagicMock()

        mock_subscription_service.get_subscription_by_tenant.return_value = None

        mock_basic_plan = MagicMock()
        mock_basic_plan.is_active = False  # Inactive plan
        mock_plan_service.get_plan_by_name.return_value = mock_basic_plan

        with patch('app.messaging.user_consumer.get_db') as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            with patch('app.messaging.user_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch('app.messaging.user_consumer.PlanService', return_value=mock_plan_service):
                    result = await consumer.handle_user_created(message_data)

                    assert result is False

    @pytest.mark.asyncio
    async def test_handle_user_created_rabbitmq_publish_fails(self, consumer):
        """Test that subscription creation succeeds even if RabbitMQ publish fails"""
        message_data = {
            "tenant_id": "tenant-123",
            "created_at": "2024-01-15T10:30:00Z"
        }

        mock_db = MagicMock()
        mock_subscription_service = MagicMock()
        mock_plan_service = MagicMock()

        mock_subscription_service.get_subscription_by_tenant.return_value = None

        mock_basic_plan = MagicMock()
        mock_basic_plan.id = "plan-basic"
        mock_basic_plan.name = "Basic"
        mock_basic_plan.is_active = True
        mock_plan_service.get_plan_by_name.return_value = mock_basic_plan

        mock_subscription = MagicMock()
        mock_subscription.id = "sub-123"
        mock_subscription_service.create_subscription.return_value = mock_subscription

        with patch('app.messaging.user_consumer.get_db') as mock_get_db:
            mock_get_db.return_value = iter([mock_db])

            with patch('app.messaging.user_consumer.SubscriptionService', return_value=mock_subscription_service):
                with patch('app.messaging.user_consumer.PlanService', return_value=mock_plan_service):
                    with patch('app.messaging.user_consumer.rabbitmq_service') as mock_rabbitmq:
                        # RabbitMQ publish fails
                        mock_rabbitmq.publish_plan_update = AsyncMock(side_effect=Exception("RabbitMQ error"))

                        result = await consumer.handle_user_created(message_data)

                        # Should still return True (subscription was created)
                        assert result is True

    @pytest.mark.asyncio
    async def test_on_message_handles_double_encoded_json(self, consumer):
        """Test handling of double-encoded JSON messages"""
        # Create a double-encoded JSON message
        inner_data = {
            "tenant_id": "tenant-123",
            "created_at": "2024-01-15T10:30:00Z"
        }
        outer_json = json.dumps(json.dumps(inner_data))

        mock_message = AsyncMock()
        mock_message.body = outer_json.encode()

        # Create proper async context manager
        class AsyncContextManagerMock:
            async def __aenter__(self):
                return None
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_message.process = MagicMock(return_value=AsyncContextManagerMock())

        with patch.object(consumer, 'handle_user_created', new_callable=AsyncMock) as mock_handle:
            mock_handle.return_value = True

            await consumer._on_message(mock_message)

            # Verify handle_user_created was called with decoded data
            mock_handle.assert_called_once()
            call_args = mock_handle.call_args[0][0]
            assert call_args['tenant_id'] == "tenant-123"
            assert call_args['created_at'] == "2024-01-15T10:30:00Z"

    @pytest.mark.asyncio
    async def test_on_message_handles_json_decode_error(self, consumer):
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

        # Should not raise (error is caught)
        await consumer._on_message(mock_message)

    @pytest.mark.asyncio
    async def test_stop_consuming(self, consumer):
        """Test stopping the consumer"""
        import asyncio

        # Create a real async task that can be cancelled
        async def dummy_consume():
            await asyncio.sleep(100)

        mock_task = asyncio.create_task(dummy_consume())
        consumer.consume_task = mock_task

        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        consumer.connection = mock_connection

        await consumer.stop_consuming()

        # Verify task was cancelled
        assert mock_task.cancelled()

        # Verify connection was closed
        mock_connection.close.assert_called_once()


# Integration tests (require live RabbitMQ - skipped by default)
@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_usage_consumer_integration():
    """Integration test for UsageEventConsumer with real RabbitMQ"""
    consumer = UsageEventConsumer()

    try:
        await consumer.connect()
        await consumer.start_consuming()

        # Wait a bit for consumer to start
        import asyncio
        await asyncio.sleep(2)

        # Verify consumer is running
        assert consumer.consume_task is not None
        assert not consumer.consume_task.done()

    finally:
        await consumer.stop_consuming()


@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_user_consumer_integration():
    """Integration test for UserEventConsumer with real RabbitMQ"""
    consumer = UserEventConsumer()

    try:
        await consumer.connect()
        await consumer.start_consuming()

        # Wait a bit for consumer to start
        import asyncio
        await asyncio.sleep(2)

        # Verify consumer is running
        assert consumer.consume_task is not None
        assert not consumer.consume_task.done()

    finally:
        await consumer.stop_consuming()
