"""
Back-Office Webhook & Catch-Hook Dispatcher.
Fires authentic cryptographically signed JSON payloads to live webhook endpoints
(e.g., Zapier Catch Hooks, Make.com, Webhook.site, or custom CRM/accounting relays).
Enforces HMAC-SHA256 signature headers, ISO-8601 replay protection timestamps,
derived secret isolation, and SSRF domain allowlist validation.
"""

import hmac
import hashlib
import json
import uuid
import logging
import ipaddress
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
from ...config import settings

logger = logging.getLogger("backoffice_webhook_dispatcher")

_PERMITTED_DOMAINS = [
    "zapier.com",
    "make.com",
    "ifttt.com",
    "webhook.site",
    "pipedream.net",
]


def is_url_permitted(url: str) -> bool:
    """
    Validates whether target webhook URL is permitted by SSRF policy.
    Blocks private network probing (RFC 1918, link-local, loopback) and
    cloud metadata endpoints (169.254.169.254).
    Allows recognized automation webhook domains (Zapier, Make, IFTTT, Webhook.site, Pipedream)
    or localhost in local test/mock mode.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        return False

    # 1. Unconditionally block cloud metadata IP
    if hostname == "169.254.169.254" or "169.254." in hostname:
        return False

    # 2. Check if hostname is an IP address
    try:
        ip = ipaddress.ip_address(hostname)
        # If it's an IP: check if private / reserved / loopback / link-local / multicast
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            # In test/mock mode, allow 127.0.0.1 or ::1 for local test harnesses
            if getattr(settings, "mock_external_apis", False) and ip.is_loopback:
                return True
            return False
    except ValueError:
        # Not an IP literal; host is a domain name
        pass

    # 3. Localhost in test/mock mode
    if hostname in ("localhost", "testserver"):
        return getattr(settings, "mock_external_apis", False)

    # 4. Whitelist check for allowed webhook domains
    for domain in _PERMITTED_DOMAINS:
        if hostname == domain or hostname.endswith("." + domain):
            return True

    # 5. Check if matches custom admin configured webhook export URL domain
    if getattr(settings, "webhook_export_url", None) and settings.webhook_export_url.strip():
        try:
            admin_parsed = urlparse(settings.webhook_export_url.strip())
            if admin_parsed.hostname and hostname == admin_parsed.hostname.lower():
                return True
        except Exception:
            pass

    return False


class BackofficeWebhookDispatcher:
    """Dispatches cryptographically signed payloads to external webhook receivers."""

    def __init__(self, default_secret: Optional[str] = None):
        if default_secret:
            self.secret = default_secret
        elif getattr(settings, "a2a_webhook_secret", None) and settings.a2a_webhook_secret.strip():
            self.secret = settings.a2a_webhook_secret.strip()
        else:
            # Derive dedicated webhook secret from mandate secret with cryptographic domain separation
            self.secret = hashlib.sha256(
                (settings.a2a_mandate_secret + ":webhook_isolation").encode("utf-8")
            ).hexdigest()

    def sign_payload(self, payload_bytes: bytes) -> str:
        """Computes HMAC-SHA256 signature over the raw payload bytes."""
        return hmac.new(
            self.secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    async def dispatch(
        self,
        payload: Dict[str, Any],
        target_url: Optional[str] = None,
        event_type: str = "a2a.subscription.provisioned",
        timeout_seconds: float = 8.0,
    ) -> Dict[str, Any]:
        """
        Dispatches payload to target webhook URL if provided.
        If no target_url is provided or URL is blank, operates in dry-run mode
        while still computing authentic signature headers.
        """
        delivery_id = f"dlv_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload, sort_keys=True)
        payload_bytes = payload_json.encode("utf-8")
        signature = self.sign_payload(payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "FieldSmith-Pro-A2A-Backoffice/1.0",
            "X-FieldSmith-Signature": f"sha256={signature}",
            "X-FieldSmith-Timestamp": timestamp,
            "X-FieldSmith-Event": event_type,
            "X-FieldSmith-Delivery-Id": delivery_id,
        }

        # Dry run / local inspection mode when no live target URL specified
        if not target_url:
            logger.info(
                f"[Webhook Dispatcher] Dry-run export completed for delivery {delivery_id}. "
                f"Signature: sha256={signature[:16]}... (0 external network calls)"
            )
            return {
                "dispatched": False,
                "dry_run": True,
                "delivery_id": delivery_id,
                "timestamp": timestamp,
                "event_type": event_type,
                "headers": headers,
                "status_code": None,
                "response_body": None,
                "error": None,
            }

        # SSRF Security Validation
        if not is_url_permitted(target_url):
            logger.warning(
                f"[SECURITY] Blocked potentially unsafe webhook URL (SSRF protection): {target_url}"
            )
            return {
                "dispatched": False,
                "dry_run": False,
                "delivery_id": delivery_id,
                "timestamp": timestamp,
                "target_url": target_url,
                "event_type": event_type,
                "headers": headers,
                "status_code": None,
                "response_body": None,
                "error": "URL target blocked by SSRF security policy (unauthorized domain or private IP range)",
            }

        # Live HTTP POST dispatch
        logger.info(f"[Webhook Dispatcher] Firing live payload to {target_url} (delivery: {delivery_id})")
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                res = await client.post(
                    target_url,
                    content=payload_bytes,
                    headers=headers,
                )
                logger.info(
                    f"[Webhook Dispatcher] Live dispatch to {target_url} returned HTTP {res.status_code}"
                )
                return {
                    "dispatched": True,
                    "dry_run": False,
                    "delivery_id": delivery_id,
                    "timestamp": timestamp,
                    "target_url": target_url,
                    "event_type": event_type,
                    "headers": headers,
                    "status_code": res.status_code,
                    "response_body": res.text[:500] if res.text else "",
                    "error": None,
                }
        except Exception as e:
            logger.error(f"[Webhook Dispatcher] Error firing live webhook to {target_url}: {e}")
            return {
                "dispatched": False,
                "dry_run": False,
                "delivery_id": delivery_id,
                "timestamp": timestamp,
                "target_url": target_url,
                "event_type": event_type,
                "headers": headers,
                "status_code": None,
                "response_body": None,
                "error": str(e),
            }


webhook_dispatcher = BackofficeWebhookDispatcher()
