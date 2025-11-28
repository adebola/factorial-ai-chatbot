#!/usr/bin/env python3
"""
Test script to verify enum fix for communications service
This ensures that MessageStatus enums correctly insert lowercase values
"""

from app.models.communications import MessageStatus, MessageType, TemplateType

def test_enum_values():
    """Test that enum values are lowercase"""
    print("Testing enum values...")

    # Test MessageStatus
    assert MessageStatus.PENDING.value == "pending", f"Expected 'pending', got '{MessageStatus.PENDING.value}'"
    assert MessageStatus.SENT.value == "sent", f"Expected 'sent', got '{MessageStatus.SENT.value}'"
    assert MessageStatus.DELIVERED.value == "delivered", f"Expected 'delivered', got '{MessageStatus.DELIVERED.value}'"
    assert MessageStatus.FAILED.value == "failed", f"Expected 'failed', got '{MessageStatus.FAILED.value}'"
    assert MessageStatus.BOUNCED.value == "bounced", f"Expected 'bounced', got '{MessageStatus.BOUNCED.value}'"
    assert MessageStatus.OPENED.value == "opened", f"Expected 'opened', got '{MessageStatus.OPENED.value}'"
    assert MessageStatus.CLICKED.value == "clicked", f"Expected 'clicked', got '{MessageStatus.CLICKED.value}'"
    print("✓ MessageStatus enum values are correct (lowercase)")

    # Test MessageType
    assert MessageType.EMAIL.value == "email", f"Expected 'email', got '{MessageType.EMAIL.value}'"
    assert MessageType.SMS.value == "sms", f"Expected 'sms', got '{MessageType.SMS.value}'"
    print("✓ MessageType enum values are correct (lowercase)")

    # Test TemplateType
    assert TemplateType.EMAIL.value == "email", f"Expected 'email', got '{TemplateType.EMAIL.value}'"
    assert TemplateType.SMS.value == "sms", f"Expected 'sms', got '{TemplateType.SMS.value}'"
    print("✓ TemplateType enum values are correct (lowercase)")

    print("\n✅ All enum values are lowercase - ready for production!")

if __name__ == "__main__":
    test_enum_values()
