"""WhatsApp provider abstractions.

Per-tenant credentials: unlike the SMS service (single Twilio account at module
level), each tenant brings their own Twilio Account SID + Auth Token, so
providers are instantiated per-send using the credentials loaded from
TenantSettings. Do NOT cache the Twilio Client at module load.
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple


WHATSAPP_PREFIX = "whatsapp:"


def _ensure_whatsapp_prefix(phone: str) -> str:
    """Twilio's WhatsApp API requires the 'whatsapp:' prefix on both from_ and to."""
    if phone.startswith(WHATSAPP_PREFIX):
        return phone
    return f"{WHATSAPP_PREFIX}{phone}"


class WhatsAppProvider(ABC):
    """Abstract base class for WhatsApp providers."""

    @abstractmethod
    def send_whatsapp(
        self,
        to_phone: str,
        from_phone: str,
        message: str,
        *,
        status_callback: Optional[str] = None,
        **kwargs,
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        """Send a WhatsApp message.

        Args:
            status_callback: Optional URL Twilio will POST delivery-status
                updates to (`queued`, `sent`, `delivered`, `read`, `failed`,
                etc.). When omitted, only the default status callback
                configured on the sender number in the Twilio Console (if
                any) is used.

        Returns:
            Tuple of (provider_message_id, success, error_message)
        """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Provider identifier (e.g. 'twilio', 'mock')."""


class TwilioWhatsAppProvider(WhatsAppProvider):
    """Twilio-backed WhatsApp provider. Instantiated with a single tenant's credentials."""

    def __init__(self, account_sid: str, auth_token: str):
        if not account_sid or not auth_token:
            raise ValueError("TwilioWhatsAppProvider requires account_sid and auth_token")

        self.account_sid = account_sid
        self.auth_token = auth_token

        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise ImportError(
                "twilio package is required for Twilio WhatsApp support. "
                "Install with: pip install twilio"
            ) from exc

        self.client = Client(account_sid, auth_token)

    def send_whatsapp(
        self,
        to_phone: str,
        from_phone: str,
        message: str,
        *,
        status_callback: Optional[str] = None,
        **kwargs,
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        try:
            payload = {
                "body": message,
                "from_": _ensure_whatsapp_prefix(from_phone),
                "to": _ensure_whatsapp_prefix(to_phone),
            }
            if status_callback:
                payload["status_callback"] = status_callback
            message_obj = self.client.messages.create(**payload)
            return message_obj.sid, True, None
        except Exception as exc:  # noqa: BLE001 — provider failures surface as (False, error)
            return None, False, str(exc)

    def get_provider_name(self) -> str:
        return "twilio"


class MockWhatsAppProvider(WhatsAppProvider):
    """Mock provider for local development and unit tests. Same constructor
    signature as TwilioWhatsAppProvider so tests can substitute it cleanly."""

    def __init__(self, account_sid: str = "MOCK_SID", auth_token: str = "MOCK_TOKEN"):
        self.account_sid = account_sid
        self.auth_token = auth_token

    def send_whatsapp(
        self,
        to_phone: str,
        from_phone: str,
        message: str,
        *,
        status_callback: Optional[str] = None,
        **kwargs,
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        import uuid
        mock_id = f"MOCK_{uuid.uuid4().hex}"
        callback_suffix = f" [callback={status_callback}]" if status_callback else ""
        print(f"MOCK WHATSAPP: from {from_phone} to {to_phone}: {message}{callback_suffix}")
        return mock_id, True, None

    def get_provider_name(self) -> str:
        return "mock"
