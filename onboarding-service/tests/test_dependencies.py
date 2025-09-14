"""
Test suite for dependencies.py functions
Tests get_full_tenant_details and get_tenant_settings functions
"""

import pytest
import asyncio
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict, Any
import httpx
import requests

# Add the app directory to the path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.dependencies import (
    get_full_tenant_details,
    get_tenant_settings,
    TokenClaims,
    _get_fallback_settings
)


class TestAuthenticationHelpers:
    """Helper methods for authentication in tests"""
    
    @staticmethod
    def get_test_credentials() -> Dict[str, str]:
        """Get test credentials for authentication"""
        return {
            "username": "adebola",
            "password": "password",
            "grant_type": "password",
            "client_id": "frontend-client",
            "client_secret": "secret"
        }
    
    @staticmethod
    async def get_access_token() -> tuple[str, str]:
        """
        Get a real access token from the authorization server
        Returns: (access_token, tenant_id)
        """
        auth_server_url = os.environ.get("AUTHORIZATION_SERVER_URL", "http://localhost:9000")
        token_url = f"{auth_server_url}/oauth2/token"
        
        credentials = TestAuthenticationHelpers.get_test_credentials()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data=credentials,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    access_token = token_data.get("access_token")
                    
                    # Decode the token to get tenant_id (without verification for testing)
                    import jwt
                    decoded = jwt.decode(access_token, options={"verify_signature": False})
                    tenant_id = decoded.get("tenant_id")
                    
                    return access_token, tenant_id
                else:
                    print(f"Failed to get access token: {response.status_code} - {response.text}")
                    # Return mock data for testing when auth server is not available
                    return "mock_access_token", "test_tenant_id"
                    
        except Exception as e:
            print(f"Error getting access token: {e}")
            # Return mock data for testing when auth server is not available
            return "mock_access_token", "test_tenant_id"


class TestGetFullTenantDetails:
    """Test suite for get_full_tenant_details function"""
    
    @pytest.mark.asyncio
    async def test_get_full_tenant_details_with_cache_hit(self):
        """Test that cached tenant details are returned when available"""
        tenant_id = "test_tenant_123"
        cached_tenant = {
            "id": tenant_id,
            "name": "Test Tenant",
            "domain": "test.com",
            "apiKey": "test_api_key"
        }
        
        with patch('app.services.cache_service.CacheService') as mock_cache_service:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get_cached_tenant.return_value = cached_tenant
            mock_cache_service.return_value = mock_cache_instance
            
            result = await get_full_tenant_details(tenant_id)
            
            assert result == cached_tenant
            mock_cache_instance.get_cached_tenant.assert_called_once_with('id', tenant_id)
    
    @pytest.mark.asyncio
    async def test_get_full_tenant_details_with_cache_miss_and_auth(self):
        """Test fetching tenant details from auth server with authentication"""
        tenant_id = "test_tenant_123"
        access_token = "test_access_token"
        tenant_data = {
            "id": tenant_id,
            "name": "Test Tenant",
            "domain": "test.com",
            "apiKey": "test_api_key",
            "config": {},
            "planId": "basic",
            "isActive": True
        }
        
        with patch('app.services.cache_service.CacheService') as mock_cache_service:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get_cached_tenant.return_value = None
            mock_cache_service.return_value = mock_cache_instance
            
            with patch('app.services.dependencies.httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = tenant_data
                
                mock_client_instance = AsyncMock()
                mock_client_instance.get.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance
                
                result = await get_full_tenant_details(tenant_id, access_token)
                
                assert result == tenant_data
                mock_client_instance.get.assert_called_once()
                
                # Verify authorization header was included
                call_args = mock_client_instance.get.call_args
                assert call_args[1]['headers'] == {"Authorization": f"Bearer {access_token}"}
    
    @pytest.mark.asyncio
    async def test_get_full_tenant_details_without_auth(self):
        """Test fetching tenant details without authentication token"""
        tenant_id = "test_tenant_123"
        tenant_data = {
            "id": tenant_id,
            "name": "Test Tenant",
            "domain": "test.com",
            "apiKey": "test_api_key"
        }
        
        with patch('app.services.cache_service.CacheService') as mock_cache_service:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get_cached_tenant.return_value = None
            mock_cache_service.return_value = mock_cache_instance
            
            with patch('app.services.dependencies.httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = tenant_data
                
                mock_client_instance = AsyncMock()
                mock_client_instance.get.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance
                
                result = await get_full_tenant_details(tenant_id)
                
                assert result == tenant_data
                
                # Verify no authorization header when no token provided
                call_args = mock_client_instance.get.call_args
                assert call_args[1]['headers'] == {}
    
    @pytest.mark.asyncio
    async def test_get_full_tenant_details_not_found(self):
        """Test handling of 404 response from auth server"""
        tenant_id = "nonexistent_tenant"
        
        with patch('app.services.cache_service.CacheService') as mock_cache_service:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get_cached_tenant.return_value = None
            mock_cache_service.return_value = mock_cache_instance
            
            with patch('app.services.dependencies.httpx.AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 404
                
                mock_client_instance = AsyncMock()
                mock_client_instance.get.return_value = mock_response
                mock_client.return_value.__aenter__.return_value = mock_client_instance
                
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    await get_full_tenant_details(tenant_id)
                
                assert exc_info.value.status_code == 404
                assert exc_info.value.detail == "Tenant not found"
    
    @pytest.mark.asyncio
    async def test_get_full_tenant_details_server_error(self):
        """Test handling of server errors from auth server"""
        tenant_id = "test_tenant_123"
        
        with patch('app.services.cache_service.CacheService') as mock_cache_service:
            mock_cache_instance = MagicMock()
            mock_cache_instance.get_cached_tenant.return_value = None
            mock_cache_service.return_value = mock_cache_instance
            
            with patch('app.services.dependencies.httpx.AsyncClient') as mock_client:
                mock_client_instance = AsyncMock()
                mock_client_instance.get.side_effect = httpx.RequestError("Connection failed")
                mock_client.return_value.__aenter__.return_value = mock_client_instance
                
                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    await get_full_tenant_details(tenant_id)
                
                assert exc_info.value.status_code == 503
                assert exc_info.value.detail == "Authorization server unavailable"


class TestGetTenantSettings:
    """Test suite for get_tenant_settings function"""
    
    def test_get_tenant_settings_success_with_auth(self):
        """Test successful retrieval of tenant settings with authentication"""
        tenant_id = "test_tenant_123"
        access_token = "test_access_token"
        settings_data = {
            "primaryColor": "#5D3EC1",
            "secondaryColor": "#C15D3E",
            "companyLogoUrl": "https://example.com/logo.png",
            "chatLogo": {
                "type": "url",
                "url": "https://example.com/chat-logo.png"
            },
            "hoverText": "Chat with us!",
            "welcomeMessage": "Welcome to our chat!",
            "chatWindowTitle": "Support Chat",
            "logoUrl": "https://example.com/logo.png"
        }
        
        with patch('app.services.dependencies.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = settings_data
            mock_get.return_value = mock_response
            
            result = get_tenant_settings(tenant_id, access_token)
            
            expected_result = {
                "primary_color": "#5D3EC1",
                "secondary_color": "#C15D3E",
                "company_logo_url": "https://example.com/logo.png",
                "chatLogo": {"type": "url", "url": "https://example.com/chat-logo.png"},
                "hover_text": "Chat with us!",
                "welcome_message": "Welcome to our chat!",
                "chat_window_title": "Support Chat",
                "logo_url": "https://example.com/logo.png"
            }
            
            assert result == expected_result
            
            # Verify the request was made with correct headers
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[1]['headers']['Authorization'] == f"Bearer {access_token}"
    
    def test_get_tenant_settings_without_auth(self):
        """Test retrieval of tenant settings without authentication"""
        tenant_id = "test_tenant_123"
        settings_data = {
            "primaryColor": "#5D3EC1",
            "secondaryColor": "#C15D3E"
        }
        
        with patch('app.services.dependencies.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = settings_data
            mock_get.return_value = mock_response
            
            result = get_tenant_settings(tenant_id)
            
            # Verify no Authorization header when no token
            call_args = mock_get.call_args
            assert 'Authorization' not in call_args[1]['headers']
    
    def test_get_tenant_settings_fallback_on_error(self):
        """Test fallback settings are returned on error"""
        tenant_id = "test_tenant_123"
        
        with patch('app.services.dependencies.requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response
            
            result = get_tenant_settings(tenant_id)
            
            # Should return fallback settings
            expected_fallback = _get_fallback_settings()
            assert result == expected_fallback
    
    def test_get_tenant_settings_connection_error(self):
        """Test fallback settings on connection error"""
        tenant_id = "test_tenant_123"
        
        with patch('app.services.dependencies.requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.RequestException("Connection failed")
            
            result = get_tenant_settings(tenant_id)
            
            # Should return fallback settings
            expected_fallback = _get_fallback_settings()
            assert result == expected_fallback
    
    def test_get_fallback_settings(self):
        """Test that fallback settings have correct structure"""
        fallback = _get_fallback_settings()
        
        assert fallback["primary_color"] == "#5D3EC1"
        assert fallback["secondary_color"] == "#C15D3E"
        assert fallback["company_logo_url"] == "https://"
        assert fallback["hover_text"] == "AI Chat"
        assert fallback["welcome_message"] == "Welcome to AI Chat"
        assert fallback["chat_window_title"] == "Chat Support"


class TestIntegration:
    """Integration tests using real authorization server (when available)"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_real_get_full_tenant_details(self):
        """Integration test with real authorization server"""
        # Skip if authorization server is not running
        auth_server_url = "http://localhost:90002/auth"
        # try:
        #     async with httpx.AsyncClient() as client:
        #         response = await client.get(f"{auth_server_url}/health", timeout=2.0)
        #         if response.status_code != 200:
        #             pytest.skip("Authorization server not available")
        # except:
        #     pytest.skip("Authorization server not available")
        
        # Get real access token
        access_token, tenant_id = await TestAuthenticationHelpers.get_access_token()
        
        if access_token == "mock_access_token":
            pytest.skip("Could not get real access token")
        
        # Test the actual function
        result = await get_full_tenant_details(tenant_id, access_token)
        
        # Verify result structure
        assert "id" in result
        assert result["id"] == tenant_id
        assert "name" in result
        assert "apiKey" in result
    
    @pytest.mark.integration
    def test_real_get_tenant_settings(self):
        """Integration test for get_tenant_settings with real server"""
        # Skip if authorization server is not running
        auth_server_url = "http://localhost:90002/auth"
        # try:
        #     response = requests.get(f"{auth_server_url}/health", timeout=2.0)
        #     if response.status_code != 200:
        #         pytest.skip("Authorization server not available")
        # except:
        #     pytest.skip("Authorization server not available")
        
        # Get a real access token (synchronously for this test)
        loop = asyncio.new_event_loop()
        access_token, tenant_id = loop.run_until_complete(
            TestAuthenticationHelpers.get_access_token()
        )
        loop.close()
        
        if access_token == "mock_access_token":
            pytest.skip("Could not get real access token")
        
        # Test the actual function
        result = get_tenant_settings(tenant_id, access_token)
        
        # Verify result structure
        assert "primary_color" in result
        assert "secondary_color" in result
        assert "hover_text" in result
        assert "welcome_message" in result
        assert "chat_window_title" in result


class TestTokenClaims:
    """Test suite for TokenClaims dataclass"""
    
    def test_token_claims_with_all_fields(self):
        """Test TokenClaims with all fields populated"""
        claims = TokenClaims(
            tenant_id="tenant_123",
            user_id="user_456",
            email="test@example.com",
            full_name="Test User",
            api_key="api_key_789",
            authorities=["ROLE_USER", "ROLE_ADMIN"],
            access_token="token_abc"
        )
        
        assert claims.tenant_id == "tenant_123"
        assert claims.user_id == "user_456"
        assert claims.email == "test@example.com"
        assert claims.full_name == "Test User"
        assert claims.api_key == "api_key_789"
        assert claims.authorities == ["ROLE_USER", "ROLE_ADMIN"]
        assert claims.access_token == "token_abc"
        assert claims.is_admin is True
    
    def test_token_claims_is_admin(self):
        """Test is_admin property with various authority combinations"""
        # Test with ROLE_ADMIN
        claims1 = TokenClaims(
            tenant_id="t1",
            user_id="u1",
            authorities=["ROLE_ADMIN"]
        )
        assert claims1.is_admin is True
        
        # Test with ADMIN
        claims2 = TokenClaims(
            tenant_id="t2",
            user_id="u2",
            authorities=["ADMIN"]
        )
        assert claims2.is_admin is True
        
        # Test with ROLE_TENANT_ADMIN
        claims3 = TokenClaims(
            tenant_id="t3",
            user_id="u3",
            authorities=["ROLE_TENANT_ADMIN"]
        )
        assert claims3.is_admin is True
        
        # Test with TENANT_ADMIN
        claims4 = TokenClaims(
            tenant_id="t4",
            user_id="u4",
            authorities=["TENANT_ADMIN"]
        )
        assert claims4.is_admin is True
        
        # Test with no admin roles
        claims5 = TokenClaims(
            tenant_id="t5",
            user_id="u5",
            authorities=["ROLE_USER"]
        )
        assert claims5.is_admin is False
        
        # Test with no authorities
        claims6 = TokenClaims(
            tenant_id="t6",
            user_id="u6",
            authorities=None
        )
        assert claims6.is_admin is False


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])