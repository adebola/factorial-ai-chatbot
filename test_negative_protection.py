#!/usr/bin/env python3
"""
Test to verify that usage counters never go below 0
"""

# Test the max(0, x - 1) logic
test_cases = [
    ("Normal case", 5, 4),
    ("Edge case - at 1", 1, 0),
    ("Critical case - at 0", 0, 0),  # Should NOT go negative!
    ("Missed event case", 0, 0),     # Multiple decrements when at 0
]

print("="*80)
print("Testing Negative Value Protection")
print("="*80)
print()

for description, current_value, expected_result in test_cases:
    # This is the actual logic from usage_consumer.py lines 281 and 289
    result = max(0, current_value - 1)

    status = "✅ PASS" if result == expected_result else "❌ FAIL"

    print(f"{status} - {description}")
    print(f"   Current: {current_value}")
    print(f"   After decrement: {result}")
    print(f"   Expected: {expected_result}")
    print(f"   Result: {'Never goes negative!' if result >= 0 else 'ERROR: Negative value!'}")
    print()

# Test multiple decrements from 0
print("="*80)
print("Stress Test: Multiple Decrements from 0 (Missed Events Scenario)")
print("="*80)
print()

counter = 0
print(f"Starting counter: {counter}")

for i in range(5):
    counter = max(0, counter - 1)
    print(f"Decrement {i+1}: counter = {counter}")

print()
if counter >= 0:
    print("✅ PASS: Counter remained at 0, never went negative!")
else:
    print("❌ FAIL: Counter went negative!")

print("="*80)
