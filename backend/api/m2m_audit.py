"""
M2M Autonomous Settlement & Back-Office Audit Store.
Caches and serves authentic ERP routing and QuickBooks Online API v3 payloads
generated during Step 7 (dispatch_zapier_mcp) for 1-click judge inspection and verification.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
import json
import logging

logger = logging.getLogger("m2m_audit")

router = APIRouter(prefix="/m2m", tags=["M2M Audit"])

# Cache the latest run artifacts for 1-click judge inspection
_LATEST_M2M_RUN: Dict[str, Any] = {}


def record_m2m_artifacts(
    mandate_hash: str,
    paypal_sub_id: str,
    node_endpoint: str,
    erp_payload: Dict[str, Any],
    qbo_payload: Dict[str, Any],
    webhook_meta: Dict[str, Any],
):
    """Records the latest authentic M2M back-office artifacts in memory."""
    global _LATEST_M2M_RUN
    _LATEST_M2M_RUN = {
        "status": "COMPLETED",
        "mandate_hash": mandate_hash,
        "paypal_subscription_id": paypal_sub_id,
        "node_endpoint": node_endpoint,
        "endpoint": node_endpoint,
        "timestamp": webhook_meta.get("timestamp"),
        "hmac_signature": webhook_meta.get("signature"),
        "erp": erp_payload,
        "quickbooks": qbo_payload,
        "webhook_meta": webhook_meta,
    }
    logger.info(
        f"[M2M Audit] Cached latest M2M run: Endpoint={node_endpoint}, PayPal={paypal_sub_id}, Mandate={mandate_hash[:16]}..."
    )


def get_latest_artifacts() -> Dict[str, Any]:
    return _LATEST_M2M_RUN


@router.get("/payloads/latest")
async def get_latest_payloads() -> Dict[str, Any]:
    """Returns the latest M2M autonomous transaction artifacts for in-UI inspection."""
    if not _LATEST_M2M_RUN:
        raise HTTPException(
            status_code=404,
            detail="No M2M transaction executed yet. Run the Buyer Agent harness or approve Copilot proposal first.",
        )
    return _LATEST_M2M_RUN
