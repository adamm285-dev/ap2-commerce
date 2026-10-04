"""
Telnyx Telephony Line Provisioning Service.
Binds verified PayPal subscriber identity to dedicated local 10DLC telephone lines.
Supports full mock fallback when TELNYX_API_KEY is not configured in .env.
"""

import uuid
import logging
from typing import Dict, Any
import httpx
from ..config import settings
from ..models import ProvisionRequest, ProvisionResponse

from .telecom_router import allocate_dynamic_did

logger = logging.getLogger("telnyx_provisioner")


class TelnyxProvisioner:
    def __init__(self):
        self.api_key = settings.telnyx_api_key
        self.mock_mode = settings.mock_external_apis or not self.api_key
        self._allocated_inventory: Dict[str, Dict[str, Any]] = {}
        self._contractor_dids: Dict[str, Dict[str, Any]] = {}

    def get_contractor_did(self, contractor_email: str):
        if not contractor_email:
            return None
        info = self._contractor_dids.get(contractor_email.strip().lower())
        return info.get("did") if info else None

    def retain_did(
        self,
        request: ProvisionRequest,
        previous_did: str,
        replaces_subscription_id: str = None,
    ) -> ProvisionResponse:
        """Re-binds an existing allocated DID across subscription upgrade or replacement."""
        email_key = request.contractor_email.strip().lower()
        prior_record = self._contractor_dids.get(email_key) or {}
        carrier = prior_record.get("carrier", "Telnyx LLC (Standard 10DLC Pool)")
        region = prior_record.get("region", "Standard 10DLC Pool")

        record = {
            "did": previous_did,
            "subscription_id": request.subscription_id,
            "contractor_email": request.contractor_email,
            "status": "RETAINED_AND_ACTIVE",
            "carrier": carrier,
            "routing_state": "ACTIVE_10DLC_BOUND",
            "replaces_subscription_id": replaces_subscription_id,
            "retained": True,
            "region": region,
        }
        self._allocated_inventory[request.subscription_id] = record
        self._contractor_dids[email_key] = record

        logger.info(
            f"[Telnyx] Retained existing DID {previous_did} for {request.contractor_email} "
            f"(New Sub: {request.subscription_id}, Replaced: {replaces_subscription_id})"
        )

        return ProvisionResponse(
            status="RETAINED",
            assigned_did=previous_did,
            carrier=carrier,
            routing_state="ACTIVE_10DLC_BOUND",
            subscription_id=request.subscription_id,
            failover_triggered=False,
            region=region,
            retained_from_subscription=replaces_subscription_id,
        )

    def reset(self):
        self._allocated_inventory.clear()
        self._contractor_dids.clear()

    async def provision_did(self, request: ProvisionRequest, simulate_exhaustion: bool = False) -> ProvisionResponse:
        """Provisions a dedicated 10DLC telephone DID anchored to verified PayPal identity."""
        if self.mock_mode:
            seed = f"{request.contractor_email}:{request.subscription_id}"
            alloc = allocate_dynamic_did(
                preferred_area_code=request.area_code,
                simulate_exhaustion=simulate_exhaustion,
                contractor_seed=seed,
            )
            assigned_did = alloc["did"]
            region = alloc.get("region", "Standard 10DLC Pool")
            failover = alloc.get("failover_triggered", False)

            record = {
                "did": assigned_did,
                "subscription_id": request.subscription_id,
                "contractor_email": request.contractor_email,
                "status": "ALLOCATED_AND_ACTIVE",
                "carrier": f"Telnyx LLC ({region})",
                "routing_state": "ACTIVE_10DLC_BOUND",
                "failover_triggered": failover,
                "region": region,
            }
            self._allocated_inventory[request.subscription_id] = record
            self._contractor_dids[request.contractor_email.strip().lower()] = record

            logger.info(
                f"[Telnyx MOCK] Allocated DID {assigned_did} to {request.contractor_email} "
                f"(Sub: {request.subscription_id}, Failover: {failover}, Region: {region})"
            )

            return ProvisionResponse(
                status="ALLOCATED",
                assigned_did=assigned_did,
                carrier=f"Telnyx LLC ({region})",
                routing_state="ACTIVE_10DLC_BOUND",
                subscription_id=request.subscription_id,
                failover_triggered=failover,
                region=region,
            )

        # Live Telnyx API path
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            # Search available phone numbers
            res = await client.get(
                "https://api.telnyx.com/v2/available_phone_numbers",
                params={
                    "filter[country_code]": "US",
                    "filter[national_destination_code]": request.area_code,
                    "filter[limit]": 1,
                },
                headers=headers,
                timeout=10.0,
            )
            res.raise_for_status()
            numbers = res.json().get("data", [])
            if not numbers:
                raise RuntimeError(
                    f"No available numbers found in area code {request.area_code}"
                )

            selected_number = numbers[0]["phone_number"]

            # Order phone number
            order_res = await client.post(
                "https://api.telnyx.com/v2/number_orders",
                headers=headers,
                json={"phone_numbers": [{"phone_number": selected_number}]},
                timeout=10.0,
            )
            order_res.raise_for_status()

            return ProvisionResponse(
                status="ALLOCATED",
                assigned_did=selected_number,
                carrier="Telnyx LLC",
                routing_state="ACTIVE_10DLC_BOUND",
                subscription_id=request.subscription_id,
            )


telnyx_provisioner = TelnyxProvisioner()
