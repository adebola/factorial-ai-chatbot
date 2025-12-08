-- Fix subscription ends_at values to match current_period_end
-- This fixes a bug where ends_at retained the trial period calculation (45 days)
-- instead of being updated to match the new billing period (30 or 365 days)
--
-- Run this script on the billing_db database
-- Date: 2025-11-27
-- Bug fix for: NULL user fields and incorrect ends_at calculation

-- First, check how many records will be affected
SELECT
    COUNT(*) as affected_subscriptions,
    COUNT(CASE WHEN user_email IS NULL THEN 1 END) as null_user_email_count,
    COUNT(CASE WHEN user_full_name IS NULL THEN 1 END) as null_user_full_name_count,
    COUNT(CASE WHEN ends_at != current_period_end THEN 1 END) as mismatched_ends_at_count
FROM subscriptions
WHERE status IN ('active', 'trialing');

-- Show the records that will be updated
SELECT
    id,
    tenant_id,
    status,
    billing_cycle,
    user_email,
    user_full_name,
    starts_at,
    ends_at,
    current_period_end,
    EXTRACT(DAY FROM (ends_at - starts_at)) as current_ends_at_days,
    EXTRACT(DAY FROM (current_period_end - starts_at)) as correct_period_days
FROM subscriptions
WHERE status IN ('active', 'trialing')
  AND (ends_at != current_period_end OR user_email IS NULL OR user_full_name IS NULL)
ORDER BY starts_at DESC;

-- Update ends_at to match current_period_end for active/trialing subscriptions
-- This fixes subscriptions where ends_at was not updated during trial-to-paid conversion
UPDATE subscriptions
SET ends_at = current_period_end
WHERE status IN ('active', 'trialing')
  AND ends_at != current_period_end;

-- Verify the fix
SELECT
    COUNT(*) as total_subscriptions,
    COUNT(CASE WHEN ends_at = current_period_end THEN 1 END) as matching_dates,
    COUNT(CASE WHEN ends_at != current_period_end THEN 1 END) as mismatched_dates
FROM subscriptions
WHERE status IN ('active', 'trialing');

-- Show updated records
SELECT
    id,
    tenant_id,
    status,
    billing_cycle,
    user_email,
    user_full_name,
    starts_at,
    ends_at,
    current_period_end,
    EXTRACT(DAY FROM (ends_at - starts_at)) as ends_at_days,
    EXTRACT(DAY FROM (current_period_end - starts_at)) as period_days
FROM subscriptions
WHERE status IN ('active', 'trialing')
ORDER BY starts_at DESC
LIMIT 10;

-- Note: user_email and user_full_name cannot be fixed via SQL
-- They must be populated by the application during plan switches
-- Future plan switches will now correctly populate these fields
