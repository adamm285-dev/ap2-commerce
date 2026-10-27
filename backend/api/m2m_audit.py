"""
M2M Autonomous Settlement & Back-Office Audit Store.
Caches and serves authentic ERP routing and QuickBooks Online API v3 payloads
generated during Step 7 (dispatch_zapier_mcp) for 1-click judge inspection and verification.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, Optional
import hmac
import json
import logging
from ..config import settings

logger = logging.getLogger("m2m_audit")

router = APIRouter(prefix="/m2m", tags=["M2M Audit"])

# Cache the latest run artifacts for 1-click judge inspection
_LATEST_M2M_RUN: Dict[str, Any] = {}


def _has_admin_key(request: Request) -> bool:
    """True only when the request carries the configured ADMIN_API_KEY (X-Admin-Key or Bearer)."""
    expected = (getattr(settings, "admin_api_key", None) or "").strip()
    if not expected or expected == "dev-admin-secret-key":
        return False
    raw = request.headers.get("Authorization") or request.headers.get("X-Admin-Key") or ""
    token = raw[7:].strip() if raw.startswith("Bearer ") else raw.strip()
    return bool(token) and hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))


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
async def get_latest_payloads(request: Request) -> Dict[str, Any]:
    """Returns the latest M2M autonomous transaction artifacts for in-UI inspection."""
    is_admin = _has_admin_key(request)
    if not getattr(settings, "mock_external_apis", False) and not is_admin:
        raise HTTPException(
            status_code=401,
            detail="Admin authorization required to inspect M2M audit payloads in live mode.",
        )
    if not _LATEST_M2M_RUN:
        raise HTTPException(
            status_code=404,
            detail="No M2M transaction executed yet. Run the Buyer Agent harness or approve Copilot proposal first.",
        )
    if is_admin:
        return _LATEST_M2M_RUN

    # Mask sensitive webhook HMAC signature and response bodies for non-admin callers
    sanitized = dict(_LATEST_M2M_RUN)
    sanitized["hmac_signature"] = None
    if "webhook_meta" in sanitized and isinstance(sanitized["webhook_meta"], dict):
        wm = dict(sanitized["webhook_meta"])
        wm["signature"] = None
        wm["response_body"] = None
        wm["target_url"] = None
        if "headers" in wm and isinstance(wm["headers"], dict):
            hdrs = dict(wm["headers"])
            hdrs.pop("X-AP2-Signature", None)
            hdrs.pop("x-ap2-signature", None)
            wm["headers"] = hdrs
        sanitized["webhook_meta"] = wm
    return sanitized
