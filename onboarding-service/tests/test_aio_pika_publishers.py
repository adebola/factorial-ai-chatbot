"""
Tests for aio-pika publishers in onboarding-service.

Tests both usage_publisher.py and rabbitmq_service.py to ensure
the migration from pika to aio-pika works correctly.
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch

from app.services.usage_publisher import UsageEventPublisher
from app.services.rabbitmq_service import RabbitMQService


class TestUsageEventPublisher:
    """Test suite for UsageEventPublisher (aio-pika)"""

    @pytest.fixture
    def publisher(self):
        """Create UsageEventPublisher instance for testing"""
        return UsageEventPublisher()

    @pytest.mark.asyncio
    async def test_initialization(self, publisher):
        """Test that UsageEventPublisher initializes correctly"""
        assert publisher.connection is None
        assert publisher.rabbitmq_host == "localhost"
        assert publisher.rabbitmq_port == 5672
        assert publisher.usage_exchange == "usage.events"

    @pytest.mark.asyncio
    async def test_connect_creates_robust_connection(self, publisher):
        """Test that connect() creates a robust connection"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False

        with patch('app.services.usage_publisher.connect_robust', return_value=mock_connection) as mock_connect:
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
    async def test_publish_document_added_success(self, publisher):
        """Test publishing document added event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.usage_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_document_added(
                tenant_id="tenant-123",
                document_id="doc-456",
                filename="test.pdf",
                file_size=1024
            )

            # Verify result
            assert result is True

            # Verify exchange.publish was called
            mock_exchange.publish.assert_called_once()
            call_args = mock_exchange.publish.call_args

            # Verify routing key
            assert call_args.kwargs['routing_key'] == 'usage.document.added'

    @pytest.mark.asyncio
    async def test_publish_document_removed_success(self, publisher):
        """Test publishing document removed event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.usage_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_document_removed(
                tenant_id="tenant-123",
                document_id="doc-456",
                filename="test.pdf"
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'usage.document.removed'

    @pytest.mark.asyncio
    async def test_publish_website_added_success(self, publisher):
        """Test publishing website added event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.usage_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_website_added(
                tenant_id="tenant-123",
                website_id="web-456",
                url="https://example.com",
                pages_scraped=10
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'usage.website.added'

    @pytest.mark.asyncio
    async def test_publish_website_removed_success(self, publisher):
        """Test publishing website removed event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.usage_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_website_removed(
                tenant_id="tenant-123",
                website_id="web-456",
                url="https://example.com"
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'usage.website.removed'

    @pytest.mark.asyncio
    async def test_publish_handles_exceptions(self, publisher):
        """Test that publish methods handle exceptions gracefully"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_connection.channel.side_effect = Exception("Channel error")

        with patch('app.services.usage_publisher.connect_robust', return_value=mock_connection):
            result = await publisher.publish_document_added(
                tenant_id="tenant-123",
                document_id="doc-456",
                filename="test.pdf",
                file_size=1024
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


class TestRabbitMQService:
    """Test suite for RabbitMQService (aio-pika)"""

    @pytest.fixture
    def service(self):
        """Create RabbitMQService instance for testing"""
        return RabbitMQService()

    @pytest.mark.asyncio
    async def test_initialization(self, service):
        """Test that RabbitMQService initializes correctly"""
        assert service.connection is None
        assert service.host == "localhost"
        assert service.port == 5672
        assert service.exchange == "topic-exchange"
        assert service.plan_update_routing_key == "plan.update"
        assert service.logo_update_routing_key == "logo.update"

    @pytest.mark.asyncio
    async def test_publish_plan_update_success(self, service):
        """Test publishing plan update message"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.rabbitmq_service.connect_robust', return_value=mock_connection):
            result = await service.publish_plan_update(
                tenant_id="tenant-123",
                plan_id="plan-789",
                action="subscription_created"
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'plan.update'

    @pytest.mark.asyncio
    async def test_publish_plan_switch_success(self, service):
        """Test publishing plan switch message"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.rabbitmq_service.connect_robust', return_value=mock_connection):
            result = await service.publish_plan_switch(
                tenant_id="tenant-123",
                old_plan_id="plan-old",
                new_plan_id="plan-new"
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_logo_uploaded_success(self, service):
        """Test publishing logo uploaded event"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_channel.declare_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.__aenter__ = AsyncMock(return_value=mock_channel)
        mock_channel.__aexit__ = AsyncMock(return_value=None)
        mock_connection.channel = Mock(return_value=mock_channel)

        with patch('app.services.rabbitmq_service.connect_robust', return_value=mock_connection):
            result = await service.publish_logo_uploaded(
                tenant_id="tenant-123",
                logo_url="https://example.com/logo.png"
            )

            assert result is True
            mock_exchange.publish.assert_called_once()

            # Verify routing key
            call_args = mock_exchange.publish.call_args
            assert call_args.kwargs['routing_key'] == 'logo.update'

    @pytest.mark.asyncio
    async def test_health_check_success(self, service):
        """Test health check when connection successful"""
        mock_connection = AsyncMock()
        mock_connection.is_closed = False

        with patch('app.services.rabbitmq_service.connect_robust', return_value=mock_connection):
            result = await service.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, service):
        """Test health check when connection fails"""
        with patch('app.services.rabbitmq_service.connect_robust', side_effect=Exception("Connection failed")):
            result = await service.health_check()

            assert result is False


# Integration tests (require live RabbitMQ - skipped by default)
@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_usage_publisher_integration():
    """Integration test for UsageEventPublisher with real RabbitMQ"""
    publisher = UsageEventPublisher()

    try:
        await publisher.connect()

        result = await publisher.publish_document_added(
            tenant_id="test-tenant",
            document_id="test-doc",
            filename="test.pdf",
            file_size=1024
        )

        assert result is True

    finally:
        await publisher.close()


@pytest.mark.skip(reason="Requires live RabbitMQ connection")
@pytest.mark.asyncio
async def test_rabbitmq_service_integration():
    """Integration test for RabbitMQService with real RabbitMQ"""
    service = RabbitMQService()

    try:
        await service.connect()

        result = await service.publish_plan_update(
            tenant_id="test-tenant",
            plan_id="test-plan"
        )

        assert result is True

    finally:
        await service.close()