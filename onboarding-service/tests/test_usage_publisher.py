"""
Tests for UsageEventPublisher RabbitMQ channel validation and reconnection logic.

These tests verify the fixes for the production error:
'NoneType' object has no attribute 'basic_publish'
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pika.exceptions import AMQPConnectionError

from app.services.usage_publisher import UsageEventPublisher


class TestIsConnected:
    """Test the _is_connected() helper method"""

    def test_is_connected_returns_false_when_connection_is_none(self):
        """Test _is_connected returns False when connection is None"""
        publisher = UsageEventPublisher()
        publisher.connection = None
        publisher.channel = None

        assert publisher._is_connected() is False

    def test_is_connected_returns_false_when_channel_is_none(self):
        """Test _is_connected returns False when channel is None"""
        publisher = UsageEventPublisher()
        publisher.connection = Mock()
        publisher.connection.is_closed = False
        publisher.channel = None

        assert publisher._is_connected() is False

    def test_is_connected_returns_false_when_connection_is_closed(self):
        """Test _is_connected returns False when connection is closed"""
        publisher = UsageEventPublisher()
        publisher.connection = Mock()
        publisher.connection.is_closed = True
        publisher.channel = Mock()
        publisher.channel.is_open = True

        assert publisher._is_connected() is False

    def test_is_connected_returns_false_when_channel_is_closed(self):
        """Test _is_connected returns False when channel is closed"""
        publisher = UsageEventPublisher()
        publisher.connection = Mock()
        publisher.connection.is_closed = False
        publisher.channel = Mock()
        publisher.channel.is_open = False

        assert publisher._is_connected() is False

    def test_is_connected_returns_true_when_connection_and_channel_are_open(self):
        """Test _is_connected returns True when both connection and channel are open"""
        publisher = UsageEventPublisher()
        publisher.connection = Mock()
        publisher.connection.is_closed = False
        publisher.channel = Mock()
        publisher.channel.is_open = True

        assert publisher._is_connected() is True

    def test_is_connected_returns_false_when_checking_state_raises_exception(self):
        """Test _is_connected returns False when checking connection state throws exception"""
        publisher = UsageEventPublisher()
        publisher.connection = Mock()
        publisher.connection.is_closed = Mock(side_effect=Exception("Connection error"))
        publisher.channel = Mock()

        assert publisher._is_connected() is False


class TestForceReconnection:
    """Test the _force_reconnection() method"""

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    def test_force_reconnection_returns_true_on_success(self, mock_is_connected, mock_connect):
        """Test _force_reconnection returns True when reconnection succeeds"""
        publisher = UsageEventPublisher()

        # Setup: Old connection exists
        old_connection = Mock()
        old_connection.is_closed = False
        old_connection.close = Mock()
        publisher.connection = old_connection
        publisher.channel = Mock()

        # Mock successful reconnection
        mock_connect.return_value = None
        mock_is_connected.return_value = True

        result = publisher._force_reconnection()

        assert result is True
        mock_connect.assert_called_once()
        old_connection.close.assert_called_once()

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    def test_force_reconnection_returns_false_when_connect_fails(self, mock_is_connected, mock_connect):
        """Test _force_reconnection returns False when connect() raises exception"""
        publisher = UsageEventPublisher()

        # Setup: Old connection exists
        old_connection = Mock()
        old_connection.is_closed = False
        old_channel = Mock()
        old_channel.is_open = True
        publisher.connection = old_connection
        publisher.channel = old_channel

        # Mock failed reconnection
        mock_connect.side_effect = AMQPConnectionError("Connection failed")

        result = publisher._force_reconnection()

        assert result is False
        # Old connection should be restored
        assert publisher.connection == old_connection
        assert publisher.channel == old_channel

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    def test_force_reconnection_returns_false_when_validation_fails(self, mock_is_connected, mock_connect):
        """Test _force_reconnection returns False when connection validation fails"""
        publisher = UsageEventPublisher()

        # Setup: Old connection exists
        old_connection = Mock()
        publisher.connection = old_connection
        publisher.channel = Mock()

        # Mock connect succeeds but validation fails
        mock_connect.return_value = None
        mock_is_connected.return_value = False

        result = publisher._force_reconnection()

        assert result is False

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    def test_force_reconnection_restores_old_connection_on_failure(self, mock_is_connected, mock_connect):
        """Test _force_reconnection restores old connection if new connection fails"""
        publisher = UsageEventPublisher()

        # Setup: Valid old connection
        old_connection = Mock()
        old_connection.is_closed = False
        old_channel = Mock()
        old_channel.is_open = True
        publisher.connection = old_connection
        publisher.channel = old_channel

        # Save references to verify restoration
        saved_connection = old_connection
        saved_channel = old_channel

        # Mock failed reconnection
        mock_connect.side_effect = AMQPConnectionError("Connection failed")

        result = publisher._force_reconnection()

        assert result is False
        # Verify old connection was restored
        assert publisher.connection == saved_connection
        assert publisher.channel == saved_channel

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    def test_force_reconnection_doesnt_restore_closed_connection(self, mock_is_connected, mock_connect):
        """Test _force_reconnection doesn't restore old connection if it was closed"""
        publisher = UsageEventPublisher()

        # Setup: Old connection is closed
        old_connection = Mock()
        old_connection.is_closed = True
        old_channel = Mock()
        publisher.connection = old_connection
        publisher.channel = old_channel

        # Mock failed reconnection
        mock_connect.side_effect = AMQPConnectionError("Connection failed")

        result = publisher._force_reconnection()

        assert result is False
        # Old connection should NOT be restored (it was closed)
        assert publisher.connection is None
        assert publisher.channel is None


class TestPublishMethodsValidation:
    """Test that publish methods validate channel before use"""

    @patch('time.sleep')  # Mock sleep to speed up test
    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_publish_document_added_returns_false_when_channel_is_none(
        self, mock_force_reconnection, mock_is_connected, mock_connect, mock_sleep
    ):
        """Test publish_document_added returns False (after retries) when channel is None"""
        publisher = UsageEventPublisher()
        publisher.connection = None
        publisher.channel = None

        mock_connect.return_value = None
        mock_is_connected.return_value = False
        mock_force_reconnection.return_value = False  # Reconnection fails

        # Should return False after exhausting retries (not raise exception)
        result = publisher.publish_document_added(
            tenant_id="test-tenant",
            document_id="doc-123",
            filename="test.pdf",
            file_size=1024
        )

        assert result is False
        # Verify reconnection was attempted
        assert mock_force_reconnection.call_count >= 1

    @patch('time.sleep')  # Mock sleep to speed up test
    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_publish_document_removed_returns_false_when_channel_is_none(
        self, mock_force_reconnection, mock_is_connected, mock_connect, mock_sleep
    ):
        """Test publish_document_removed returns False (after retries) when channel is None"""
        publisher = UsageEventPublisher()
        publisher.channel = None

        mock_connect.return_value = None
        mock_is_connected.return_value = False
        mock_force_reconnection.return_value = False

        result = publisher.publish_document_removed(
            tenant_id="test-tenant",
            document_id="doc-123",
            filename="test.pdf"
        )

        assert result is False

    @patch('time.sleep')  # Mock sleep to speed up test
    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_publish_website_added_returns_false_when_channel_is_none(
        self, mock_force_reconnection, mock_is_connected, mock_connect, mock_sleep
    ):
        """Test publish_website_added returns False (after retries) when channel is None"""
        publisher = UsageEventPublisher()
        publisher.channel = None

        mock_connect.return_value = None
        mock_is_connected.return_value = False
        mock_force_reconnection.return_value = False

        result = publisher.publish_website_added(
            tenant_id="test-tenant",
            website_id="web-123",
            url="https://example.com",
            pages_scraped=10
        )

        assert result is False

    @patch('time.sleep')  # Mock sleep to speed up test
    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_publish_website_removed_returns_false_when_channel_is_none(
        self, mock_force_reconnection, mock_is_connected, mock_connect, mock_sleep
    ):
        """Test publish_website_removed returns False (after retries) when channel is None"""
        publisher = UsageEventPublisher()
        publisher.channel = None

        mock_connect.return_value = None
        mock_is_connected.return_value = False
        mock_force_reconnection.return_value = False

        result = publisher.publish_website_removed(
            tenant_id="test-tenant",
            website_id="web-123",
            url="https://example.com"
        )

        assert result is False

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    def test_publish_succeeds_when_channel_is_valid(self, mock_is_connected, mock_connect):
        """Test publish succeeds when channel is valid"""
        publisher = UsageEventPublisher()

        # Setup valid connection and channel
        mock_connection = Mock()
        mock_channel = Mock()
        mock_channel.basic_publish = Mock()

        publisher.connection = mock_connection
        publisher.channel = mock_channel

        mock_connect.return_value = None
        mock_is_connected.return_value = True

        # Should not raise exception
        result = publisher.publish_website_added(
            tenant_id="test-tenant",
            website_id="web-123",
            url="https://example.com",
            pages_scraped=10
        )

        assert result is True
        mock_channel.basic_publish.assert_called_once()


class TestRetryDecoratorWithReconnection:
    """Test the retry decorator handles reconnection failures correctly"""

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_retry_decorator_skips_publish_when_reconnection_fails(
        self, mock_force_reconnection, mock_is_connected, mock_connect
    ):
        """Test retry decorator skips publish attempt when reconnection fails"""
        publisher = UsageEventPublisher()

        # Setup initial state - channel is None
        publisher.connection = None
        publisher.channel = None

        mock_connect.return_value = None

        # First attempt: validation fails (channel is None)
        # Retry attempts: reconnection fails repeatedly
        mock_is_connected.return_value = False
        mock_force_reconnection.return_value = False

        # This should exhaust retries without calling basic_publish
        result = publisher.publish_website_added(
            tenant_id="test-tenant",
            website_id="web-123",
            url="https://example.com",
            pages_scraped=10
        )

        assert result is False
        # Reconnection should be attempted on retries
        assert mock_force_reconnection.call_count >= 1

    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_retry_decorator_succeeds_after_reconnection(
        self, mock_force_reconnection, mock_is_connected, mock_connect
    ):
        """Test retry decorator succeeds after successful reconnection"""
        publisher = UsageEventPublisher()

        # Setup mock channel
        mock_channel = Mock()
        mock_channel.basic_publish = Mock()

        # First attempt fails (channel None)
        # Second attempt succeeds (after reconnection)
        call_count = [0]

        def is_connected_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return False  # First call fails
            return True  # Subsequent calls succeed

        def force_reconnection_side_effect():
            # Simulate successful reconnection
            publisher.connection = Mock()
            publisher.connection.is_closed = False
            publisher.channel = mock_channel
            return True

        mock_connect.return_value = None
        mock_is_connected.side_effect = is_connected_side_effect
        mock_force_reconnection.side_effect = force_reconnection_side_effect

        result = publisher.publish_website_added(
            tenant_id="test-tenant",
            website_id="web-123",
            url="https://example.com",
            pages_scraped=10
        )

        assert result is True
        mock_channel.basic_publish.assert_called_once()
        mock_force_reconnection.assert_called_once()


class TestProductionScenario:
    """Test the exact production scenario that was failing"""

    @patch('time.sleep')  # Mock sleep to speed up test
    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_production_error_scenario_is_fixed(
        self, mock_force_reconnection, mock_is_connected, mock_connect, mock_sleep
    ):
        """
        Test the production error scenario is fixed:
        - RabbitMQ becomes unavailable
        - Channel becomes None
        - Publish attempt should NOT raise AttributeError
        - Instead, it should fail gracefully and return False
        """
        publisher = UsageEventPublisher()

        # Simulate production state: channel is None after connection failure
        publisher.connection = None
        publisher.channel = None

        mock_connect.return_value = None
        mock_is_connected.return_value = False
        mock_force_reconnection.return_value = False

        # In production, this raised:
        # AttributeError: 'NoneType' object has no attribute 'basic_publish'
        #
        # After fix, it should NOT raise AttributeError
        # Instead, it should return False after exhausting retries
        result = publisher.publish_website_added(
            tenant_id="69577f6f-5ba1-47ee-991a-e011be582d3e",
            website_id="26f2de09-2482-4c87-9827-d0274b5320d4",
            url="https://example.com",
            pages_scraped=78
        )

        # Should return False (not raise AttributeError)
        assert result is False
        # Verify validation was checked
        assert mock_is_connected.called
        # Verify reconnection was attempted
        assert mock_force_reconnection.called

    @patch('time.sleep')  # Mock sleep to speed up test
    @patch.object(UsageEventPublisher, 'connect')
    @patch.object(UsageEventPublisher, '_is_connected')
    @patch.object(UsageEventPublisher, '_force_reconnection')
    def test_production_scenario_with_eventual_recovery(
        self, mock_force_reconnection, mock_is_connected, mock_connect, mock_sleep
    ):
        """
        Test that the system can recover when RabbitMQ comes back online
        """
        publisher = UsageEventPublisher()

        # Setup: Channel starts as None (RabbitMQ unavailable)
        publisher.connection = None
        publisher.channel = None

        mock_connect.return_value = None

        # Track call count for _is_connected
        is_connected_call_count = [0]

        def is_connected_effect():
            is_connected_call_count[0] += 1
            # First call: initial validation fails
            if is_connected_call_count[0] == 1:
                return False
            # Subsequent calls after successful reconnection: succeed
            else:
                # Setup mock channel when connection succeeds
                if publisher.channel is None:
                    publisher.channel = Mock()
                    publisher.channel.basic_publish = Mock()
                    publisher.connection = Mock()
                    publisher.connection.is_closed = False
                return True

        def force_reconnection_effect():
            # Simulate successful reconnection on retry
            publisher.connection = Mock()
            publisher.connection.is_closed = False
            publisher.channel = Mock()
            publisher.channel.basic_publish = Mock()
            return True

        mock_is_connected.side_effect = is_connected_effect
        # First reconnection succeeds
        mock_force_reconnection.side_effect = force_reconnection_effect

        # This should eventually succeed after first retry
        result = publisher.publish_website_added(
            tenant_id="test-tenant",
            website_id="web-123",
            url="https://example.com",
            pages_scraped=10
        )

        # Should succeed after reconnection
        assert result is True
        # Verify reconnection was attempted
        assert mock_force_reconnection.called
        # Verify basic_publish was called
        assert publisher.channel.basic_publish.called
