# OAuth2 Multi-Tenant Architecture Design

## 🎯 **Strategy Overview**

### **User ID Strategy: Tenant-Scoped (Recommended)**

```sql
-- Users table with tenant isolation
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    username VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'USER',
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- Tenant-scoped uniqueness
    UNIQUE(tenant_id, username),
    UNIQUE(tenant_id, email)
);

-- Roles per tenant (flexible role system)
CREATE TABLE tenant_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    permissions JSON NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(tenant_id, name)
);

-- User roles (many-to-many)
CREATE TABLE user_tenant_roles (
    user_id UUID REFERENCES users(id),
    tenant_role_id UUID REFERENCES tenant_roles(id),
    assigned_at TIMESTAMP DEFAULT NOW(),
    
    PRIMARY KEY (user_id, tenant_role_id)
);
```

**Benefits:**
- ✅ Same email can exist across tenants (user@company1.com, user@company2.com)
- ✅ Simpler for end users
- ✅ Natural tenant isolation
- ✅ Easier user management per tenant

## 🏗️ **Architecture Components**

### **1. Spring Authorization Server (Port 9000)**

```java
@Configuration
@EnableAuthorizationServer
public class MultiTenantAuthorizationServerConfig {

    @Bean
    public RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate, 
            TenantService tenantService) {
        
        return new JdbcRegisteredClientRepository(jdbcTemplate) {
            @Override
            public RegisteredClient findByClientId(String clientId) {
                // Parse tenant from client ID: tenant_xyz_web, tenant_xyz_mobile
                String tenantId = extractTenantFromClientId(clientId);
                
                Tenant tenant = tenantService.findById(tenantId);
                if (tenant == null || !tenant.isActive()) {
                    return null;
                }
                
                return buildTenantSpecificClient(tenant, clientId);
            }
        };
    }
    
    @Bean
    public OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer(UserService userService) {
        return (context) -> {
            if (context.getTokenType() == OAuth2TokenType.ACCESS_TOKEN) {
                Authentication principal = context.getPrincipal();
                String username = principal.getName();
                String tenantId = extractTenantFromAuthentication(principal);
                
                User user = userService.findByTenantAndUsername(tenantId, username);
                
                context.getClaims().claims((claims) -> {
                    claims.put("tenant_id", tenantId);
                    claims.put("user_id", user.getId());
                    claims.put("roles", user.getRoles());
                    claims.put("permissions", getUserPermissions(user));
                    claims.put("plan_limits", getTenantPlanLimits(tenantId));
                    claims.put("iss", "https://auth.factorialbot.com");
                });
            }
        };
    }
    
    private RegisteredClient buildTenantSpecificClient(Tenant tenant, String clientId) {
        return RegisteredClient.withId(UUID.randomUUID().toString())
                .clientId(clientId)
                .clientSecret("{bcrypt}" + tenant.getClientSecret())
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri(tenant.getCallbackUrl())
                .scope(OidcScopes.OPENID)
                .scope(OidcScopes.PROFILE)
                .scope("documents:read")
                .scope("documents:write")
                .scope("chat:access")
                .scope(tenant.getPlan().getAllowedScopes()) // Plan-based scopes
                .clientSettings(ClientSettings.builder()
                    .requireAuthorizationConsent(false)
                    .requireProofKey(true) // PKCE for security
                    .build())
                .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofHours(1))
                    .refreshTokenTimeToLive(Duration.ofDays(30))
                    .reuseRefreshTokens(false)
                    .build())
                .build();
    }
}
```

### **2. Custom Authentication Provider**

```java
@Component
public class MultiTenantAuthenticationProvider implements AuthenticationProvider {

    @Autowired
    private UserService userService;
    
    @Autowired
    private PasswordEncoder passwordEncoder;

    @Override
    public Authentication authenticate(Authentication authentication) throws AuthenticationException {
        String username = authentication.getName();
        String password = authentication.getCredentials().toString();
        
        // Extract tenant from client ID or domain
        String tenantId = extractTenantFromRequest();
        
        User user = userService.findByTenantAndUsername(tenantId, username);
        if (user == null || !user.isActive()) {
            throw new BadCredentialsException("Invalid credentials");
        }
        
        if (!passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new BadCredentialsException("Invalid credentials");
        }
        
        // Create tenant-aware principal
        MultiTenantUserPrincipal principal = new MultiTenantUserPrincipal(
            user.getId(),
            tenantId,
            username,
            user.getRoles(),
            user.getPermissions()
        );
        
        return new UsernamePasswordAuthenticationToken(
            principal, 
            null, 
            getAuthorities(user.getRoles())
        );
    }
    
    @Override
    public boolean supports(Class<?> authentication) {
        return UsernamePasswordAuthenticationToken.class.isAssignableFrom(authentication);
    }
}
```

### **3. Tenant Context Resolution**

```java
@Component
public class TenantContextResolver {
    
    // Strategy 1: Subdomain-based (tenant1.factorialbot.com)
    public String resolveTenantFromDomain(HttpServletRequest request) {
        String serverName = request.getServerName();
        if (serverName.contains(".")) {
            String[] parts = serverName.split("\\.");
            if (parts.length >= 3) { // subdomain.domain.com
                return parts[0];
            }
        }
        return null;
    }
    
    // Strategy 2: Client ID based (tenant_xyz_web)
    public String resolveTenantFromClientId(String clientId) {
        if (clientId.startsWith("tenant_")) {
            String[] parts = clientId.split("_");
            if (parts.length >= 2) {
                return parts[1]; // Extract tenant ID
            }
        }
        return null;
    }
    
    // Strategy 3: Custom header (X-Tenant-ID)
    public String resolveTenantFromHeader(HttpServletRequest request) {
        return request.getHeader("X-Tenant-ID");
    }
}
```

## 🐍 **FastAPI Services OAuth2 Integration**

### **1. JWT Token Validation Middleware**

```python
# shared/auth.py - Common authentication module
import jwt
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
import httpx
import asyncio
from functools import lru_cache
import json
import logging

logger = logging.getLogger(__name__)

class JWTBearer(HTTPBearer):
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> Optional[str]:
        credentials = await super().__call__(request)
        if credentials:
            return await self.verify_jwt(credentials.credentials)
        return None
    
    async def verify_jwt(self, token: str) -> str:
        try:
            # Get JWT public key from authorization server
            public_key = await self.get_jwt_public_key()
            
            # Verify and decode token
            payload = jwt.decode(
                token, 
                public_key, 
                algorithms=["RS256"],
                issuer="https://auth.factorialbot.com"
            )
            
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    
    @lru_cache(maxsize=1)
    async def get_jwt_public_key(self) -> str:
        """Get JWT public key from authorization server (cached)"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:9000/.well-known/jwks.json")
                response.raise_for_status()
                jwks = response.json()
                
                # Extract public key (simplified - in production, handle key rotation)
                return jwks["keys"][0]  # Get first key
        except Exception as e:
            logger.error(f"Failed to get JWT public key: {e}")
            raise HTTPException(status_code=500, detail="Authentication service unavailable")

class MultiTenantUser:
    def __init__(self, payload: Dict[str, Any]):
        self.user_id: str = payload.get("user_id")
        self.tenant_id: str = payload.get("tenant_id") 
        self.username: str = payload.get("sub")
        self.roles: list = payload.get("roles", [])
        self.permissions: list = payload.get("permissions", [])
        self.plan_limits: dict = payload.get("plan_limits", {})
        self.email: str = payload.get("email")
        
    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions
    
    def has_role(self, role: str) -> bool:
        return role in self.roles
    
    def can_access_resource(self, resource: str) -> bool:
        # Implement resource-based access control
        return f"{resource}:read" in self.permissions or f"{resource}:write" in self.permissions

# Dependency for getting current authenticated user
security = JWTBearer()

async def get_current_user(token_payload: dict = Depends(security)) -> MultiTenantUser:
    return MultiTenantUser(token_payload)

async def get_admin_user(current_user: MultiTenantUser = Depends(get_current_user)) -> MultiTenantUser:
    if not current_user.has_role("ADMIN"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Tenant-specific database session
async def get_tenant_db_session(current_user: MultiTenantUser = Depends(get_current_user)):
    # Return tenant-scoped database session
    from sqlalchemy.orm import sessionmaker
    from .database import get_engine
    
    engine = get_engine(current_user.tenant_id)  # Tenant-specific DB
    SessionLocal = sessionmaker(bind=engine)
    
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

### **2. FastAPI Service Integration**

```python
# onboarding-service/app/main.py
from fastapi import FastAPI, Depends, HTTPException
from shared.auth import get_current_user, MultiTenantUser, get_admin_user

app = FastAPI(title="Onboarding Service")

@app.post("/api/v1/documents/upload")
async def upload_document(
    file: UploadFile,
    current_user: MultiTenantUser = Depends(get_current_user)
):
    # Check permissions
    if not current_user.has_permission("documents:write"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Check plan limits
    if await document_count_exceeds_limit(current_user.tenant_id, current_user.plan_limits):
        raise HTTPException(status_code=429, detail="Document limit exceeded for current plan")
    
    # Process with tenant context
    result = await process_document(file, current_user.tenant_id, current_user.user_id)
    return result

@app.get("/api/v1/tenants/{tenant_id}/users")
async def list_tenant_users(
    tenant_id: str,
    current_user: MultiTenantUser = Depends(get_admin_user)  # Admin only
):
    # Ensure user can only access their own tenant's users
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cannot access other tenant's users")
    
    users = await get_tenant_users(tenant_id)
    return users

# Middleware for logging with tenant context
@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    # Extract user context if available
    token = request.headers.get("Authorization")
    if token:
        try:
            # Add tenant context to logs
            tenant_id = extract_tenant_from_token(token)
            request.state.tenant_id = tenant_id
        except:
            pass
    
    response = await call_next(request)
    return response
```

### **3. Chat Service WebSocket Authentication**

```python
# chat-service/app/websockets/chat.py
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
import jwt
from typing import Dict, List

class ConnectionManager:
    def __init__(self):
        # Tenant-isolated connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, tenant_id: str, user_id: str):
        await websocket.accept()
        
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = []
        
        self.active_connections[tenant_id].append({
            "websocket": websocket,
            "user_id": user_id
        })
    
    async def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id] = [
                conn for conn in self.active_connections[tenant_id] 
                if conn["websocket"] != websocket
            ]

manager = ConnectionManager()

@app.websocket("/ws/chat/{tenant_id}")
async def websocket_endpoint(websocket: WebSocket, tenant_id: str):
    # Authenticate WebSocket connection
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return
    
    try:
        user = await verify_jwt_token(token)
        if user.tenant_id != tenant_id:
            await websocket.close(code=4003, reason="Tenant access denied")
            return
    except:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    await manager.connect(websocket, tenant_id, user.user_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Process chat message with tenant context
            response = await process_chat_message(
                message["content"], 
                tenant_id, 
                user.user_id
            )
            
            await websocket.send_text(json.dumps(response))
            
    except WebSocketDisconnect:
        await manager.disconnect(websocket, tenant_id)
```

## 🌐 **Frontend Integration**

### **OAuth2 Authorization Code Flow**

```javascript
// Frontend OAuth2 client
class MultiTenantOAuth2Client {
    constructor(tenantId, clientId) {
        this.tenantId = tenantId;
        this.clientId = `tenant_${tenantId}_web`;
        this.authUrl = 'http://localhost:9000';
        this.gatewayUrl = 'http://localhost:8080';
    }
    
    // Initiate OAuth2 flow
    async login() {
        const codeVerifier = this.generateCodeVerifier();
        const codeChallenge = await this.generateCodeChallenge(codeVerifier);
        
        localStorage.setItem('oauth_code_verifier', codeVerifier);
        
        const params = new URLSearchParams({
            response_type: 'code',
            client_id: this.clientId,
            redirect_uri: `${window.location.origin}/auth/callback`,
            scope: 'openid profile documents:read documents:write chat:access',
            code_challenge: codeChallenge,
            code_challenge_method: 'S256',
            state: this.generateState()
        });
        
        window.location.href = `${this.authUrl}/oauth2/authorize?${params}`;
    }
    
    // Handle callback
    async handleCallback(code, state) {
        const codeVerifier = localStorage.getItem('oauth_code_verifier');
        
        const response = await fetch(`${this.authUrl}/oauth2/token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                grant_type: 'authorization_code',
                client_id: this.clientId,
                code: code,
                redirect_uri: `${window.location.origin}/auth/callback`,
                code_verifier: codeVerifier
            })
        });
        
        const tokens = await response.json();
        
        // Store tokens
        localStorage.setItem('access_token', tokens.access_token);
        localStorage.setItem('refresh_token', tokens.refresh_token);
        
        // Decode user info
        const userInfo = this.decodeJWT(tokens.access_token);
        localStorage.setItem('user_info', JSON.stringify(userInfo));
        
        return userInfo;
    }
    
    // API client with automatic token handling
    async apiCall(endpoint, options = {}) {
        const token = localStorage.getItem('access_token');
        
        const response = await fetch(`${this.gatewayUrl}${endpoint}`, {
            ...options,
            headers: {
                ...options.headers,
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });
        
        if (response.status === 401) {
            // Token expired, try refresh
            await this.refreshToken();
            return this.apiCall(endpoint, options);
        }
        
        return response;
    }
}
```

## 🔒 **Security Considerations**

### **1. Tenant Isolation**
- JWT tokens include `tenant_id` claim
- All database queries filtered by tenant
- Resource access validation per tenant

### **2. Permission Model**
```json
{
  "roles": ["ADMIN", "USER"],
  "permissions": [
    "documents:read",
    "documents:write", 
    "chat:access",
    "users:manage"
  ],
  "plan_limits": {
    "max_documents": 100,
    "max_users": 10,
    "features": ["advanced_chat", "api_access"]
  }
}
```

### **3. API Rate Limiting**
```python
# Per-tenant rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=lambda request: f"{request.state.tenant_id}:{get_remote_address(request)}"
)

@app.get("/api/v1/documents/")
@limiter.limit("100/minute")  # Per tenant per IP
async def list_documents(request: Request, current_user: MultiTenantUser = Depends(get_current_user)):
    # Implementation
    pass
```

## 📈 **Scalability & Deployment**

### **Microservices Setup:**
```yaml
# docker-compose.yml
services:
  auth-service:
    image: factorial-auth-server:latest
    ports:
      - "9000:9000"
    environment:
      - DB_URL=postgresql://postgres:pass@postgres:5432/auth_db
  
  gateway-service:
    image: factorial-gateway:latest
    ports:
      - "8080:8080"
    environment:
      - OAUTH2_ISSUER=http://auth-service:9000
  
  onboarding-service:
    image: factorial-onboarding:latest
    environment:
      - OAUTH2_ISSUER=http://auth-service:9000
      - JWT_PUBLIC_KEY_URL=http://auth-service:9000/.well-known/jwks.json
```

This architecture provides:
- ✅ **Tenant Isolation**: Complete data and user isolation
- ✅ **Scalable Authentication**: OAuth2.0 with JWT tokens
- ✅ **Flexible Permissions**: Role and permission-based access
- ✅ **Multi-Language Support**: Works with Python FastAPI services
- ✅ **Frontend Integration**: Standard OAuth2 flows
- ✅ **Production Ready**: Secure, scalable, and maintainable