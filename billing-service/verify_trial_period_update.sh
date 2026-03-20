#!/bin/bash

echo "=========================================="
echo "Trial Period Update Verification"
echo "=========================================="
echo ""

echo "1. Configuration File (config.py):"
echo "-----------------------------------"
grep -n "TRIAL_PERIOD_DAYS" billing-service/app/core/config.py
echo ""

echo "2. User Consumer (user_consumer.py):"
echo "-------------------------------------"
grep -n "timedelta(days=30)" billing-service/app/messaging/user_consumer.py | head -1
grep -n "30-day trial" billing-service/app/messaging/user_consumer.py | head -1
echo ""

echo "3. Plans API (plans.py):"
echo "------------------------"
grep -n "timedelta(days=30)" billing-service/app/api/plans.py | head -1
grep -n "30-day trial" billing-service/app/api/plans.py | head -1
echo ""

echo "4. Database Migration:"
echo "----------------------"
grep -B1 "^\s*30," billing-service/alembic/versions/20251029_1330_insert_default_plans_reference_data.py | grep -E "(trial|30)"
echo ""

echo "5. Utility Scripts:"
echo "-------------------"
grep -n "timedelta(days=30)" billing-service/create_missing_subscriptions.py | head -1
grep -n "30-day trial" billing-service/start_consumer.py | head -1
echo ""

echo "6. Check for any remaining 14-day references (excluding tests):"
echo "----------------------------------------------------------------"
REMAINING=$(grep -r "timedelta(days=14)" --include="*.py" billing-service/ | grep -v "test_" | grep -v ".pyc" | grep -v "__pycache__" | wc -l)
if [ "$REMAINING" -eq 0 ]; then
    echo "✓ No remaining timedelta(days=14) found in production code"
else
    echo "✗ Found $REMAINING remaining references to timedelta(days=14)"
    grep -r "timedelta(days=14)" --include="*.py" billing-service/ | grep -v "test_" | grep -v ".pyc" | grep -v "__pycache__"
fi
echo ""

echo "=========================================="
echo "Verification Complete!"
echo "=========================================="
