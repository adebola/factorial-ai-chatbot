-- ============================================================================
-- Manual Subscription Extension for Offline Payments (Production-Safe SQL)
-- ============================================================================
--
-- This SQL script extends a subscription after receiving offline payment
-- (bank transfer, cash, etc.) while maintaining complete data integrity.
--
-- USAGE:
--   1. Replace <TENANT_ID> with actual tenant UUID
--   2. Replace <PAYMENT_AMOUNT> with actual amount (e.g., 50000.00)
--   3. Replace <PAYMENT_NOTES> with payment details
--   4. Review the summary SELECT queries before running INSERTs/UPDATEs
--   5. Execute in a transaction (BEGIN; ... COMMIT;)
--
-- IMPORTANT: Run this entire script in a single transaction!
-- ============================================================================

BEGIN;

-- ============================================================================
-- STEP 0: Set Variables (MODIFY THESE)
-- ============================================================================
-- Replace these values before running:
\set tenant_id '\'17b5ed30-8198-46c0-9e76-9b21362dad92\''
\set payment_amount 50000.00
\set payment_notes '\'Bank transfer - Manual payment recorded by admin\''
\set extension_days 30

-- ============================================================================
-- STEP 1: Review Current Subscription Details
-- ============================================================================
\echo '============================================================================'
\echo 'STEP 1: Current Subscription Details'
\echo '============================================================================'

SELECT
    s.id as subscription_id,
    s.tenant_id,
    s.user_full_name as tenant_contact,
    s.user_email as contact_email,
    s.status,
    p.name as plan_name,
    s.billing_cycle,
    s.current_period_start,
    s.current_period_end,
    CASE
        WHEN s.status = 'expired' THEN 'Will start from today'
        ELSE 'Will extend from current period end'
    END as extension_strategy
FROM subscriptions s
JOIN plans p ON s.plan_id = p.id
WHERE s.tenant_id = :tenant_id
    AND s.status IN ('active', 'expired', 'trialing')
ORDER BY s.created_at DESC
LIMIT 1;

-- ============================================================================
-- STEP 2: Create Payment Record
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'STEP 2: Creating Payment Record'
\echo '============================================================================'

WITH subscription_info AS (
    SELECT id, tenant_id
    FROM subscriptions
    WHERE tenant_id = :tenant_id
        AND status IN ('active', 'expired', 'trialing')
    ORDER BY created_at DESC
    LIMIT 1
),
new_payment AS (
    INSERT INTO payments (
        id,
        subscription_id,
        tenant_id,
        amount,
        currency,
        status,
        payment_method,
        transaction_type,
        paystack_reference,
        description,
        created_at,
        processed_at,
        gateway_response,
        refunded_amount
    )
    SELECT
        gen_random_uuid()::text,
        si.id,
        si.tenant_id,
        :payment_amount,
        'NGN',
        'completed',
        'bank_transfer',
        'renewal',
        'manual_banktransfer_' || si.id || '_' || to_char(NOW(), 'YYYYMMDDHH24MISS'),
        :payment_notes,
        NOW(),
        NOW(),
        jsonb_build_object(
            'payment_method', 'manual_bank_transfer',
            'processed_by', 'admin',
            'notes', :payment_notes,
            'timestamp', NOW()
        ),
        0.00
    FROM subscription_info si
    RETURNING id, paystack_reference, amount, subscription_id
)
SELECT
    id as payment_id,
    paystack_reference,
    amount,
    subscription_id,
    '✅ Payment record created' as status
FROM new_payment;

-- ============================================================================
-- STEP 3: Extend Subscription
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'STEP 3: Extending Subscription Period'
\echo '============================================================================'

WITH subscription_info AS (
    SELECT
        id,
        current_period_end,
        status,
        CASE
            WHEN status = 'expired' THEN NOW()
            ELSE current_period_end
        END as new_period_start
    FROM subscriptions
    WHERE tenant_id = :tenant_id
        AND status IN ('active', 'expired', 'trialing')
    ORDER BY created_at DESC
    LIMIT 1
),
updated_subscription AS (
    UPDATE subscriptions s
    SET
        current_period_start = si.new_period_start,
        current_period_end = si.new_period_start + (interval '1 day' * :extension_days),
        ends_at = si.new_period_start + (interval '1 day' * :extension_days),
        status = 'active',
        updated_at = NOW()
    FROM subscription_info si
    WHERE s.id = si.id
    RETURNING
        s.id,
        s.status,
        s.current_period_start,
        s.current_period_end
)
SELECT
    id as subscription_id,
    status,
    current_period_start as new_period_start,
    current_period_end as new_period_end,
    'Subscription extended' as status_message
FROM updated_subscription;

-- ============================================================================
-- STEP 4: Generate Invoice
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'STEP 4: Generating Invoice'
\echo '============================================================================'

WITH last_invoice AS (
    SELECT
        COALESCE(
            MAX(CAST(SPLIT_PART(invoice_number, '-', 3) AS INTEGER)),
            0
        ) as last_number
    FROM invoices
    WHERE invoice_number LIKE 'INV-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-%'
),
payment_info AS (
    SELECT
        p.id as payment_id,
        p.subscription_id,
        p.tenant_id,
        p.amount,
        s.current_period_start,
        s.current_period_end
    FROM payments p
    JOIN subscriptions s ON p.subscription_id = s.id
    WHERE p.tenant_id = :tenant_id
        AND p.payment_method = 'bank_transfer'
        AND p.status = 'completed'
    ORDER BY p.created_at DESC
    LIMIT 1
),
new_invoice AS (
    INSERT INTO invoices (
        id,
        invoice_number,
        subscription_id,
        tenant_id,
        subtotal,
        tax_amount,
        total_amount,
        currency,
        status,
        period_start,
        period_end,
        due_date,
        notes,
        created_at,
        paid_at
    )
    SELECT
        gen_random_uuid()::text,
        'INV-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' || LPAD((li.last_number + 1)::text, 4, '0'),
        pi.subscription_id,
        pi.tenant_id,
        pi.amount,
        0.00,
        pi.amount,
        'NGN',
        'completed',
        pi.current_period_start,
        pi.current_period_end,
        NOW(),
        'Manual payment - Bank Transfer',
        NOW(),
        NOW()
    FROM payment_info pi, last_invoice li
    RETURNING id, invoice_number, total_amount, subscription_id
)
SELECT
    id as invoice_id,
    invoice_number,
    total_amount,
    subscription_id,
    '✅ Invoice created' as status
FROM new_invoice;

-- ============================================================================
-- STEP 5: Link Payment to Invoice
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'STEP 5: Linking Payment to Invoice'
\echo '============================================================================'

WITH latest_invoice AS (
    SELECT id
    FROM invoices
    WHERE tenant_id = :tenant_id
    ORDER BY created_at DESC
    LIMIT 1
),
latest_payment AS (
    SELECT id
    FROM payments
    WHERE tenant_id = :tenant_id
        AND payment_method = 'bank_transfer'
    ORDER BY created_at DESC
    LIMIT 1
)
UPDATE payments p
SET invoice_id = i.id
FROM latest_invoice i, latest_payment lp
WHERE p.id = lp.id
RETURNING p.id as payment_id, p.invoice_id, '✅ Payment linked to invoice' as status;

-- ============================================================================
-- STEP 6: Log in Audit Trail
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'STEP 6: Logging in Audit Trail'
\echo '============================================================================'

WITH subscription_info AS (
    SELECT id, tenant_id
    FROM subscriptions
    WHERE tenant_id = :tenant_id
    ORDER BY created_at DESC
    LIMIT 1
)
INSERT INTO subscription_changes (
    id,
    subscription_id,
    tenant_id,
    change_type,
    effective_at,
    reason,
    change_metadata
)
SELECT
    gen_random_uuid()::text,
    si.id,
    si.tenant_id,
    'manual_extension',
    NOW(),
    :payment_notes,
    jsonb_build_object(
        'manual_entry', true,
        'payment_method', 'bank_transfer',
        'extension_days', :extension_days,
        'amount', :payment_amount
    )
FROM subscription_info si
RETURNING id, subscription_id, change_type, '✅ Audit trail logged' as status;

-- ============================================================================
-- STEP 7: Verification Summary
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'STEP 7: Verification Summary'
\echo '============================================================================'

SELECT * FROM (
    SELECT
        '=== PAYMENT ===' as section,
        p.id as record_id,
        p.paystack_reference as reference,
        p.amount::text as amount,
        p.status::text as status,
        p.payment_method::text as extra_info
    FROM payments p
    WHERE p.tenant_id = :tenant_id
    ORDER BY p.created_at DESC
    LIMIT 1
) payment_info

UNION ALL

SELECT * FROM (
    SELECT
        '=== INVOICE ===' as section,
        i.id as record_id,
        i.invoice_number as reference,
        i.total_amount::text as amount,
        i.status::text as status,
        'Invoice' as extra_info
    FROM invoices i
    WHERE i.tenant_id = :tenant_id
    ORDER BY i.created_at DESC
    LIMIT 1
) invoice_info

UNION ALL

SELECT * FROM (
    SELECT
        '=== SUBSCRIPTION ===' as section,
        s.id as record_id,
        'N/A' as reference,
        s.amount::text as amount,
        s.status::text as status,
        s.billing_cycle::text as extra_info
    FROM subscriptions s
    WHERE s.tenant_id = :tenant_id
    ORDER BY s.created_at DESC
    LIMIT 1
) subscription_info;

-- ============================================================================
-- FINAL: Display Updated Subscription Details
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'FINAL: Updated Subscription Details'
\echo '============================================================================'

SELECT
    s.id as subscription_id,
    s.status,
    p.name as plan_name,
    s.current_period_start as period_start,
    s.current_period_end as period_end,
    s.user_email,
    '✅ Subscription successfully extended!' as result
FROM subscriptions s
JOIN plans p ON s.plan_id = p.id
WHERE s.tenant_id = :tenant_id
ORDER BY s.created_at DESC
LIMIT 1;

-- ============================================================================
-- COMMIT TRANSACTION
-- ============================================================================
\echo ''
\echo '============================================================================'
\echo 'Review the output above. If everything looks correct, type COMMIT;'
\echo 'If anything looks wrong, type ROLLBACK;'
\echo '============================================================================'

-- Uncomment the line below to auto-commit (or run manually after review)
-- COMMIT;
