import logging
from flask import current_app

logger = logging.getLogger(__name__)

class NotificationProvider:
    def send_sms(self, to_phone: str, message: str) -> bool:
        raise NotImplementedError

    def send_whatsapp(self, to_phone: str, message: str) -> bool:
        raise NotImplementedError

class ConsoleProvider(NotificationProvider):
    """
    Logs notification delivery details to system console/logger.
    Used during local development and testing. Never makes real network requests.
    """
    _instance = None
    sent_messages = []

    def __init__(self):
        pass

    def send_sms(self, to_phone: str, message: str) -> bool:
        log_entry = {'type': 'SMS', 'to': to_phone, 'message': message}
        ConsoleProvider.sent_messages.append(log_entry)
        logger.info(f"[CONSOLE OUTBOUND SMS] -> {to_phone}: {message}")
        return True

    def send_whatsapp(self, to_phone: str, message: str) -> bool:
        log_entry = {'type': 'WHATSAPP', 'to': to_phone, 'message': message}
        ConsoleProvider.sent_messages.append(log_entry)
        logger.info(f"[CONSOLE OUTBOUND WHATSAPP] -> {to_phone}: {message}")
        return True

    @classmethod
    def clear_sent_messages(cls):
        cls.sent_messages.clear()

class TwilioProvider(NotificationProvider):
    """
    Real Twilio outbound SMS and WhatsApp delivery integration.
    Reads credentials strictly from environment variables.
    """
    def __init__(self, account_sid=None, auth_token=None, from_phone=None, from_whatsapp=None):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_phone = from_phone
        self.from_whatsapp = from_whatsapp

    def _get_client(self):
        sid = self.account_sid or (current_app.config.get('TWILIO_ACCOUNT_SID') if current_app else None)
        token = self.auth_token or (current_app.config.get('TWILIO_AUTH_TOKEN') if current_app else None)
        if not sid or not token:
            logger.error("Twilio credentials not configured in environment variables.")
            return None
        try:
            from twilio.rest import Client  # type: ignore # pyright: ignore[reportMissingImports]
            return Client(sid, token)
        except Exception as e:
            logger.error(f"Failed to initialize Twilio client: {e}")
            return None

    def send_sms(self, to_phone: str, message: str) -> bool:
        client = self._get_client()
        from_num = self.from_phone or (
            current_app.config.get('TWILIO_FROM_NUMBER') or current_app.config.get('TWILIO_PHONE_NUMBER') if current_app else None
        )
        if not client or not from_num:
            logger.error("Twilio client or sender phone number missing.")
            return False
        try:
            client.messages.create(
                body=message,
                from_=from_num,
                to=to_phone
            )
            logger.info(f"[TWILIO SMS SENT] -> {to_phone}")
            return True
        except Exception as e:
            logger.error(f"Twilio SMS delivery failed to {to_phone}: {e}")
            return False

    def send_whatsapp(self, to_phone: str, message: str) -> bool:
        client = self._get_client()
        from_wa = self.from_whatsapp or (current_app.config.get('TWILIO_WHATSAPP_NUMBER') if current_app else None)
        if not client or not from_wa:
            logger.error("Twilio client or sender WhatsApp number missing.")
            return False
        try:
            formatted_to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
            formatted_from = f"whatsapp:{from_wa}" if not from_wa.startswith("whatsapp:") else from_wa
            client.messages.create(
                body=message,
                from_=formatted_from,
                to=formatted_to
            )
            logger.info(f"[TWILIO WHATSAPP SENT] -> {to_phone}")
            return True
        except Exception as e:
            logger.error(f"Twilio WhatsApp delivery failed to {to_phone}: {e}")
            return False


def get_notification_provider():
    """Factory function returning configured NotificationProvider."""
    provider_type = 'console'
    if current_app:
        provider_type = current_app.config.get('NOTIFICATION_PROVIDER', 'console').lower()
    
    if provider_type == 'twilio':
        return TwilioProvider()
    return ConsoleProvider()
