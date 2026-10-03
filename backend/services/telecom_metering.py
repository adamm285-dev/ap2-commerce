"""
Telecom Usage Metering & Overage Settlement Engine.
Combines recurring base plans with dynamic PayPal Vault MIT debiting for usage overages.
"""

from typing import Dict, Any
from .paypal_vault import execute_headless_mit_capture


def settle_monthly_overage(
    contractor_id: str,
    vault_token: str,
    included_minutes: int,
    actual_minutes: int,
    rate_per_min: float = 0.18,
) -> Dict[str, Any]:
    """
    Settles monthly call-time usage overages via PayPal Vault Merchant-Initiated Transactions (MIT).
    If usage is within included minutes, debits $0.00.
    """
    if actual_minutes <= included_minutes:
        return {
            "status": "ZERO_OVERAGE",
            "amount_debited": 0.0,
            "billable_minutes": 0,
            "actual_minutes": actual_minutes,
            "included_minutes": included_minutes,
        }

    billable_overage = actual_minutes - included_minutes
    total_due = round(billable_overage * rate_per_min, 2)

    # Executes headless off-session capture via PayPal Orders v2 Vault API
    capture_receipt = execute_headless_mit_capture(
        vault_id=vault_token,
        amount_usd=f"{total_due:.2f}",
        reference_id=f"overage_{contractor_id}_{billable_overage}min",
    )
    return {
        "status": "OVERAGE_SETTLED",
        "billable_minutes": billable_overage,
        "amount_usd": total_due,
        "paypal_capture_id": capture_receipt.get("capture_id"),
        "vault_id": vault_token,
        "actual_minutes": actual_minutes,
        "included_minutes": included_minutes,
    }
