-- ========================================================
-- Fix Trial Period Calculation Issue
-- ========================================================
--
-- Purpose: Fix TRIALING subscriptions where current_period_end
--          is incorrectly set to trial_ends_at + 30 days
--
-- Issue: TRIALING subscriptions show "Renews in 44 days" instead
--        of "Trial ends in 14 days" because current_period_end
--        was calculated as trial_ends_at + 30 days
--
-- Fix: Update current_period_end to equal trial_ends_at for
--      TRIALING subscriptions
--
-- Run this AFTER deploying the code fix to subscription_service.py
--
-- ========================================================

-- Step 1: DIAGNOSTIC - Show affected subscriptions
-- This query identifies TRIALING subscriptions that need fixing
SELECT
    id,
    tenant_id,
    status,
    trial_starts_at,
    trial_ends_at,
    current_period_start,
    current_period_end,
    starts_at,
    ends_at,
    EXTRACT(DAY FROM (trial_ends_at - trial_starts_at)) as trial_days,
    EXTRACT(DAY FROM (current_period_end - trial_starts_at)) as period_days_from_start,
    EXTRACT(DAY FROM (current_period_end - trial_ends_at)) as days_after_trial
FROM subscriptions
WHERE status = 'trialing'
  AND trial_ends_at IS NOT NULL
  AND current_period_end > trial_ends_at
ORDER BY trial_ends_at;

-- Expected result: Subscriptions with trial_days=14 but period_days_from_start=44


-- Step 2: Count affected records
SELECT COUNT(*) as affected_subscriptions_count
FROM subscriptions
WHERE status = 'trialing'
  AND trial_ends_at IS NOT NULL
  AND current_period_end > trial_ends_at;


-- Step 3: BACKUP (Recommended)
-- Create a backup of affected subscriptions before making changes
-- Uncomment and run if you want a backup table

/*
CREATE TABLE subscriptions_backup_trial_fix AS
SELECT *
FROM subscriptions
WHERE status = 'trialing'
  AND trial_ends_at IS NOT NULL
  AND current_period_end > trial_ends_at;

-- Verify backup
SELECT COUNT(*) as backup_count FROM subscriptions_backup_trial_fix;
*/


-- Step 4: FIX - Update TRIALING subscriptions
-- This sets current_period_end and ends_at to match trial_ends_at
-- Also fixes current_period_start to match trial_starts_at

BEGIN;  -- Start transaction

UPDATE subscriptions
SET
    current_period_end = trial_ends_at,
    current_period_start = trial_starts_at,
    ends_at = trial_ends_at,
    updated_at = NOW()
WHERE status = 'trialing'
  AND trial_ends_at IS NOT NULL
  AND current_period_end > trial_ends_at;

-- Show what we updated
SELECT COUNT(*) as updated_count
FROM subscriptions
WHERE status = 'trialing'
  AND trial_ends_at IS NOT NULL
  AND current_period_end = trial_ends_at;

COMMIT;  -- Commit transaction
-- If something went wrong, run ROLLBACK; instead


-- Step 5: VERIFICATION - Confirm all TRIALING subscriptions are fixed
-- After the fix, all TRIALING subscriptions should have:
-- - current_period_end = trial_ends_at
-- - current_period_start = trial_starts_at
-- - ends_at = trial_ends_at

SELECT
    COUNT(*) as total_trialing,
    COUNT(CASE WHEN current_period_end = trial_ends_at THEN 1 END) as correct_period_end,
    COUNT(CASE WHEN current_period_start = trial_starts_at THEN 1 END) as correct_period_start,
    COUNT(CASE WHEN ends_at = trial_ends_at THEN 1 END) as correct_ends_at,
    COUNT(CASE
        WHEN current_period_end = trial_ends_at
         AND current_period_start = trial_starts_at
         AND ends_at = trial_ends_at
        THEN 1
    END) as fully_correct
FROM subscriptions
WHERE status = 'trialing'
  AND trial_ends_at IS NOT NULL;

-- Expected: total_trialing = correct_period_end = correct_period_start = correct_ends_at = fully_correct


-- Step 6: SAMPLE CHECK - View a few fixed subscriptions
SELECT
    id,
    tenant_id,
    status,
    trial_starts_at,
    trial_ends_at,
    current_period_start,
    current_period_end,
    ends_at,
    EXTRACT(DAY FROM (trial_ends_at - trial_starts_at)) as trial_days,
    EXTRACT(DAY FROM (current_period_end - trial_starts_at)) as total_period_days
FROM subscriptions
WHERE status = 'trialing'
  AND trial_ends_at IS NOT NULL
ORDER BY created_at DESC
LIMIT 5;

-- Expected: trial_days = total_period_days (should both be 14)


-- ========================================================
-- Optional: Clean up backup table after verification
-- ========================================================
-- Uncomment after confirming the fix works correctly

/*
DROP TABLE IF EXISTS subscriptions_backup_trial_fix;
*/


-- ========================================================
-- NOTES
-- ========================================================
--
-- 1. This script is idempotent - safe to run multiple times
-- 2. Always test on staging/dev database first
-- 3. Run during low-traffic period if possible
-- 4. Monitor application logs after running
-- 5. New subscriptions created after code deployment will
--    have correct values automatically
--
-- ========================================================
