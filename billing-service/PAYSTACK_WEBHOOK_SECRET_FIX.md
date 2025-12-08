# Paystack Webhook Secret Fix

**Date**: 2025-11-19
**Status**: ✅ **FIXED**
**Issue**: Incorrect webhook signature verification using non-existent `PAYSTACK_WEBHOOK_SECRET`

---

## Problem Identified

The billing service was incorrectly configured to use a separate `PAYSTACK_WEBHOOK_SECRET` environment variable for webhook signature verification.

**Issue**: Paystack does NOT provide a separate webhook secret. They use your **SECRET KEY** for webhook signature verification.

---

## What Paystack Actually Does

According to Paystack's official documentation:

1. **Webhook Signing**: Paystack signs webhook payloads using **HMAC SHA512** with your **SECRET KEY**
2. **Signature Header**: The signature is sent in the `x-paystack-signature` header
3. **Verification**: You verify by computing the same HMAC SHA512 hash using your secret key and comparing

**Formula**:
```python
expected_signature = hmac.new(
    secret_key.encode('utf-8'),  # Your Paystack SECRET KEY
    payload,                      # Raw request body
    hashlib.sha512               # SHA512 algorithm
).hexdigest()
```

---

## Changes Made

### 1. Updated PaystackService Class

**File**: `app/services/paystack_service.py`

#### Before (Incorrect):
```python
def __init__(self, db: Session):
    self.secret_key = os.environ.get("PAYSTACK_SECRET_KEY")
    self.webhook_secret = os.environ.get("PAYSTACK_WEBHOOK_SECRET")  # ❌ WRONG
    # ...

def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
    if not self.webhook_secret:  # ❌ WRONG
        raise ValueError("PAYSTACK_WEBHOOK_SECRET is required")

    expected_signature = hmac.new(
        self.webhook_secret.encode('utf-8'),  # ❌ WRONG
        payload,
        hashlib.sha512
    ).hexdigest()
```

#### After (Correct):
```python
def __init__(self, db: Session):
    self.secret_key = os.environ.get("PAYSTACK_SECRET_KEY")
    # Removed self.webhook_secret ✅
    # ...

def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
    """
    Verify Paystack webhook signature.

    Paystack signs webhook payloads using HMAC SHA512 with your SECRET KEY.
    The signature is sent in the 'x-paystack-signature' header.

    Reference: https://paystack.com/docs/payments/webhooks/
    """
    if not self.secret_key:  # ✅ CORRECT
        raise ValueError("PAYSTACK_SECRET_KEY is required")

    expected_signature = hmac.new(
        self.secret_key.encode('utf-8'),  # ✅ CORRECT
        payload,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)
```

### 2. Updated Environment Configuration

**File**: `.env`

#### Before (Incorrect):
```bash
PAYSTACK_SECRET_KEY=sk_test_xxxxx
PAYSTACK_PUBLIC_KEY=pk_test_xxxxx
PAYSTACK_WEBHOOK_SECRET=sk_test_xxxxx  # ❌ WRONG - Not used by Paystack
```

#### After (Correct):
```bash
# The SECRET_KEY is used for both API calls AND webhook signature verification
PAYSTACK_SECRET_KEY=sk_test_xxxxx
PAYSTACK_PUBLIC_KEY=pk_test_xxxxx
# Removed PAYSTACK_WEBHOOK_SECRET ✅
```

---

## How Paystack Webhook Verification Works

### Step-by-Step Process

1. **Paystack sends webhook**:
   ```http
   POST /webhooks/paystack HTTP/1.1
   Content-Type: application/json
   x-paystack-signature: abc123def456...

   {"event": "charge.success", "data": {...}}
   ```

2. **Your server receives the request**:
   - Extract signature from `x-paystack-signature` header
   - Get raw request body (as bytes)

3. **Compute expected signature**:
   ```python
   expected_signature = hmac.new(
       PAYSTACK_SECRET_KEY.encode('utf-8'),
       raw_body,
       hashlib.sha512
   ).hexdigest()
   ```

4. **Compare signatures**:
   ```python
   if hmac.compare_digest(expected_signature, received_signature):
       # Valid webhook from Paystack ✅
   else:
       # Invalid/forged webhook ❌
   ```

---

## Why This Matters

### Security Implications

**Without proper verification**:
- Attackers could send fake "payment successful" webhooks
- Subscriptions could be activated without payment
- Money could be lost through fraudulent activations

**With correct verification**:
- Only Paystack can send valid webhooks (they have your secret key)
- Attackers cannot forge signatures without the secret key
- Your system is protected against webhook spoofing

---

## Testing

### Verification Test Results

```bash
✅ PaystackService imported successfully
✅ verify_webhook_signature method exists
✅ Correctly validates valid signatures
✅ Correctly rejects invalid signatures
```

### Manual Testing

#### Generate Valid Signature (Python):
```python
import hmac
import hashlib

secret_key = "sk_test_your_secret_key"
payload = b'{"event":"charge.success","data":{"reference":"test123"}}'

signature = hmac.new(
    secret_key.encode('utf-8'),
    payload,
    hashlib.sha512
).hexdigest()

print(f"Signature: {signature}")
```

#### Test Webhook Endpoint:
```bash
# With valid signature
curl -X POST http://localhost:8004/api/v1/webhooks/paystack \
  -H "Content-Type: application/json" \
  -H "x-paystack-signature: <computed_signature>" \
  -d '{"event":"charge.success","data":{"reference":"test123"}}'

# Response: 200 OK - Webhook processed

# With invalid signature
curl -X POST http://localhost:8004/api/v1/webhooks/paystack \
  -H "Content-Type: application/json" \
  -H "x-paystack-signature: invalid_signature" \
  -d '{"event":"charge.success","data":{"reference":"test123"}}'

# Response: 400 Bad Request - Invalid webhook signature
```

---

## References

### Paystack Documentation

1. **Webhook Documentation**: https://paystack.com/docs/payments/webhooks/
2. **Signature Verification**: Uses HMAC SHA512 with secret key
3. **Security Best Practices**: https://support.paystack.com/en/articles/2123458

### Implementation Examples from Paystack Community

**PHP**:
```php
$signature = $_SERVER['HTTP_X_PAYSTACK_SIGNATURE'];
$body = file_get_contents('php://input');
$computed = hash_hmac('sha512', $body, $secret_key);

if ($signature === $computed) {
    // Valid webhook
}
```

**Node.js**:
```javascript
const crypto = require('crypto');
const signature = req.headers['x-paystack-signature'];
const hash = crypto
    .createHmac('sha512', secretKey)
    .update(JSON.stringify(req.body))
    .digest('hex');

if (hash === signature) {
    // Valid webhook
}
```

**Go**:
```go
import "crypto/hmac"
import "crypto/sha512"

signature := r.Header.Get("x-paystack-signature")
h := hmac.New(sha512.New, []byte(secretKey))
h.Write(body)
computed := hex.EncodeToString(h.Sum(nil))

if hmac.Equal([]byte(signature), []byte(computed)) {
    // Valid webhook
}
```

---

## Migration Checklist

If you had `PAYSTACK_WEBHOOK_SECRET` configured:

- [x] Remove `PAYSTACK_WEBHOOK_SECRET` from `.env`
- [x] Remove `self.webhook_secret` from `PaystackService.__init__`
- [x] Update `verify_webhook_signature` to use `self.secret_key`
- [x] Test webhook signature verification
- [x] Update documentation

---

## Key Differences: Secret Key vs Public Key

| Key Type | Purpose | Used For | Secure? |
|----------|---------|----------|---------|
| **Secret Key** | Server-side operations | API calls, webhook verification | ✅ Keep private |
| **Public Key** | Client-side operations | JavaScript SDK, embedded forms | ⚠️ Can be public |

**Important**:
- **NEVER** expose your secret key in client-side code
- **ALWAYS** use secret key for webhook verification
- **ALWAYS** use public key for frontend integrations

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Using Public Key for Webhooks
```python
# WRONG - Public key cannot verify signatures
expected_signature = hmac.new(
    public_key.encode('utf-8'),  # ❌
    payload,
    hashlib.sha512
).hexdigest()
```

### ❌ Mistake 2: Not Verifying Signatures
```python
# WRONG - Accepting all webhooks without verification
@router.post("/webhooks/paystack")
async def handle_webhook(data: dict):
    # Process without verification ❌
    process_payment(data)
```

### ❌ Mistake 3: Using Wrong Hash Algorithm
```python
# WRONG - Paystack uses SHA512, not SHA256
expected_signature = hmac.new(
    secret_key.encode('utf-8'),
    payload,
    hashlib.sha256  # ❌ Should be sha512
).hexdigest()
```

### ✅ Correct Implementation
```python
# CORRECT
def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
    expected_signature = hmac.new(
        self.secret_key.encode('utf-8'),  # ✅ Secret key
        payload,                           # ✅ Raw bytes
        hashlib.sha512                    # ✅ SHA512
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)  # ✅ Constant-time comparison
```

---

## Summary

### What Changed
- Removed `PAYSTACK_WEBHOOK_SECRET` environment variable
- Updated webhook verification to use `PAYSTACK_SECRET_KEY`
- Added documentation explaining Paystack's signature verification

### Why It Matters
- Fixes incorrect configuration that would have failed in production
- Aligns with Paystack's official documentation
- Ensures proper webhook security

### Impact
- ✅ Webhooks will now verify correctly
- ✅ No separate webhook secret needed
- ✅ Simpler configuration (one less environment variable)
- ✅ Follows Paystack best practices

---

**Fix Status**: ✅ **COMPLETE**
**Testing Status**: ✅ **VERIFIED**
**Documentation Status**: ✅ **UPDATED**
