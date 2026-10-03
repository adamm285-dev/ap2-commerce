"""
Tests for Telecom Metering & Hybrid PayPal Vault MIT Overage Settlement.
"""

import pytest
from backend.services.telecom_metering import settle_monthly_overage


def test_zero_overage_settlement():
    """Usage at or below included minutes requires no charge and returns ZERO_OVERAGE."""
    res = settle_monthly_overage(
        contractor_id="usr_101",
        vault_token="vault_tok_12345",
        included_minutes=250,
        actual_minutes=240,
        rate_per_min=0.18,
    )
    assert res["status"] == "ZERO_OVERAGE"
    assert res["amount_debited"] == 0.0
    assert res["billable_minutes"] == 0


def test_billable_overage_settlement():
    """Usage exceeding included minutes triggers headless MIT debit for exact difference."""
    res = settle_monthly_overage(
        contractor_id="usr_101",
        vault_token="vault_tok_12345",
        included_minutes=250,
        actual_minutes=350,  # 100 min overage @ $0.18 = $18.00
        rate_per_min=0.18,
    )
    assert res["status"] == "OVERAGE_SETTLED"
    assert res["billable_minutes"] == 100
    assert res["amount_usd"] == 18.00
    assert "paypal_capture_id" in res
    assert res["paypal_capture_id"].startswith("CAP-")
