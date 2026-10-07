"""
PayPal Service Gateway.
Handles PayPal OAuth2 tokens, Orders v2, and Subscriptions.
Operates seamlessly in Mock Mode when credentials are omitted, and switches to
live PayPal Sandbox REST APIs when PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are provided.
"""

import uuid
import logging
import hashlib
import hmac
import datetime
import json
from typing import Optional, Dict, Any, List
import httpx
from ..config import settings
from ..models import PayPalOrderResponse

try:
    from paypal_agent_toolkit.shared.paypal_client import PayPalClient
    from paypal_agent_toolkit.shared.configuration import Context as PayPalContext
    from paypal_agent_toolkit.shared.subscriptions import tool_handlers as paypal_sub_handlers
    from paypal_agent_toolkit.shared.orders import tool_handlers as paypal_ord_handlers
    from paypal_agent_toolkit.shared.tools import tools as paypal_official_tools
    PAYPAL_TOOLKIT_AVAILABLE = True
except ImportError:
    PayPalClient = None  # type: ignore
    PayPalContext = None  # type: ignore
    paypal_sub_handlers = None  # type: ignore
    paypal_ord_handlers = None  # type: ignore
    paypal_official_tools = []  # type: ignore
    PAYPAL_TOOLKIT_AVAILABLE = False

logger = logging.getLogger("paypal_service")


class PayPalService:
    def __init__(self):
        self.base_url = settings.paypal_base_url
        self.client_id = settings.paypal_client_id
        self.client_secret = settings.paypal_client_secret
        self.mock_mode = (
            settings.mock_external_apis or not self.client_id or not self.client_secret
        )
        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime.datetime] = None

    async def get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        Obtains an OAuth2 bearer token from PayPal Sandbox with proactive in-memory caching and refresh.
        Cached token is automatically refreshed 5 minutes before the 9-hour sandbox expiration window.
        """
        if self.mock_mode:
            logger.info(
                "[PayPal] Running in Mock Mode; returning synthetic bearer token."
            )
            return f"MOCK_BEARER_TOKEN_{uuid.uuid4().hex[:16]}"

        now = datetime.datetime.now(datetime.timezone.utc)
        if (
            not force_refresh
            and self._cached_token
            and self._token_expires_at
            and now < (self._token_expires_at - datetime.timedelta(minutes=5))
        ):
            return self._cached_token

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    auth=(self.client_id, self.client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json"},
                    timeout=10.0,
                )
                res.raise_for_status()
                data = res.json()
                token = data.get("access_token")
                expires_in = int(data.get("expires_in", 32400))  # Default 9 hours (32400s)
                self._cached_token = token
                self._token_expires_at = now + datetime.timedelta(seconds=expires_in)
                logger.info(
                    f"[PayPal] Acquired OAuth token (expires in {expires_in}s, cached until {self._token_expires_at.isoformat()})"
                )
                return token
            except Exception as e:
                logger.error(
                    f"[PayPal] Failed to obtain OAuth token from {self.base_url}: {e}"
                )
                return None

    def get_sync_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        Synchronous counterpart to get_access_token for synchronous service paths (e.g. paypal_vault.py).
        Reuses cached token and proactively refreshes before expiration or upon forced invalidation.
        """
        if self.mock_mode:
            return f"MOCK_BEARER_TOKEN_{uuid.uuid4().hex[:16]}"

        now = datetime.datetime.now(datetime.timezone.utc)
        if (
            not force_refresh
            and self._cached_token
            and self._token_expires_at
            and now < (self._token_expires_at - datetime.timedelta(minutes=5))
        ):
            return self._cached_token

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    auth=(self.client_id, self.client_secret),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json"},
                )
                res.raise_for_status()
                data = res.json()
                token = data.get("access_token")
                expires_in = int(data.get("expires_in", 32400))
                self._cached_token = token
                self._token_expires_at = now + datetime.timedelta(seconds=expires_in)
                logger.info(
                    f"[PayPal Sync] Acquired OAuth token (expires in {expires_in}s, cached until {self._token_expires_at.isoformat()})"
                )
                return token
        except Exception as e:
            logger.error(f"[PayPal Sync] Failed to obtain OAuth token from {self.base_url}: {e}")
            return None

    def get_toolkit_client(self) -> Optional[Any]:
        """Returns official PayPalAgentToolkit client if configured and available."""
        if not PAYPAL_TOOLKIT_AVAILABLE or self.mock_mode or not self.client_id or not self.client_secret:
            return None
        ctx = PayPalContext(sandbox=("sandbox" in self.base_url.lower()))
        return PayPalClient(self.client_id, self.client_secret, ctx)

    def list_plans_via_toolkit(self) -> Optional[List[Dict[str, Any]]]:
        """Queries plans using official PayPal Agent Toolkit."""
        client = self.get_toolkit_client()
        if not client:
            return None
        try:
            raw = paypal_sub_handlers.list_subscription_plans(client, {"total_required": True})
            return json.loads(raw).get("plans", [])
        except Exception as e:
            logger.warning(f"[PayPal Toolkit] Failed to list plans: {e}")
            return None

    def show_plan_details_via_toolkit(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """Queries plan details using official PayPal Agent Toolkit."""
        client = self.get_toolkit_client()
        if not client:
            return None
        try:
            raw = paypal_sub_handlers.show_subscription_plan_details(client, {"plan_id": plan_id})
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[PayPal Toolkit] Failed to show plan {plan_id}: {e}")
            return None

    def show_subscription_details_via_toolkit(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Queries subscription details using official PayPal Agent Toolkit."""
        client = self.get_toolkit_client()
        if not client:
            return None
        try:
            raw = paypal_sub_handlers.show_subscription_details(client, {"subscription_id": subscription_id})
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[PayPal Toolkit] Failed to show subscription {subscription_id}: {e}")
            return None

    def capture_order_via_toolkit(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Captures an order using the official PayPal Agent Toolkit."""
        client = self.get_toolkit_client()
        if not client or not paypal_ord_handlers:
            return None
        try:
            raw = paypal_ord_handlers.capture_order(client, {"order_id": order_id})
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            logger.warning(f"[PayPal Toolkit] Failed to capture order {order_id}: {e}")
            return None

    def cancel_subscription_via_toolkit(self, subscription_id: str, reason: str = "Customer requested cancellation") -> Optional[Dict[str, Any]]:
        """Cancels an active subscription using the official PayPal Agent Toolkit."""
        client = self.get_toolkit_client()
        if not client or not paypal_sub_handlers:
            return None
        try:
            raw = paypal_sub_handlers.cancel_subscription(client, {"subscription_id": subscription_id, "payload": {"reason": reason}})
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            logger.warning(f"[PayPal Toolkit] Failed to cancel subscription {subscription_id}: {e}")
            return None

    async def create_order(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "FieldSmith Pro Subscription",
        custom_id: Optional[str] = None,
    ) -> PayPalOrderResponse:
        """Creates a PayPal Checkout Order (v2/checkout/orders)."""
        if self.mock_mode:
            mock_id = f"ORDER-MOCK-{uuid.uuid4().hex[:12].upper()}"
            mock_approval_url = f"https://www.sandbox.paypal.com/checkoutnow?token={mock_id}"
            logger.info(
                f"[PayPal MOCK] Created synthetic order {mock_id} for ${amount:.2f} {currency}"
            )
            return PayPalOrderResponse(
                order_id=mock_id,
                status="CREATED",
                approval_url=mock_approval_url,
                mock_mode=True,
            )

        # First try official PayPal Agent Toolkit order handler
        client = self.get_toolkit_client()
        if client and paypal_ord_handlers:
            try:
                params = {
                    "currency_code": "USD",
                    "items": [
                        {
                            "name": description,
                            "item_cost": float(amount),
                            "item_total": float(amount),
                            "quantity": 1,
                        }
                    ],
                    "return_url": "http://localhost:5173/payment-success",
                    "cancel_url": "http://localhost:5173/payment-cancelled",
                }
                raw = paypal_ord_handlers.create_order(client, params)
                data = json.loads(raw)
                approval_url = None
                for link in data.get("links", []):
                    if link.get("rel") == "approve":
                        approval_url = link.get("href")
                        break
                return PayPalOrderResponse(
                    order_id=data.get("id"),
                    status=data.get("status", "CREATED"),
                    approval_url=approval_url,
                    mock_mode=False,
                )
            except Exception as e:
                logger.warning(f"[PayPal Toolkit] Failed to create order via toolkit, falling back to direct REST: {e}")

        token = await self.get_access_token()
        if not token:
            raise RuntimeError(
                "Failed to authenticate with PayPal Sandbox API. Verify PAYPAL_CLIENT_ID/SECRET in .env."
            )

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
                    "description": description,
                    "custom_id": custom_id or "fieldsmith-a2a",
                }
            ],
            "application_context": {
                "return_url": "http://localhost:5173/payment-success",
                "cancel_url": "http://localhost:5173/payment-cancelled",
                "brand_name": "FieldSmith Pro A2A",
                "user_action": "PAY_NOW",
            },
        }

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10.0,
            )
            res.raise_for_status()
            data = res.json()

            approval_url = None
            for link in data.get("links", []):
                if link.get("rel") == "approve":
                    approval_url = link.get("href")
                    break

            return PayPalOrderResponse(
                order_id=data.get("id"),
                status=data.get("status", "CREATED"),
                approval_url=approval_url,
                mock_mode=False,
            )

    async def verify_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """Checks the active status of a PayPal Recurring Subscription."""
        if self.mock_mode:
            logger.info(
                f"[PayPal MOCK] Verifying synthetic subscription {subscription_id}"
            )
            return {
                "id": subscription_id,
                "status": "ACTIVE",
                "plan_id": "P-5ML4271244454362WXNWU5NQ",
                "subscriber": {
                    "email_address": "verified-contractor@floorsmith.pro",
                    "name": {"given_name": "Verified", "surname": "Contractor"},
                },
                "mock_mode": True,
            }

        # First try official PayPal Agent Toolkit subscription handler
        toolkit_data = self.show_subscription_details_via_toolkit(subscription_id)
        if toolkit_data and isinstance(toolkit_data, dict) and "id" in toolkit_data:
            logger.info(f"[PayPal Toolkit] Verified subscription {subscription_id} via official toolkit")
            return toolkit_data

        token = await self.get_access_token()
        if not token:
            raise RuntimeError("PayPal authentication failed.")

        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{self.base_url}/v1/billing/subscriptions/{subscription_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            if res.status_code == 401:
                logger.warning(f"[PayPal] 401 Unauthorized during subscription verification ({subscription_id}); refreshing expired token...")
                token = await self.get_access_token(force_refresh=True)
                res = await client.get(
                    f"{self.base_url}/v1/billing/subscriptions/{subscription_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10.0,
                )
            res.raise_for_status()
            return res.json()

    async def create_subscription(
        self,
        tier_id: str,
        agreed_monthly_rate: float,
        contractor_email: str,
        contractor_name: str = "Marcus Miller",
        offer_id: Optional[str] = None,
        mandate_proof_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates a recurring subscription on PayPal.
        In Mock Mode: Returns a deterministic, verified subscription contract.
        In Live Mode: Authenticates via OAuth2 and creates an active/approved subscription on PayPal Sandbox.
        """
        if self.mock_mode:
            seed = f"{offer_id or mandate_proof_hash}:{tier_id}:{agreed_monthly_rate:.2f}"
            stable_int = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % 10000000
            sub_id = f"I-A2A-VAULT-{stable_int:07d}"
            payer_id = f"PAYER-{hashlib.sha256(contractor_email.strip().lower().encode()).hexdigest()[:12].upper()}" if contractor_email else "PAYER-A2A-BUYER"
            vault_id = f"vault_tok_{sub_id.lower().replace('-', '_')}"
            payment_token = f"tok_{hashlib.sha256(f'{sub_id}:payment'.encode()).hexdigest()[:16]}"
            paypal_req_id = f"req_{hashlib.sha256(sub_id.encode()).hexdigest()[:16]}"
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            created_time = utc_now.isoformat()
            next_billing = (utc_now + datetime.timedelta(days=30)).isoformat()

            logger.info(
                f"[PayPal MOCK] Creating synthetic vaulted subscription {sub_id} for {contractor_email} at ${agreed_monthly_rate:.2f}/mo"
            )
            return {
                "subscription_id": sub_id,
                "status": "ACTIVE",
                "payer_id": payer_id,
                "vault_id": vault_id,
                "payment_token": payment_token,
                "paypal_request_id": paypal_req_id,
                "created_time": created_time,
                "next_billing_time": next_billing,
                "plan_id": f"P-FLSMITH-{tier_id.upper().replace('-', '_')}",
                "mock_mode": True,
                "hateoas_links": [
                    {
                        "href": f"https://api.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}",
                        "rel": "self",
                        "method": "GET",
                    },
                    {
                        "href": f"https://api.sandbox.paypal.com/v1/billing/subscriptions/{sub_id}/cancel",
                        "rel": "cancel",
                        "method": "POST",
                    },
                ],
            }

        plan_map = {
            "solo-starter": getattr(settings, "paypal_plan_id_solo", "P-FLSMITH-SOLO-STARTER"),
            "fieldsmith-pro": getattr(settings, "paypal_plan_id_pro", "P-FLSMITH-PRO"),
            "pro-dispatch": getattr(settings, "paypal_plan_id_dispatch", "P-FLSMITH-DISPATCH"),
        }
        target_plan_id = plan_map.get(tier_id, f"P-FLSMITH-{tier_id.upper().replace('-', '_')}")

        name_parts = contractor_name.split(" ", 1)
        given_name = name_parts[0]
        surname = name_parts[1] if len(name_parts) > 1 else "Contractor"

        # First try official PayPal Agent Toolkit subscription handler
        client = self.get_toolkit_client()
        if client and paypal_sub_handlers:
            try:
                params = {
                    "plan_id": target_plan_id,
                    "subscriber": {
                        "name": {"given_name": given_name, "surname": surname},
                        "email_address": contractor_email,
                    },
                    "custom_id": f"a2a_{offer_id or (mandate_proof_hash[:16] if mandate_proof_hash else 'sub')}",
                    "application_context": {
                        "brand_name": "FieldSmith Pro A2A",
                        "locale": "en-US",
                        "shipping_preference": "GET_FROM_FILE",
                        "user_action": "SUBSCRIBE_NOW",
                        "return_url": "http://localhost:5173/subscription-success",
                        "cancel_url": "http://localhost:5173/subscription-cancelled",
                    },
                }
                raw = paypal_sub_handlers.create_subscription(client, params)
                data = json.loads(raw) if isinstance(raw, str) else raw
                sub_id = data.get("id")
                links = data.get("links", [])
                approval_url = None
                for link in links:
                    if link.get("rel") == "approve":
                        approval_url = link.get("href")
                        break
                live_status = data.get("status", "APPROVAL_PENDING")
                return {
                    "subscription_id": sub_id,
                    "status": live_status,
                    "approval_url": approval_url,
                    "plan_id": target_plan_id,
                    "payer_id": f"PAYER-{data.get('subscriber', {}).get('payer_id', 'SANDBOX')}",
                    "vault_id": f"vault_tok_{sub_id.lower().replace('-', '_')}",
                    "payment_token": f"tok_{sub_id.lower().replace('-', '_')}",
                    "paypal_request_id": f"req_{sub_id}",
                    "created_time": data.get("create_time"),
                    "next_billing_time": data.get("billing_info", {}).get("next_billing_time"),
                    "hateoas_links": links,
                    "mock_mode": False,
                }
            except Exception as e:
                logger.warning(f"[PayPal Toolkit] Failed to create subscription via toolkit, falling back to direct REST: {e}")

        token = await self.get_access_token()
        if not token:
            raise RuntimeError("Failed to authenticate with PayPal Sandbox API.")

        payload = {
            "plan_id": target_plan_id,
            "subscriber": {
                "name": {"given_name": given_name, "surname": surname},
                "email_address": contractor_email,
            },
            "custom_id": f"a2a_{offer_id or (mandate_proof_hash[:16] if mandate_proof_hash else 'sub')}",
            "application_context": {
                "brand_name": "FieldSmith Pro A2A",
                "locale": "en-US",
                "shipping_preference": "NO_SHIPPING",
                "user_action": "SUBSCRIBE_NOW",
                "return_url": "http://localhost:5173/subscription-success",
                "cancel_url": "http://localhost:5173/subscription-cancelled",
            },
        }

        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{self.base_url}/v1/billing/subscriptions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10.0,
            )
            if res.status_code == 401:
                logger.warning(f"[PayPal] 401 Unauthorized during subscription creation ({target_plan_id}); refreshing expired token...")
                token = await self.get_access_token(force_refresh=True)
                res = await client.post(
                    f"{self.base_url}/v1/billing/subscriptions",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10.0,
                )
            res.raise_for_status()
            data = res.json()
            sub_id = data.get("id")
            links = data.get("links", [])
            approval_url = None
            for link in links:
                if link.get("rel") == "approve":
                    approval_url = link.get("href")
                    break

            live_status = data.get("status", "APPROVAL_PENDING")
            return {
                "subscription_id": sub_id,
                "status": live_status,
                "approval_url": approval_url,
                "plan_id": target_plan_id,
                "payer_id": f"PAYER-{data.get('subscriber', {}).get('payer_id', 'SANDBOX')}",
                "vault_id": f"vault_tok_{sub_id.lower().replace('-', '_')}",
                "payment_token": f"tok_{sub_id.lower().replace('-', '_')}",
                "paypal_request_id": f"req_{sub_id}",
                "created_time": data.get("create_time"),
                "next_billing_time": data.get("billing_info", {}).get("next_billing_time"),
                "hateoas_links": links,
                "mock_mode": False,
            }

    @staticmethod
    def generate_mock_webhook_signature(raw_body: str) -> str:
        """Generates an authentic HMAC-SHA256 signature for test webhook transmissions."""
        secret = getattr(settings, "a2a_mandate_secret", "")
        if not secret or not secret.strip():
            raise RuntimeError(
                "A2A_MANDATE_SECRET is not configured. Cannot generate mock webhook signature."
            )
        return hmac.new(
            secret.encode("utf-8"),
            (raw_body or "").encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def verify_webhook_signature(
        self,
        headers: Dict[str, str],
        raw_body: str,
        webhook_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verifies a PayPal webhook transmission signature.
        In Mock Mode: Strictly validates HMAC-SHA256 signature calculated over raw_body; rejects fixed magic strings.
        In Live Mode: Calls PayPal Sandbox POST /v1/notifications/verify-webhook-signature.
        """
        h_lower = {k.lower(): v for k, v in headers.items()}
        sig = h_lower.get("paypal-transmission-sig")
        auth_algo = h_lower.get("paypal-auth-algo")
        cert_url = h_lower.get("paypal-cert-url")
        trans_id = h_lower.get("paypal-transmission-id")
        trans_time = h_lower.get("paypal-transmission-time")

        if self.mock_mode:
            if not sig or not sig.strip():
                logger.warning("[PayPal Webhook MOCK] Missing or empty transmission signature.")
                return {"verification_status": "FAILURE", "mock_mode": True, "error": "MISSING_SIGNATURE"}

            expected_hmac = self.generate_mock_webhook_signature(raw_body or "")
            sig_clean = sig.strip()
            if sig_clean.lower() == expected_hmac.lower():
                logger.info(f"[PayPal Webhook MOCK] Verified HMAC transmission signature ({sig_clean[:16]}...).")
                return {"verification_status": "SUCCESS", "mock_mode": True}

            logger.warning(f"[PayPal Webhook MOCK] Forged or invalid transmission signature rejected: {sig_clean[:32]}")
            return {"verification_status": "FAILURE", "mock_mode": True, "error": "INVALID_SIGNATURE"}

        token = await self.get_access_token()
        if not token:
            logger.error("[PayPal Webhook] Live token acquisition failed.")
            return {"verification_status": "FAILURE", "error": "AUTH_FAILED"}

        try:
            event_json = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
        except Exception:
            event_json = {}

        payload = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": trans_id,
            "transmission_sig": sig,
            "transmission_time": trans_time,
            "webhook_id": webhook_id or settings.paypal_webhook_id or "MOCK_WEBHOOK_ID",
            "webhook_event": event_json,
        }

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.base_url}/v1/notifications/verify-webhook-signature",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=10.0,
                )
                res.raise_for_status()
                data = res.json()
                return data
            except Exception as e:
                logger.error(f"[PayPal Webhook] Live signature verification API call failed: {e}")
                return {"verification_status": "FAILURE", "error": str(e)}


paypal_service = PayPalService()
