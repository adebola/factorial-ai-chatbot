-- Fix Development Database Enum Values
-- This script converts all enum types from uppercase to lowercase
-- Run this against the billing_db database in development

-- 1. Fix billingcycle enum (used in subscriptions table)
ALTER TYPE billingcycle RENAME TO billingcycle_old;
CREATE TYPE billingcycle AS ENUM ('monthly', 'yearly');
ALTER TABLE subscriptions
    ALTER COLUMN billing_cycle TYPE billingcycle
    USING LOWER(billing_cycle::text)::billingcycle;
ALTER TABLE subscriptions
    ALTER COLUMN pending_billing_cycle TYPE billingcycle
    USING LOWER(pending_billing_cycle::text)::billingcycle;
DROP TYPE billingcycle_old;

-- 2. Fix paymentstatus enum (used in payments, invoices, and refund_requests tables)
ALTER TYPE paymentstatus RENAME TO paymentstatus_old;
CREATE TYPE paymentstatus AS ENUM ('pending', 'processing', 'completed', 'failed', 'cancelled', 'refunded');
ALTER TABLE payments
    ALTER COLUMN status TYPE paymentstatus
    USING LOWER(status::text)::paymentstatus;
ALTER TABLE invoices
    ALTER COLUMN status TYPE paymentstatus
    USING LOWER(status::text)::paymentstatus;
ALTER TABLE refund_requests
    ALTER COLUMN status TYPE paymentstatus
    USING LOWER(status::text)::paymentstatus;
DROP TYPE paymentstatus_old;

-- 3. Fix paymentmethod enum (used in payments and payment_methods tables)
ALTER TYPE paymentmethod RENAME TO paymentmethod_old;
CREATE TYPE paymentmethod AS ENUM ('card', 'bank_transfer', 'ussd', 'qr', 'mobile_money');
ALTER TABLE payments
    ALTER COLUMN payment_method TYPE paymentmethod
    USING LOWER(payment_method::text)::paymentmethod;
ALTER TABLE payment_methods
    ALTER COLUMN type TYPE paymentmethod
    USING LOWER(type::text)::paymentmethod;
DROP TYPE paymentmethod_old;

-- 4. Fix transactiontype enum (used in payments table)
ALTER TYPE transactiontype RENAME TO transactiontype_old;
CREATE TYPE transactiontype AS ENUM ('subscription', 'upgrade', 'downgrade', 'renewal', 'refund');
ALTER TABLE payments
    ALTER COLUMN transaction_type TYPE transactiontype
    USING LOWER(transaction_type::text)::transactiontype;
DROP TYPE transactiontype_old;

-- Verify all enum values are now lowercase
SELECT 'subscriptionstatus' as enum_type, unnest(enum_range(NULL::subscriptionstatus))::text as value
UNION ALL
SELECT 'billingcycle', unnest(enum_range(NULL::billingcycle))::text
UNION ALL
SELECT 'paymentstatus', unnest(enum_range(NULL::paymentstatus))::text
UNION ALL
SELECT 'paymentmethod', unnest(enum_range(NULL::paymentmethod))::text
UNION ALL
SELECT 'transactiontype', unnest(enum_range(NULL::transactiontype))::text
ORDER BY enum_type, value;
