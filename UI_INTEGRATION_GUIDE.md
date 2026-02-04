# UI Integration Guide: Manual Subscription Extension

## Quick Reference

This guide provides the essential information needed to integrate the manual subscription extension feature into the admin UI.

## API Endpoints

### 1. Get Tenants for Dropdown

**Endpoint**: `GET /api/v1/admin/tenants/dropdown`

**Base URL**: `http://localhost:8080` (via gateway)

**Authentication**: Bearer token (SYSTEM_ADMIN role required)

**Request Headers**:
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Response** (200 OK):
```json
[
  {
    "id": "017f4c3f-42a8-4f82-aee8-601318e4f4ed",
    "name": "Acme Corporation"
  },
  {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "name": "Beta Industries"
  },
  {
    "id": "987fcdeb-51a2-4321-9876-543210fedcba",
    "name": "Gamma Solutions"
  }
]
```

**Features**:
- Returns only active tenants
- Sorted alphabetically by name
- Simple structure optimized for dropdowns
- No pagination (returns all active tenants)

**Error Responses**:
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: User doesn't have SYSTEM_ADMIN role

---

### 2. Create Manual Payment & Extend Subscription

**Endpoint**: `POST /api/v1/admin/billing/payments/manual`

**Base URL**: `http://localhost:8080` (via gateway)

**Authentication**: Bearer token (SYSTEM_ADMIN role required)

**Request Headers**:
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body**:
```json
{
  "tenant_id": "017f4c3f-42a8-4f82-aee8-601318e4f4ed",
  "subscription_id": "b06070dd-e8e7-4ba6-8f8c-e6face5612c8",
  "amount": 50000.00,
  "payment_method": "bank_transfer",
  "reference_number": "TRF-20260203-001",
  "notes": "Bank transfer received on Feb 3, 2026",
  "should_extend_subscription": true,
  "extension_days": 30,
  "send_confirmation_email": true
}
```

**Field Descriptions**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tenant_id` | string (UUID) | Yes | Tenant ID from dropdown |
| `subscription_id` | string (UUID) | Yes | Tenant's subscription ID |
| `amount` | number (decimal) | Yes | Payment amount received |
| `payment_method` | string | Yes | Payment method: "bank_transfer", "cash", "check", etc. |
| `reference_number` | string | No | Bank reference or transaction ID |
| `notes` | string | Yes | Description of the payment |
| `should_extend_subscription` | boolean | No | Whether to extend subscription (default: true) |
| `extension_days` | integer | No | Number of days to extend (default: 30) |
| `send_confirmation_email` | boolean | No | Send email to tenant (default: true) |

**Response** (200 OK):
```json
{
  "success": true,
  "payment_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "invoice_number": "INV-20260203-0001",
  "subscription_status": "active",
  "new_period_end": "2026-03-05T12:00:00Z",
  "message": "Manual payment recorded and subscription extended"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request body or missing required fields
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: User doesn't have SYSTEM_ADMIN role
- `404 Not Found`: Subscription or tenant not found
- `422 Unprocessable Entity`: Validation errors (e.g., negative amount)

---

## UI Workflow

### Step-by-Step Implementation

```javascript
// 1. When page loads, fetch tenants for dropdown
async function loadTenants() {
  const response = await fetch('http://localhost:8080/api/v1/admin/tenants/dropdown', {
    headers: {
      'Authorization': `Bearer ${adminToken}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error('Failed to load tenants');
  }

  const tenants = await response.json();
  // Populate dropdown with tenants
  // Each option: value = tenant.id, text = tenant.name
  return tenants;
}

// 2. When tenant is selected, optionally get their subscription
async function getTenantSubscription(tenantId) {
  const response = await fetch(
    `http://localhost:8080/api/v1/admin/tenants/${tenantId}/subscription`,
    {
      headers: {
        'Authorization': `Bearer ${adminToken}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    console.warn('No subscription found for tenant');
    return null;
  }

  const data = await response.json();
  return data.subscription;
}

// 3. Submit manual payment form
async function submitManualPayment(formData) {
  const payload = {
    tenant_id: formData.tenantId,
    subscription_id: formData.subscriptionId,
    amount: parseFloat(formData.amount),
    payment_method: formData.paymentMethod,
    reference_number: formData.referenceNumber,
    notes: formData.notes,
    should_extend_subscription: formData.shouldExtend ?? true,
    extension_days: parseInt(formData.extensionDays) || 30,
    send_confirmation_email: formData.sendEmail ?? true
  };

  const response = await fetch(
    'http://localhost:8080/api/v1/admin/billing/payments/manual',
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${adminToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to process payment');
  }

  const result = await response.json();
  return result;
}

// 4. Display success message
function displaySuccess(result) {
  alert(`
    Payment recorded successfully!

    Invoice: ${result.invoice_number}
    Subscription Status: ${result.subscription_status}
    New Period End: ${new Date(result.new_period_end).toLocaleDateString()}
  `);
}
```

---

## Form Fields Recommendations

### Tenant Selection
- **Component**: Searchable dropdown/select
- **Data Source**: GET `/api/v1/admin/tenants/dropdown`
- **Display**: Tenant name
- **Value**: Tenant ID (UUID)
- **Required**: Yes

### Amount
- **Component**: Number input
- **Validation**: Positive decimal, max 2 decimal places
- **Placeholder**: "50000.00"
- **Required**: Yes

### Payment Method
- **Component**: Dropdown/select
- **Options**:
  - Bank Transfer
  - Cash
  - Check
  - Other
- **Default**: Bank Transfer
- **Required**: Yes

### Reference Number
- **Component**: Text input
- **Placeholder**: "TRF-20260203-001"
- **Max Length**: 100 characters
- **Required**: No (but recommended)

### Notes
- **Component**: Textarea
- **Placeholder**: "Bank transfer received on [date] for [purpose]"
- **Max Length**: 500 characters
- **Required**: Yes

### Extension Days
- **Component**: Number input
- **Default**: 30
- **Min**: 1
- **Max**: 365
- **Required**: No

### Send Confirmation Email
- **Component**: Checkbox
- **Default**: Checked
- **Required**: No

---

## Error Handling

```javascript
async function handleSubmit(formData) {
  try {
    // Validate form data
    if (!formData.tenantId) {
      throw new Error('Please select a tenant');
    }

    if (!formData.subscriptionId) {
      throw new Error('Subscription ID is required');
    }

    if (formData.amount <= 0) {
      throw new Error('Amount must be greater than 0');
    }

    if (!formData.notes) {
      throw new Error('Notes are required');
    }

    // Submit payment
    const result = await submitManualPayment(formData);

    // Show success
    displaySuccess(result);

    // Optionally reset form or redirect
    resetForm();

  } catch (error) {
    // Show error to user
    if (error.response) {
      // HTTP error
      const status = error.response.status;
      if (status === 401) {
        alert('Your session has expired. Please log in again.');
      } else if (status === 403) {
        alert('You do not have permission to perform this action.');
      } else if (status === 404) {
        alert('Subscription not found. Please check the tenant and try again.');
      } else {
        alert(`Error: ${error.message}`);
      }
    } else {
      // Network or other error
      alert(`Error: ${error.message}`);
    }
  }
}
```

---

## Testing the Integration

### Manual Test Steps

1. **Verify Authentication**:
   - Ensure admin user has SYSTEM_ADMIN role
   - Obtain valid Bearer token

2. **Test Tenant Dropdown**:
   ```bash
   curl -X GET http://localhost:8080/api/v1/admin/tenants/dropdown \
     -H "Authorization: Bearer <token>"
   ```
   - Should return list of active tenants
   - Verify tenants are sorted alphabetically

3. **Test Manual Payment** (with test data):
   ```bash
   curl -X POST http://localhost:8080/api/v1/admin/billing/payments/manual \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "tenant_id": "<tenant_id>",
       "subscription_id": "<subscription_id>",
       "amount": 50000.00,
       "payment_method": "bank_transfer",
       "reference_number": "TEST-001",
       "notes": "Test payment",
       "should_extend_subscription": true,
       "extension_days": 30,
       "send_confirmation_email": false
     }'
   ```

4. **Verify Results**:
   - Check payment was created in database
   - Verify subscription period was extended
   - Confirm invoice was generated
   - Check audit log in admin_actions table

---

## Common Issues & Solutions

### Issue: 401 Unauthorized
**Cause**: Missing or invalid Bearer token
**Solution**: Ensure token is valid and not expired

### Issue: 403 Forbidden
**Cause**: User doesn't have SYSTEM_ADMIN role
**Solution**: Grant SYSTEM_ADMIN role to user in database

### Issue: Empty Tenant Dropdown
**Cause**: No active tenants in system
**Solution**: Ensure tenants exist and are active (is_active = true)

### Issue: 404 Subscription Not Found
**Cause**: Invalid subscription_id or subscription doesn't belong to tenant
**Solution**: Verify subscription_id matches tenant's subscription

### Issue: CORS Error
**Cause**: Browser blocking cross-origin request
**Solution**: Ensure gateway has proper CORS configuration

---

## Database Verification

After submitting a manual payment, verify in database:

```sql
-- Check payment was created
SELECT * FROM payments
WHERE tenant_id = '<tenant_id>'
ORDER BY created_at DESC LIMIT 1;

-- Check subscription was extended
SELECT id, status, current_period_start, current_period_end
FROM subscriptions
WHERE tenant_id = '<tenant_id>';

-- Check invoice was generated
SELECT * FROM invoices
WHERE subscription_id = '<subscription_id>'
ORDER BY created_at DESC LIMIT 1;

-- Check audit trail
SELECT * FROM admin_actions
WHERE action_type = 'manual_payment'
ORDER BY created_at DESC LIMIT 1;
```

---

## Environment Configuration

| Environment | Gateway URL | Auth Server URL |
|-------------|-------------|-----------------|
| Development | http://localhost:8080 | http://localhost:9002/auth |
| Production | https://api.chatcraft.cc | https://auth.chatcraft.cc |

Replace `localhost` URLs with production URLs when deploying to production.

---

## Support

For issues or questions about the API endpoints:
1. Check MANUAL_SUBSCRIPTION_EXTENSION_IMPLEMENTATION.md for detailed documentation
2. Run test scripts:
   - `test-dropdown-endpoint.sh` - Verify endpoint existence
   - `test-manual-subscription-extension.sh` - Full integration test (requires auth)
3. Review authorization-server2 logs for authentication issues
4. Review billing-service logs for payment processing issues

---

## Status

✅ **Tenant Dropdown Endpoint**: Implemented and tested
✅ **Manual Payment Endpoint**: Verified working (already existed)
✅ **Gateway Routing**: Configured correctly
⚠️ **OAuth2 Password Grant**: Requires additional configuration
📋 **Ready for UI Integration**: Both endpoints are functional

The backend is ready for UI integration. Once OAuth2 password grant is properly configured for admin authentication, the full workflow will be operational.
