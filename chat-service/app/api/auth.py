"""
OAuth2 PKCE Auth Router for Chat Service.

Provides:
- POST /pkce/exchange  — exchange authorization code for tokens (BFF pattern)
- POST /pkce/refresh   — refresh tokens using stored refresh_token
- GET  /callback       — minimal HTML page that posts code back to opener via postMessage
"""

import uuid
import httpx
import jwt
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from ..services.tenant_client import TenantClient
from ..services.session_auth_service import session_auth_service
from ..models.chat_models import ChatSession
from ..core.database import SessionLocal
from ..core.logging_config import get_logger

logger = get_logger("auth")

router = APIRouter()
tenant_client = TenantClient()


# --- Request / Response schemas ---

class PKCEExchangeRequest(BaseModel):
    api_key: str
    authorization_code: str
    code_verifier: str
    redirect_uri: str
    session_id: Optional[str] = None  # Existing WebSocket session to upgrade (mid-chat login)


class PKCEExchangeResponse(BaseModel):
    session_id: str
    user: Dict[str, Any]
    expires_in: int


class PKCERefreshRequest(BaseModel):
    session_id: str
    api_key: str


class PKCERefreshResponse(BaseModel):
    expires_in: int


# --- Endpoints ---

@router.post("/pkce/exchange", response_model=PKCEExchangeResponse)
async def pkce_exchange(request: PKCEExchangeRequest):
    """
    Exchange an OAuth2 authorization code for tokens (BFF pattern).
    The widget never talks directly to the tenant's IdP token endpoint.
    """
    # 1. Look up tenant by API key
    tenant = await tenant_client.get_tenant_by_api_key(request.api_key)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant_id = tenant["id"]

    # 2. Fetch tenant's auth config (token_endpoint, client_id) from settings
    settings = await tenant_client.get_tenant_settings(tenant_id)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant auth settings not configured"
        )

    allow_auth = settings.get("allowAuthentication", False)
    token_endpoint = settings.get("authTokenEndpoint")
    client_id = settings.get("authClientId")

    if not allow_auth or not token_endpoint or not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End-user authentication is not enabled for this tenant"
        )

    # 3. Exchange authorization code at the tenant's token endpoint
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": request.authorization_code,
                    "code_verifier": request.code_verifier,
                    "redirect_uri": request.redirect_uri,
                    "client_id": client_id,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
    except httpx.RequestError as e:
        logger.error("Failed to reach tenant IdP token endpoint", error=str(e), url=token_endpoint)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to reach identity provider"
        )

    if token_response.status_code != 200:
        logger.error(
            "Token exchange failed",
            status=token_response.status_code,
            body=token_response.text[:500],
            tenant_id=tenant_id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization code exchange failed"
        )

    token_data = token_response.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    id_token = token_data.get("id_token")
    expires_in = token_data.get("expires_in", 3600)

    # 4. Decode the id_token or access_token to extract user claims
    user_info = _extract_user_claims(id_token or access_token)

    # 5. Create or upgrade an authenticated ChatSession
    db = SessionLocal()
    try:
        existing_session = None
        if request.session_id:
            # Mid-chat login: upgrade the existing WebSocket session in-place
            existing_session = db.query(ChatSession).filter(
                ChatSession.session_id == request.session_id,
                ChatSession.tenant_id == tenant_id,
            ).first()

        if existing_session:
            # Upgrade existing session to authenticated
            session_id = existing_session.session_id
            existing_session.is_authenticated = True
            existing_session.auth_user_sub = user_info.get("sub")
            existing_session.auth_user_email = user_info.get("email")
            existing_session.auth_user_name = user_info.get("name")
            existing_session.user_identifier = user_info.get("email") or user_info.get("sub")
            db.commit()
            logger.info("Upgraded existing session to authenticated", session_id=session_id, tenant_id=tenant_id)
        else:
            # Fresh login: create a new session
            session_id = str(uuid.uuid4())
            chat_session = ChatSession(
                tenant_id=tenant_id,
                session_id=session_id,
                user_identifier=user_info.get("email") or user_info.get("sub"),
                is_active=True,
                is_authenticated=True,
                auth_user_sub=user_info.get("sub"),
                auth_user_email=user_info.get("email"),
                auth_user_name=user_info.get("name"),
            )
            db.add(chat_session)
            db.commit()
    finally:
        db.close()

    # 6. Store tokens in Redis
    session_auth_service.store_tokens(
        session_id=session_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user_info=user_info
    )

    logger.info(
        "PKCE exchange successful",
        tenant_id=tenant_id,
        session_id=session_id,
        user_sub=user_info.get("sub")
    )

    return PKCEExchangeResponse(
        session_id=session_id,
        user=user_info,
        expires_in=expires_in
    )


@router.post("/pkce/refresh", response_model=PKCERefreshResponse)
async def pkce_refresh(request: PKCERefreshRequest):
    """Refresh the access token for an authenticated session."""
    # Verify the session exists and belongs to a valid tenant
    tenant = await tenant_client.get_tenant_by_api_key(request.api_key)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant_id = tenant["id"]

    # Get auth config
    settings = await tenant_client.get_tenant_settings(tenant_id)
    if not settings:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auth settings not configured")

    token_endpoint = settings.get("authTokenEndpoint")
    client_id = settings.get("authClientId")

    if not token_endpoint or not client_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Auth not configured")

    # Refresh the token
    new_token = await session_auth_service.refresh_token(
        session_id=request.session_id,
        token_endpoint=token_endpoint,
        client_id=client_id
    )

    if not new_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token refresh failed — user must re-authenticate"
        )

    # Get updated auth data for expires_in
    auth_data = session_auth_service.get_session_auth(request.session_id)
    expires_in = auth_data.get("expires_in", 3600) if auth_data else 3600

    return PKCERefreshResponse(expires_in=expires_in)


@router.get("/callback", response_class=HTMLResponse)
async def auth_callback():
    """
    OAuth2 callback page. This minimal HTML page:
    1. Reads `code` and `state` from URL query params
    2. Posts { code, state } to window.opener via postMessage
    3. Closes itself
    """
    return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head><title>Authentication</title></head>
<body>
<p>Completing authentication...</p>
<script>
(function() {
    var params = new URLSearchParams(window.location.search);
    var code = params.get('code');
    var state = params.get('state');
    var error = params.get('error');

    if (window.opener) {
        window.opener.postMessage({
            type: 'factorial_auth_callback',
            code: code,
            state: state,
            error: error
        }, '*');
        window.close();
    } else {
        document.body.innerHTML = '<p>Authentication complete. You may close this window.</p>';
    }
})();
</script>
</body>
</html>""")


# --- Helpers ---

def _extract_user_claims(token: str) -> Dict[str, Any]:
    """Decode a JWT token (without signature verification) to extract user claims."""
    try:
        # Decode without verification — we trust the token endpoint response
        payload = jwt.decode(token, options={"verify_signature": False})
        return {
            "sub": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name") or payload.get("preferred_username") or payload.get("given_name", ""),
        }
    except Exception as e:
        logger.warning(f"Failed to decode token for user claims: {e}")
        return {"sub": "unknown"}
