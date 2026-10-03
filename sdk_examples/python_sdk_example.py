"""
APIMatic Generated SDK Integration Example (Python).
Demonstrates how an autonomous Buyer Agent or third-party developer integrates with
FieldSmith Pro's A2A Commerce Protocol using the auto-generated client SDK.
Conforms 100% to openapi.yaml (OpenAPI 3.1.0).
"""

import httpx
from typing import Dict, Any, Optional


class FieldSmithA2AClient:
    """Lightweight Python SDK client generated from openapi.yaml."""

    def __init__(self, base_url: str = "http://127.0.0.1:8001"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=10.0)

    def check_health(self) -> Dict[str, Any]:
        """Check API gateway operational health."""
        res = self.client.get("/health")
        res.raise_for_status()
        return res.json()

    def get_trade_catalog(self) -> Dict[str, Any]:
        """Retrieve available trade solutions and subscription pricing."""
        res = self.client.get("/api/agent/catalog")
        res.raise_for_status()
        return res.json()

    def evaluate_spending_mandate(
        self,
        buyer_agent_id: str,
        amount: float,
        recurrence: str = "monthly",
        category: str = "contractor-dispatch-ai",
        monthly_budget_cap: float = 100.0,
    ) -> Dict[str, Any]:
        """Verify spending authorization against contractor budget cap."""
        payload = {
            "buyerAgentId": buyer_agent_id,
            "amount": amount,
            "recurrence": recurrence,
            "category": category,
            "monthlyBudgetCap": monthly_budget_cap,
        }
        res = self.client.post("/api/agent/spending-mandate/evaluate", json=payload)
        res.raise_for_status()
        return res.json()

    def create_paypal_order(
        self,
        amount: float,
        description: str,
        currency: str = "USD",
        custom_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate PayPal subscription order."""
        payload = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "custom_id": custom_id,
        }
        res = self.client.post("/api/paypal/create-order", json=payload)
        res.raise_for_status()
        return res.json()

    def provision_contractor_did(
        self,
        subscription_id: str,
        contractor_email: str,
        area_code: str = "863",
    ) -> Dict[str, Any]:
        """Provision dedicated Telnyx DID anchored to verified PayPal KYC identity."""
        payload = {
            "subscriptionId": subscription_id,
            "contractorEmail": contractor_email,
            "areaCode": area_code,
        }
        res = self.client.post("/api/agent/provision", json=payload)
        res.raise_for_status()
        return res.json()

    def trigger_zapier_mcp_sync(
        self,
        workflow_type: str = "a2a_onboarding",
        contractor_name: str = "Marcus Miller",
        business_entity: str = "Miller Custom Flooring LLC",
        allocated_did: str = "+1 (863) 802-6000",
        trade_vertical: str = "Tile & Custom Flooring",
        monthly_fee: float = 89.0,
        paypal_sub_id: str = "I-AUTONOMOUS-8902",
        contractor_email: str = "marcus@millercustomfloors.com",
    ) -> Dict[str, Any]:
        """Execute autonomous downline back-office automation via Zapier MCP."""
        payload = {
            "workflowType": workflow_type,
            "contractorName": contractor_name,
            "businessEntity": business_entity,
            "allocatedDid": allocated_did,
            "tradeVertical": trade_vertical,
            "monthlySubscriptionFee": monthly_fee,
            "paypalSubscriptionId": paypal_sub_id,
            "contractorEmail": contractor_email,
        }
        res = self.client.post("/api/mcp/zapier-sync", json=payload)
        res.raise_for_status()
        return res.json()


def main():
    print("=======================================================")
    print("🚀 Running APIMatic Python SDK Integration Demo")
    print("=======================================================\n")

    client = FieldSmithA2AClient()

    # 1. Health check
    health = client.check_health()
    print(f"1. Health Check: {health['status']} (Mock Mode: {health['mock_mode']})")

    # 2. Query catalog
    catalog = client.get_trade_catalog()
    tier = catalog["trades"][0]
    print(f"2. Catalog Inquiry: Selected '{tier['title']}' at ${tier['monthlySubscription']:.2f}/mo")

    # 3. Verify mandate
    mandate = client.evaluate_spending_mandate(
        buyer_agent_id="sdk-buyer-agent-01",
        amount=tier["monthlySubscription"],
        monthly_budget_cap=100.0,
    )
    print(f"3. Mandate Check: Approved={mandate['approved']} (Proof: {mandate['mandateProofHash'][:20]}...)")

    # 4. Provision Line
    prov = client.provision_contractor_did(
        subscription_id=f"I-SDK-{mandate['mandateProofHash'][:8].upper()}",
        contractor_email="marcus@millercustomfloors.com",
    )
    print(f"4. KYC Telecom Line Allocated: {prov['assignedDid']} (Carrier: {prov['carrier']})")

    # 5. Zapier MCP
    zap = client.trigger_zapier_mcp_sync(
        allocated_did=prov["assignedDid"],
        paypal_sub_id=f"I-SDK-{mandate['mandateProofHash'][:8].upper()}",
    )
    print(f"5. Zapier MCP Synchronized: QBO={zap['qboDraftInvoiceId']}, Jobber={zap['jobberQuoteId']}")

    print("\n✅ APIMatic SDK Client Integration Verified Successfully!\n")


if __name__ == "__main__":
    main()
