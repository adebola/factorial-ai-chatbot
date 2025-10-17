"""Custom exceptions for billing service"""


class BillingServiceError(Exception):
    """Base exception for billing service"""
    pass


class PlanNotFoundError(BillingServiceError):
    """Plan not found"""
    pass


class SubscriptionNotFoundError(BillingServiceError):
    """Subscription not found"""
    pass


class PaymentError(BillingServiceError):
    """Payment processing error"""
    pass


class UsageLimitExceededError(BillingServiceError):
    """Usage limit exceeded"""
    pass
