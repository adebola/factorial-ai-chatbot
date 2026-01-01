# Admin Module Recommendations for Billing Management

## Overview
This document outlines recommendations for building an admin module to handle manual subscription management, offline payments, and administrative billing operations.

---

## Immediate Solution: Manual Subscription Extension

### Using the Script

**Location**: `billing-service/manual_subscription_extension.py`

**Usage**:
```bash
cd billing-service
python manual_subscription_extension.py <tenant_id>
```

**Example**:
```bash
python manual_subscription_extension.py a72627cd-0169-434a-9ce1-a694709e329e
```

**What the Script Does** (Maintains Data Integrity):
1. ✅ **Finds subscription**: Retrieves active/expired subscription for tenant
2. ✅ **Creates payment record**: Adds BANK_TRANSFER payment with COMPLETED status
3. ✅ **Extends subscription**: Updates period dates and activates subscription
4. ✅ **Generates invoice**: Creates invoice and links to payment
5. ✅ **Audit trail**: Logs change in subscription_changes table
6. ✅ **Interactive**: Confirms all details before processing

**Data Integrity Features**:
- Creates proper payment record (not just updates subscription)
- Links payment → invoice → subscription correctly
- Maintains audit trail
- Uses proper transaction types and payment methods
- Generates unique invoice numbers

---

## Future Admin Module Design

### 1. API Endpoints to Build

#### a. Manual Payment Processing
```python
# billing-service/app/api/admin.py

@router.post("/admin/payments/manual")
async def create_manual_payment(
    payment_data: ManualPaymentRequest,
    admin_claims: AdminTokenClaims = Depends(validate_admin_token),  # Admin-only
    db: Session = Depends(get_db)
):
    """
    Create manual payment for offline transactions.

    Supports:
    - Bank transfers
    - Cash payments
    - Check payments
    - Other offline methods
    """
    pass
```

**Request Schema**:
```python
class ManualPaymentRequest(BaseModel):
    tenant_id: str
    subscription_id: str
    amount: Decimal
    payment_method: PaymentMethod  # bank_transfer, cash, check, etc.
    payment_date: datetime
    reference_number: Optional[str]  # Bank transfer reference, check number, etc.
    notes: str
    should_extend_subscription: bool = True
    extension_days: int = 30
```

#### b. Subscription Override
```python
@router.post("/admin/subscriptions/{subscription_id}/override")
async def override_subscription(
    subscription_id: str,
    override_data: SubscriptionOverrideRequest,
    admin_claims: AdminTokenClaims = Depends(validate_admin_token),
    db: Session = Depends(get_db)
):
    """
    Override subscription settings for special cases.

    Allows:
    - Custom expiration dates
    - Trial extensions
    - Plan changes without payment
    - Usage limit overrides
    """
    pass
```

#### c. Invoice Generation
```python
@router.post("/admin/invoices/generate")
async def generate_invoice_manually(
    invoice_data: ManualInvoiceRequest,
    admin_claims: AdminTokenClaims = Depends(validate_admin_token),
    db: Session = Depends(get_db)
):
    """
    Generate invoice for custom charges.

    Use cases:
    - Retroactive invoices
    - Custom service charges
    - Adjusted amounts
    """
    pass
```

#### d. Subscription History & Audit
```python
@router.get("/admin/subscriptions/{subscription_id}/history")
async def get_subscription_history(
    subscription_id: str,
    admin_claims: AdminTokenClaims = Depends(validate_admin_token),
    db: Session = Depends(get_db)
):
    """
    Get complete subscription history including:
    - All payments
    - All invoices
    - All plan changes
    - All manual interventions
    - Audit trail
    """
    pass
```

---

### 2. Admin Authentication & Authorization

**Recommendation**: Add role-based access control (RBAC)

```python
# app/services/dependencies.py

class AdminTokenClaims(TokenClaims):
    """Extended token claims for admin users"""
    role: str  # 'admin', 'finance', 'support'
    permissions: List[str]  # ['billing:write', 'subscription:override', etc.]


def validate_admin_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AdminTokenClaims:
    """Validate admin-only access"""
    claims = validate_token(credentials)

    if claims.role not in ['admin', 'finance']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return AdminTokenClaims(**claims.dict())
```

**Roles**:
- **Super Admin**: Full access (all operations)
- **Finance Admin**: Manual payments, invoices, refunds
- **Support Admin**: View-only access, trial extensions
- **Read-Only Admin**: View billing data, generate reports

---

### 3. Audit Trail Enhancements

**Current**: `subscription_changes` table logs changes

**Recommendation**: Add comprehensive admin actions audit table

```sql
CREATE TABLE admin_actions (
    id TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL,
    admin_email TEXT NOT NULL,
    action_type TEXT NOT NULL,  -- 'manual_payment', 'subscription_override', 'refund', etc.
    target_type TEXT NOT NULL,  -- 'subscription', 'payment', 'invoice'
    target_id TEXT NOT NULL,
    before_state JSONB,  -- State before change
    after_state JSONB,   -- State after change
    reason TEXT,         -- Why admin took this action
    ip_address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Log Every Admin Action**:
```python
def log_admin_action(
    admin_user_id: str,
    admin_email: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before_state: dict,
    after_state: dict,
    reason: str,
    ip_address: str,
    db: Session
):
    """Log admin action for compliance and audit"""
    pass
```

---

### 4. Frontend Admin Dashboard

**Recommended Features**:

#### a. Subscription Management View
- Search subscriptions by tenant, email, status
- View subscription details, payment history, invoices
- Quick actions: Extend, Override, Cancel, Refund

#### b. Manual Payment Form
```
┌─────────────────────────────────────────┐
│ Record Manual Payment                   │
├─────────────────────────────────────────┤
│ Tenant: [Search tenant...]              │
│ Subscription: [Auto-populated]          │
│ Payment Method: [Bank Transfer ▼]       │
│ Amount: [50,000.00] NGN                  │
│ Payment Date: [2025-12-31]              │
│ Reference: [TRF-20251231-001]           │
│ Notes: [Customer paid via bank...]      │
│                                          │
│ ☑ Extend subscription by [30] days      │
│ ☑ Generate invoice                      │
│ ☑ Send confirmation email               │
│                                          │
│ [Cancel]  [Preview]  [Submit Payment]   │
└─────────────────────────────────────────┘
```

#### c. Bulk Operations
- Import CSV of manual payments
- Batch subscription extensions
- Bulk invoice generation

#### d. Reports
- Manual payments report (by date, method)
- Subscription expirations (upcoming 7/30 days)
- Revenue report (online vs offline)
- Admin actions audit report

---

### 5. Notification System

**When Admin Extends Subscription**, automatically send:

1. **Customer Email**:
   ```
   Subject: Your Subscription Has Been Extended

   Dear [Customer Name],

   Your [Plan Name] subscription has been extended.

   Payment Details:
   - Amount: 50,000 NGN
   - Payment Method: Bank Transfer
   - Reference: TRF-20251231-001

   New Subscription Period:
   - Start: January 1, 2026
   - End: January 31, 2026

   Invoice: [Download PDF]

   Thank you for your payment!
   ```

2. **Internal Notification** (Slack/Email):
   ```
   [ADMIN ACTION] Manual Payment Processed

   Admin: admin@example.com
   Tenant: Company Name
   Amount: 50,000 NGN
   Method: Bank Transfer
   Extension: 30 days
   ```

---

### 6. Data Integrity Checklist

Every manual operation MUST:

- [ ] Create payment record with correct status
- [ ] Link payment to subscription
- [ ] Update subscription period dates
- [ ] Generate invoice and link to payment
- [ ] Log in subscription_changes table
- [ ] Log in admin_actions table (future)
- [ ] Validate amount matches plan cost (with override option)
- [ ] Check for duplicate payments (same reference)
- [ ] Ensure atomic transaction (rollback on error)
- [ ] Send notification emails

---

### 7. Recommended Implementation Phases

#### Phase 1: Core Admin API (Week 1-2)
- [ ] Admin authentication/authorization
- [ ] Manual payment endpoint
- [ ] Subscription override endpoint
- [ ] Admin actions audit table

#### Phase 2: Admin Dashboard UI (Week 3-4)
- [ ] Subscription search and view
- [ ] Manual payment form
- [ ] Payment history view
- [ ] Invoice generation

#### Phase 3: Automation & Enhancements (Week 5-6)
- [ ] Email notifications
- [ ] Bulk operations
- [ ] Reports and analytics
- [ ] CSV import/export

#### Phase 4: Advanced Features (Week 7-8)
- [ ] Refund processing
- [ ] Credit notes
- [ ] Payment plans
- [ ] Custom pricing

---

### 8. Security Considerations

**Critical**:
1. **Admin-only access**: Never expose to regular users
2. **IP whitelisting**: Restrict admin endpoints to office IPs
3. **MFA**: Require multi-factor auth for admin users
4. **Audit everything**: Log every admin action
5. **Approval workflow**: Require dual approval for high-value operations
6. **Rate limiting**: Prevent abuse of admin endpoints

**Example IP Whitelisting**:
```python
ADMIN_ALLOWED_IPS = ["192.168.1.100", "10.0.0.50"]  # Office IPs

@router.post("/admin/payments/manual")
async def create_manual_payment(
    request: Request,
    admin_claims: AdminTokenClaims = Depends(validate_admin_token),
    db: Session = Depends(get_db)
):
    # Check IP whitelist
    client_ip = request.client.host
    if client_ip not in ADMIN_ALLOWED_IPS:
        logger.warning(f"Admin access attempt from unauthorized IP: {client_ip}")
        raise HTTPException(status_code=403, detail="Access denied")

    # ... process payment
```

---

### 9. Testing Recommendations

**Manual Payment Tests**:
```python
def test_manual_payment_creates_all_records():
    """Test that manual payment creates payment, extends subscription, and generates invoice"""
    # Given: Expired subscription
    # When: Admin records manual payment
    # Then: Payment record exists, subscription extended, invoice generated, audit logged

def test_manual_payment_prevents_duplicates():
    """Test that duplicate reference numbers are rejected"""
    # Given: Existing payment with reference "TRF-001"
    # When: Admin tries to create another payment with "TRF-001"
    # Then: Error raised

def test_manual_payment_validates_amount():
    """Test that payment amount is validated against plan cost"""
    # Given: Basic plan (50,000 NGN)
    # When: Admin records 40,000 NGN payment without override
    # Then: Warning or error raised

def test_manual_payment_audit_trail():
    """Test that admin actions are logged"""
    # Given: Admin records manual payment
    # When: Check admin_actions table
    # Then: Action logged with before/after state
```

---

## Immediate Action Items

**For Your Current Client**:

1. **Get tenant ID**: Retrieve from database or frontend
   ```sql
   SELECT id, name, domain FROM tenants WHERE name ILIKE '%company%';
   ```

2. **Run the script**:
   ```bash
   python manual_subscription_extension.py <tenant_id>
   ```

3. **Verify**:
   ```sql
   -- Check payment created
   SELECT * FROM payments WHERE tenant_id = '<tenant_id>' ORDER BY created_at DESC LIMIT 1;

   -- Check subscription extended
   SELECT status, current_period_end FROM subscriptions WHERE tenant_id = '<tenant_id>';

   -- Check invoice generated
   SELECT * FROM invoices WHERE tenant_id = '<tenant_id>' ORDER BY created_at DESC LIMIT 1;
   ```

4. **Send confirmation email**: Manually email customer with invoice

5. **Document**: Note payment details in your records for accounting

---

## Questions to Consider for Admin Module

1. **Who should have admin access?**
   - Just you?
   - Finance team?
   - Customer support?

2. **Approval workflow needed?**
   - Should high-value manual payments require dual approval?
   - Email notifications to finance team?

3. **Compliance requirements?**
   - Export audit logs for accounting?
   - Tax reporting integration?

4. **Offline payment frequency?**
   - If frequent, prioritize admin dashboard
   - If rare, script is sufficient for now

---

## Conclusion

**For Now**: Use the `manual_subscription_extension.py` script - it maintains complete data integrity.

**For Future**: Build the admin module following the recommendations above when you have multiple admins or frequent offline payments.

The script creates all necessary records (payment, subscription update, invoice, audit trail) while maintaining referential integrity. This is safe for production use.
