"""Regression tests for role mapping in dependencies.validate_token.

A long-standing bug had `validate_token` mapping ROLE_TENANT_ADMIN → "admin"
but never mapping ROLE_SYSTEM_ADMIN → "super_admin", which silently broke
every super-admin-gated endpoint in this service (including the SMS admin
endpoints that had been shipped before WhatsApp).
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.services import dependencies
from app.services.dependencies import (
    TokenClaims,
    validate_super_admin_token,
    validate_token,
)


def _make_credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="anything")


def _token_info(authorities: list[str]) -> dict:
    return {
        "user_id": "user-123",
        "tenant_id": "tenant-abc",
        "email": "user@example.test",
        "authorities": authorities,
        "exp": 9999999999,
        "active": True,
    }


@pytest.mark.asyncio
async def test_system_admin_role_is_super_admin():
    with patch.object(
        dependencies, "validate_jwt_locally",
        new=AsyncMock(return_value=_token_info(["ROLE_SYSTEM_ADMIN"])),
    ):
        claims = await validate_token(_make_credentials())
    assert claims.role == "super_admin"


@pytest.mark.asyncio
async def test_tenant_admin_role_is_admin():
    with patch.object(
        dependencies, "validate_jwt_locally",
        new=AsyncMock(return_value=_token_info(["ROLE_TENANT_ADMIN"])),
    ):
        claims = await validate_token(_make_credentials())
    assert claims.role == "admin"


@pytest.mark.asyncio
async def test_system_admin_takes_precedence_over_tenant_admin():
    """A user with both authorities should be treated as super_admin."""
    with patch.object(
        dependencies, "validate_jwt_locally",
        new=AsyncMock(return_value=_token_info(["ROLE_TENANT_ADMIN", "ROLE_SYSTEM_ADMIN"])),
    ):
        claims = await validate_token(_make_credentials())
    assert claims.role == "super_admin"


@pytest.mark.asyncio
async def test_no_authorities_is_plain_user():
    with patch.object(
        dependencies, "validate_jwt_locally",
        new=AsyncMock(return_value=_token_info([])),
    ):
        claims = await validate_token(_make_credentials())
    assert claims.role == "user"


@pytest.mark.asyncio
async def test_super_admin_gate_accepts_system_admin():
    claims = TokenClaims(
        user_id="u", tenant_id="t", email="e", role="super_admin", exp=1,
    )
    result = await validate_super_admin_token(claims)
    assert result is claims


@pytest.mark.asyncio
async def test_super_admin_gate_rejects_tenant_admin():
    claims = TokenClaims(
        user_id="u", tenant_id="t", email="e", role="admin", exp=1,
    )
    with pytest.raises(HTTPException) as exc_info:
        await validate_super_admin_token(claims)
    assert exc_info.value.status_code == 403
