"""WhatsApp Business API HTTP client.

Handles sending/receiving messages via the WhatsApp Business Cloud API.
Supports HTTP/SOCKS proxy for regions where WhatsApp API is blocked
(e.g. mainland China via VPN).

Proxy configuration (priority order):
  1. ``proxies`` argument passed to the constructor
  2. ``HTTPS_PROXY`` environment variable
  3. ``ALL_PROXY`` environment variable
  4. Direct connection (no proxy)
"""
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

WHATSAPP_API_VERSION = "v21.0"
WHATSAPP_API_BASE = "https://graph.facebook.com"


def _resolve_proxy(proxies: Optional[dict] = None) -> Optional[dict]:
    """Resolve proxy settings from argument or environment."""
    if proxies is not None:
        return proxies
    env_proxy = os.getenv("HTTPS_PROXY") or os.getenv("ALL_PROXY")
    if env_proxy:
        return {"https": env_proxy, "http": env_proxy}
    return None


class WhatsAppBridge:
    """Client for WhatsApp Business Cloud API."""

    def __init__(
        self,
        phone_number_id: str = "",
        access_token: str = "",
        proxies: Optional[dict] = None,
    ):
        self._configured = bool(phone_number_id and access_token)
        self.proxies = _resolve_proxy(proxies)
        if self._configured:
            self.base_url = (
                f"{WHATSAPP_API_BASE}/{WHATSAPP_API_VERSION}"
                f"/{phone_number_id}"
            )
            self.headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            proxy_msg = f" (proxy: {self.proxies['https']})" if self.proxies else ""
            logger.info(
                "WhatsApp bridge configured%s", proxy_msg,
            )
        else:
            logger.info(
                "WhatsApp bridge not configured — running in mock mode"
            )

    def is_configured(self) -> bool:
        return self._configured

    def send_message(self, to: str, text: str) -> dict:
        """Send a text message to a WhatsApp user."""
        if not self._configured:
            logger.info("[MOCK WhatsApp] To: %s | Text: %s", to, text[:200])
            return {"status": "mock_sent", "to": to}

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        try:
            resp = requests.post(
                f"{self.base_url}/messages",
                headers=self.headers,
                json=payload,
                timeout=10,
                proxies=self.proxies,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error("Failed to send message to %s: %s", to, e)
            return {"status": "error", "error": str(e)}

    def mark_as_read(self, message_id: str) -> dict:
        """Mark a message as read."""
        if not self._configured:
            logger.info("[MOCK WhatsApp] Mark as read: %s", message_id)
            return {"status": "mock_sent"}

        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        try:
            resp = requests.post(
                f"{self.base_url}/messages",
                headers=self.headers,
                json=payload,
                timeout=10,
                proxies=self.proxies,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error("Failed to mark message %s as read: %s", message_id, e)
            return {"status": "error", "error": str(e)}

    def download_media(self, media_id: str) -> Optional[bytes]:
        """Download media (image, etc.) from WhatsApp servers by media ID."""
        if not self._configured:
            logger.warning("Cannot download media: bridge not configured")
            return None

        try:
            # Step 1: get media URL
            media_resp = requests.get(
                f"{WHATSAPP_API_BASE}/{WHATSAPP_API_VERSION}/{media_id}",
                headers=self.headers,
                timeout=10,
                proxies=self.proxies,
            )
            media_resp.raise_for_status()
            media_url = media_resp.json().get("url")
            if not media_url:
                logger.error("No URL returned for media %s", media_id)
                return None

            # Step 2: download binary
            dl_resp = requests.get(media_url, headers=self.headers, timeout=30, proxies=self.proxies)
            dl_resp.raise_for_status()
            return dl_resp.content
        except requests.RequestException as e:
            logger.error("Failed to download media %s: %s", media_id, e)
            return None

    def verify_webhook(
        self,
        mode: str,
        token: str,
        challenge: str,
        verify_token: str,
    ) -> Optional[str]:
        """Handle WhatsApp webhook verification (GET request)."""
        if mode == "subscribe" and token == verify_token:
            return challenge
        logger.warning(
            "Webhook verification failed (mode=%s, token_mismatch=%s)",
            mode,
            token != verify_token,
        )
        return None
