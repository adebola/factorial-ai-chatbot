"""
Unit tests for logo URL construction and permanent URL functionality.

Tests verify that:
1. Logo URLs use public endpoint format (not presigned MinIO URLs)
2. URLs use BACKEND_URL environment variable
3. URLs don't contain MinIO hostname or presigned URL parameters
4. Proper fallback to localhost when BACKEND_URL not set
"""

import os
import pytest
from unittest.mock import Mock, patch
from fastapi import UploadFile
from io import BytesIO

from app.services.settings_service import SettingsService


class TestPublicLogoURLConstruction:
    """Test the _construct_public_logo_url() helper method"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()

    @patch('app.services.settings_service.StorageService')
    def test_construct_public_logo_url_uses_backend_url(self, mock_storage_class):
        """Test that public logo URL uses BACKEND_URL environment variable"""
        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com"}):
            service = SettingsService(self.mock_db)
            url = service._construct_public_logo_url("tenant-123")

            assert url == "https://api.example.com/api/v1/settings-logo/tenant-123"
            assert "minio" not in url  # Should NOT contain MinIO hostname
            assert "X-Amz" not in url  # Should NOT contain presigned URL parameters

    @patch('app.services.settings_service.StorageService')
    def test_construct_public_logo_url_removes_trailing_slash(self, mock_storage_class):
        """Test that trailing slash in BACKEND_URL is properly handled"""
        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com/"}):
            service = SettingsService(self.mock_db)
            url = service._construct_public_logo_url("tenant-123")

            # Should not have double slash before /api
            assert url == "https://api.example.com/api/v1/settings-logo/tenant-123"
            assert "//" not in url.replace("https://", "")

    @patch('app.services.settings_service.StorageService')
    def test_construct_public_logo_url_defaults_to_localhost(self, mock_storage_class):
        """Test fallback to localhost when BACKEND_URL not set"""
        # Ensure BACKEND_URL is not in environment
        env_copy = os.environ.copy()
        if "BACKEND_URL" in env_copy:
            del env_copy["BACKEND_URL"]

        with patch.dict(os.environ, env_copy, clear=True):
            service = SettingsService(self.mock_db)
            url = service._construct_public_logo_url("tenant-123")

            assert url.startswith("http://localhost:8001")
            assert url == "http://localhost:8001/api/v1/settings-logo/tenant-123"

    @patch('app.services.settings_service.StorageService')
    @patch('logging.getLogger')
    def test_construct_public_logo_url_logs_warning_when_not_set(self, mock_logger, mock_storage_class):
        """Test that warning is logged when BACKEND_URL is not set"""
        env_copy = os.environ.copy()
        if "BACKEND_URL" in env_copy:
            del env_copy["BACKEND_URL"]

        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance

        with patch.dict(os.environ, env_copy, clear=True):
            service = SettingsService(self.mock_db)
            service._construct_public_logo_url("tenant-123")

            # Should log a warning about missing BACKEND_URL
            assert mock_logger_instance.warning.called

    @patch('app.services.settings_service.StorageService')
    def test_construct_public_logo_url_with_different_ports(self, mock_storage_class):
        """Test URL construction with different port configurations"""
        test_cases = [
            ("http://localhost:8001", "http://localhost:8001/api/v1/settings-logo/tenant-123"),
            ("https://api.chatcraft.cc", "https://api.chatcraft.cc/api/v1/settings-logo/tenant-123"),
            ("http://staging.example.com:3000", "http://staging.example.com:3000/api/v1/settings-logo/tenant-123"),
        ]

        for backend_url, expected_url in test_cases:
            with patch.dict(os.environ, {"BACKEND_URL": backend_url}):
                service = SettingsService(self.mock_db)
                url = service._construct_public_logo_url("tenant-123")
                assert url == expected_url


class TestLogoUploadReturnValue:
    """Test that logo upload returns permanent public URL"""

    def setup_method(self):
        """Setup test fixtures"""
        self.mock_db = Mock()

    @patch('app.services.settings_service.StorageService')
    @patch('app.services.rabbitmq_service.rabbitmq_service')
    def test_upload_company_logo_returns_public_url_not_presigned(self, mock_rabbitmq, mock_storage_class):
        """Test that upload returns permanent public URL, not presigned URL"""
        # Mock storage service
        mock_storage = Mock()
        mock_storage.upload_logo_file.return_value = (
            "tenant_123/logos/logo.png",
            "http://minio:9000/temp-url"
        )
        mock_storage.delete_file.return_value = True
        mock_storage_class.return_value = mock_storage

        # Mock environment
        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com"}):
            service = SettingsService(self.mock_db)

            # Create mock file
            mock_file = Mock(spec=UploadFile)
            mock_file.filename = "logo.png"
            mock_file.content_type = "image/png"
            mock_file.file = BytesIO(b"fake image data")

            result = service.upload_company_logo("tenant-123", mock_file)

            # Assertions
            # Should NOT contain MinIO hostname
            assert "minio" not in result

            # Should NOT contain presigned URL parameters
            assert "X-Amz-Algorithm" not in result
            assert "X-Amz-Credential" not in result
            assert "X-Amz-Date" not in result
            assert "X-Amz-Expires" not in result
            assert "X-Amz-Signature" not in result

            # Should contain public endpoint path
            assert "/api/v1/settings-logo/" in result
            assert result == "https://api.example.com/api/v1/settings-logo/tenant-123"

    @patch('app.services.settings_service.StorageService')
    @patch('app.services.rabbitmq_service.rabbitmq_service')
    def test_upload_publishes_permanent_url_to_rabbitmq(self, mock_rabbitmq, mock_storage_class):
        """Test that RabbitMQ receives permanent public URL, not presigned URL"""
        # Mock storage service
        mock_storage = Mock()
        mock_storage.upload_logo_file.return_value = (
            "tenant_123/logos/logo.png",
            "http://minio:9000/temp-url"
        )
        mock_storage.delete_file.return_value = True
        mock_storage_class.return_value = mock_storage

        # Mock environment
        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com"}):
            service = SettingsService(self.mock_db)

            # Create mock file
            mock_file = Mock(spec=UploadFile)
            mock_file.filename = "logo.png"
            mock_file.content_type = "image/png"
            mock_file.file = BytesIO(b"fake image data")

            service.upload_company_logo("tenant-123", mock_file)

            # Verify RabbitMQ received permanent public URL
            mock_rabbitmq.publish_logo_uploaded.assert_called_once()
            call_args = mock_rabbitmq.publish_logo_uploaded.call_args

            assert call_args[1]['tenant_id'] == "tenant-123"
            assert call_args[1]['logo_url'] == "https://api.example.com/api/v1/settings-logo/tenant-123"

            # Should NOT contain MinIO URL
            assert "minio" not in call_args[1]['logo_url']


class TestLogoURLFormat:
    """Test the format of returned logo URLs"""

    @patch('app.services.settings_service.StorageService')
    def test_logo_url_is_valid_http_url(self, mock_storage_class):
        """Test that constructed URL is a valid HTTP/HTTPS URL"""
        mock_db = Mock()

        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com"}):
            service = SettingsService(mock_db)
            url = service._construct_public_logo_url("tenant-123")

            # Should start with http:// or https://
            assert url.startswith("http://") or url.startswith("https://")

            # Should not have double slashes except in protocol
            assert url.count("//") == 1  # Only in https://

    @patch('app.services.settings_service.StorageService')
    def test_logo_url_contains_tenant_id(self, mock_storage_class):
        """Test that logo URL includes the tenant ID"""
        mock_db = Mock()
        tenant_id = "test-tenant-456"

        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com"}):
            service = SettingsService(mock_db)
            url = service._construct_public_logo_url(tenant_id)

            assert tenant_id in url
            assert url.endswith(tenant_id)

    @patch('app.services.settings_service.StorageService')
    def test_logo_url_uses_correct_endpoint_path(self, mock_storage_class):
        """Test that logo URL uses the correct API endpoint path"""
        mock_db = Mock()

        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com"}):
            service = SettingsService(mock_db)
            url = service._construct_public_logo_url("tenant-123")

            assert "/api/v1/settings-logo/" in url


class TestBackwardCompatibility:
    """Test that changes maintain backward compatibility"""

    @patch('app.services.settings_service.StorageService')
    @patch('app.services.rabbitmq_service.rabbitmq_service')
    def test_logo_still_stored_in_minio(self, mock_rabbitmq, mock_storage_class):
        """Test that logo file is still stored in MinIO (not removed)"""
        # Mock storage service
        mock_storage = Mock()
        mock_storage.upload_logo_file.return_value = (
            "tenant_123/logos/logo.png",
            "http://minio:9000/temp-url"
        )
        mock_storage.delete_file.return_value = True
        mock_storage_class.return_value = mock_storage

        mock_db = Mock()

        with patch.dict(os.environ, {"BACKEND_URL": "https://api.example.com"}):
            service = SettingsService(mock_db)

            # Create mock file
            mock_file = Mock(spec=UploadFile)
            mock_file.filename = "logo.png"
            mock_file.content_type = "image/png"
            mock_file.file = BytesIO(b"fake image data")

            service.upload_company_logo("tenant-123", mock_file)

            # Verify file was still uploaded to MinIO
            mock_storage.upload_logo_file.assert_called_once()

            # File should still be stored in MinIO with correct path
            call_args = mock_storage.upload_logo_file.call_args
            assert call_args[1]['tenant_id'] == "tenant-123"
