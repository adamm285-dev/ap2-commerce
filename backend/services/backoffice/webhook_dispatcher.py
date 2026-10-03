"""
Back-Office Webhook & Catch-Hook Dispatcher.
Fires authentic cryptographically signed JSON payloads to live webhook endpoints
(e.g., Zapier Catch Hooks, Make.com, Webhook.site, or custom CRM/accounting relays).
Enforces HMAC-SHA256 signature headers and ISO-8601 replay protection timestamps.
"""

import hmac
import hashlib
import json
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import httpx
from ...config import settings

logger = logging.getLogger("backoffice_webhook_dispatcher")


class BackofficeWebhookDispatcher:
    """Dispatches cryptographically signed payloads to external webhook receivers."""

    def __init__(self, default_secret: Optional[str] = None):
        self.secret = default_secret or settings.a2a_mandate_secret

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
                "signature": f"sha256={signature}",
                "event_type": event_type,
                "headers": headers,
                "status_code": None,
                "response_body": None,
                "error": None,
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
                    "signature": f"sha256={signature}",
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
                "signature": f"sha256={signature}",
                "event_type": event_type,
                "headers": headers,
                "status_code": None,
                "response_body": None,
                "error": str(e),
            }


webhook_dispatcher = BackofficeWebhookDispatcher()
