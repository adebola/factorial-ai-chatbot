# Keycloak + Docker Setup Guide for ChatCraft OAuth Testing

This guide walks you through installing Keycloak locally on Docker (port 9090) and configuring a PKCE-enabled OAuth client for the ChatCraft chat widget authentication flow.

---

## Prerequisites

- Docker installed and running
- A terminal / command prompt
- Your ChatCraft widget running locally (e.g., on `http://localhost:4200`)

---

## Part 1: Install and Run Keycloak on Docker

### Step 1 — Pull and run the Keycloak container

Run this single command to start Keycloak in development mode, mapped to port **9090**:

```bash
docker run -d \
  --name chatcraft-keycloak \
  -p 9090:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:24.0 \
  start-dev
```

What this does:
- `-d` — runs in the background (detached)
- `--name chatcraft-keycloak` — names the container so you can easily manage it
- `-p 9090:8080` — maps your machine's port 9090 to Keycloak's internal port 8080
- `-e KEYCLOAK_ADMIN=admin` — creates an admin user with username `admin`
- `-e KEYCLOAK_ADMIN_PASSWORD=admin` — sets the admin password to `admin`
- `start-dev` — runs Keycloak in development mode (no HTTPS required, faster startup)

### Step 2 — Verify Keycloak is running

Wait about 20–30 seconds for startup, then check:

```bash
docker logs chatcraft-keycloak
```

Look for a line like:
```
Keycloak 24.0.x on JVM (powered by Quarkus) started in Xs
```

Open your browser and navigate to:

```
http://localhost:9090
```

You should see the Keycloak welcome page. Click **Administration Console** and log in with:
- Username: `admin`
- Password: `admin`

### Useful Docker commands for managing Keycloak

```bash
# Stop Keycloak
docker stop chatcraft-keycloak

# Start it again
docker start chatcraft-keycloak

# View logs (follow mode)
docker logs -f chatcraft-keycloak

# Remove the container entirely (to start fresh)
docker rm -f chatcraft-keycloak
```

---

## Part 2: Create a Realm for ChatCraft

Keycloak uses "realms" to isolate groups of users and applications. You'll create a dedicated realm for testing.

### Step 1 — Create the realm

1. In the Keycloak admin console, look at the **top-left corner** where it says "Keycloak" (or "master")
2. Click the dropdown arrow next to it
3. Click **Create Realm**
4. Set the following:
    - **Realm name**: `chatcraft`
5. Click **Create**

You'll be switched into the new `chatcraft` realm automatically. The top-left should now show "chatcraft".

---

## Part 3: Create a PKCE Client for ChatCraft

This is where you configure the OAuth client that the ChatCraft widget will authenticate against. PKCE (Proof Key for Code Exchange) is essential because the chat widget is a **public client** — it runs in the user's browser and cannot securely store a client secret.

### Step 1 — Create the client

1. In the left sidebar, click **Clients**
2. Click the **Create client** button

### Step 2 — General Settings

- **Client type**: `OpenID Connect` (this should be the default)
- **Client ID**: `chatcraft-widget`
- **Name**: `ChatCraft Widget` (optional, just for display)
- **Description**: `OAuth client for ChatCraft chat widget authentication` (optional)
- Click **Next**

### Step 3 — Capability Config

This is the critical step for PKCE:

- **Client authentication**: **OFF**
    - This makes it a "public" client — no client secret is required
    - This is correct for browser-based apps like the chat widget
    - PKCE replaces the client secret as the security mechanism

- **Authorization**: **OFF**
    - We don't need Keycloak's fine-grained authorization features

- **Authentication flow** — enable ONLY these:
    - ✅ **Standard flow** — this is the Authorization Code flow (what we need)
    - ❌ **Direct access grants** — turn this OFF (it's the Resource Owner Password flow, not secure for our use case)
    - ❌ **Implicit flow** — turn this OFF (deprecated, less secure)
    - ❌ **Service accounts roles** — turn this OFF (for machine-to-machine, not relevant)

- Click **Next**

### Step 4 — Login Settings

These URLs tell Keycloak where it's allowed to redirect after authentication:

- **Root URL**: `http://localhost:4200`
    - This is where your Angular app runs during development

- **Home URL**: leave blank

- **Valid redirect URIs**: `http://localhost:4200/oauth/callback`
    - This is the URL of your OAuth callback page
    - Keycloak will ONLY redirect to URLs matching this pattern after login
    - You can add multiple entries, one per line, for different environments

- **Valid post logout redirect URIs**: `http://localhost:4200/*`
    - Where Keycloak can redirect after logout

- **Web origins**: `http://localhost:4200`
    - This configures CORS — allows your Angular app to make requests to Keycloak
    - You can also use `+` which means "use the same origins as valid redirect URIs"

- Click **Save**

### Step 5 — Enable PKCE (S256)

After saving, you need to explicitly configure PKCE:

1. Stay on the client settings page for `chatcraft-widget`
2. Click the **Advanced** tab at the top
3. Scroll down to the **Advanced Settings** section
4. Find **Proof Key for Code Exchange Code Challenge Method**
5. Set it to: **S256**
    - This means Keycloak will REQUIRE PKCE on every authorization request
    - S256 is the SHA-256 challenge method (more secure than "plain")
6. Click **Save**

> **Why S256?** When the chat widget starts the auth flow, it generates a random `code_verifier`, hashes it with SHA-256 to create the `code_challenge`, and sends only the challenge to Keycloak. When exchanging the code for a token, it sends the original `code_verifier`. Keycloak hashes it again and verifies it matches. This prevents authorization code interception attacks without needing a client secret.

---

## Part 4: Create a Test User

### Step 1 — Create the user

1. In the left sidebar, click **Users**
2. Click **Add user**
3. Fill in:
    - **Username**: `testuser`
    - **Email**: `testuser@example.com`
    - **Email verified**: toggle **ON**
    - **First name**: `Test`
    - **Last name**: `User`
4. Click **Create**

### Step 2 — Set the password

1. After the user is created, click the **Credentials** tab
2. Click **Set password**
3. Enter:
    - **Password**: `password`
    - **Password confirmation**: `password`
    - **Temporary**: toggle **OFF** (so the user isn't forced to change password on first login)
4. Click **Save**
5. Confirm by clicking **Save password**

---

## Part 5: Verify the Configuration

### The endpoints you need

All your OAuth endpoints follow this pattern:
```
http://localhost:9090/realms/chatcraft/protocol/openid-connect/{endpoint}
```

The key endpoints are:

| Endpoint | URL |
|----------|-----|
| Authorization | `http://localhost:9090/realms/chatcraft/protocol/openid-connect/auth` |
| Token | `http://localhost:9090/realms/chatcraft/protocol/openid-connect/token` |
| UserInfo | `http://localhost:9090/realms/chatcraft/protocol/openid-connect/userinfo` |
| Logout | `http://localhost:9090/realms/chatcraft/protocol/openid-connect/logout` |
| JWKS | `http://localhost:9090/realms/chatcraft/protocol/openid-connect/certs` |
| OpenID Config | `http://localhost:9090/realms/chatcraft/.well-known/openid-configuration` |

### Quick test — Verify OpenID Configuration

Open this URL in your browser:
```
http://localhost:9090/realms/chatcraft/.well-known/openid-configuration
```

You should get a JSON response listing all the endpoints. This confirms your realm is set up correctly.

### Quick test — Test the full authorization flow manually

Open this URL in your browser (all on one line):

```
http://localhost:9090/realms/chatcraft/protocol/openid-connect/auth?response_type=code&client_id=chatcraft-widget&redirect_uri=http://localhost:4200/oauth/callback&scope=openid%20profile%20email&state=test123&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
```

What should happen:
1. Keycloak shows you a login page
2. Enter `testuser` / `password`
3. Keycloak redirects to `http://localhost:4200/oauth/callback?code=SOME_CODE&state=test123`
4. If your callback page isn't running yet, you'll get a browser error — that's fine, just check the URL bar to confirm the `code` parameter is present

If you see the authorization code in the redirect URL, everything is configured correctly.

---

## Part 6: ChatCraft Widget Configuration

Update your ChatCraft OAuth configuration to point to port 9090. Here's what the config should look like:

### Angular widget config
```typescript
this.oauthConfig = {
  authorizationUrl: 'http://localhost:9090/realms/chatcraft/protocol/openid-connect/auth',
  tokenExchangeUrl: 'http://localhost:8000/v1/auth/oauth/token',  // Your ChatCraft backend
  clientId: 'chatcraft-widget',
  redirectUri: 'http://localhost:4200/oauth/callback',
  scope: 'openid profile email',
};
```

### FastAPI backend config (if using server-side token exchange)

Since this is a **public client** (no client secret), the token exchange from your backend changes slightly:

```python
# For PUBLIC clients (PKCE), there is NO client_secret
token_response = await client.post(
    "http://localhost:9090/realms/chatcraft/protocol/openid-connect/token",
    data={
        "grant_type": "authorization_code",
        "code": request.code,
        "redirect_uri": "http://localhost:4200/oauth/callback",
        "client_id": "chatcraft-widget",
        # NO client_secret — PKCE replaces it
        "code_verifier": request.code_verifier,
    },
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
```

> **Important note about public vs confidential clients:** Since we set "Client authentication" to OFF in Keycloak, this is a public client. The `code_verifier` (PKCE) is what proves the token request is legitimate — no `client_secret` is needed or accepted. If you later decide to make it a confidential client (authentication ON), you'd need to include the `client_secret` in addition to the `code_verifier`.

---

## Part 7: Adding More Redirect URIs for Production

When you deploy to production, you'll need to add the production callback URL:

1. Go to **Clients** → `chatcraft-widget` → **Settings**
2. Under **Valid redirect URIs**, add your production URL:
   ```
   https://chatcraft.cc/oauth/callback
   ```
3. Under **Web origins**, add:
   ```
   https://chatcraft.cc
   ```
4. Click **Save**

You can have multiple redirect URIs — Keycloak validates that each authorization request's `redirect_uri` matches one of the configured values.

---

## Troubleshooting

### "Invalid redirect URI" error
- Double-check that `redirect_uri` in your widget config exactly matches what's in Keycloak's **Valid redirect URIs**
- Watch for trailing slashes — `http://localhost:4200/oauth/callback` and `http://localhost:4200/oauth/callback/` are different

### "Invalid client" error
- Verify the `client_id` is exactly `chatcraft-widget`
- Make sure you're using the `chatcraft` realm, not `master`

### PKCE errors ("Missing parameter: code_challenge")
- Confirm that PKCE is being sent in the authorization request
- Check that your `code_challenge_method` is `S256` (must match what's configured in Keycloak)

### CORS errors
- Ensure `http://localhost:4200` (or your widget's origin) is in the **Web origins** field
- If using `+`, ensure the valid redirect URI origin matches your widget's origin

### "Invalid code verifier" on token exchange
- The `code_verifier` must be the original random string that was used to generate the `code_challenge`
- Make sure it's stored in `sessionStorage` and retrieved correctly
- Verify you're using SHA-256 hashing and base64url encoding (no padding)

### Keycloak container won't start
```bash
# Check if port 9090 is already in use
lsof -i :9090

# Check container logs for errors
docker logs chatcraft-keycloak

# Remove and recreate if needed
docker rm -f chatcraft-keycloak
# Then run the docker run command again
```
