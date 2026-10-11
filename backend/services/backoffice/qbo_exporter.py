"""
QuickBooks Online (QBO) Back-Office Export Engine.
Formats authentic Intuit QuickBooks Online REST API v3 Purchase/Expense objects
and Vendor representations for autonomous A2A recurring software subscriptions.
Conforms strictly to Intuit Developer API v3 schemas.
"""

from typing import Dict, Any, Optional
import uuid
from datetime import datetime, timezone


class QboExporter:
    """Generates authentic QuickBooks Online API v3 Purchase and Vendor JSON payloads."""

    def __init__(self):
        self.api_version = "v3"
        self.default_expense_account_id = "6300"
        self.default_expense_account_name = "Dues & Subscriptions: Software & SaaS"
        self.default_clearing_account_id = "99"
        self.default_clearing_account_name = "PayPal Clearing Account"
        self.vendor_name = "AP2 Autonomous Node Network Inc."
        self.vendor_id = "101"

    def format_purchase_expense_payload(
        self,
        contractor_name: str,
        business_entity: str,
        contractor_email: str,
        monthly_fee: float,
        paypal_subscription_id: str,
        allocated_did: str,
        mandate_proof_hash: str,
        trade_vertical: str,
        txn_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates an authentic QuickBooks Online API v3 Purchase (Expense) payload.
        Maps the recurring compute fee to Software & SaaS COGS/Expense account.
        """
        date_str = txn_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc_number = f"AP2-A2A-{paypal_subscription_id[-6:] if len(paypal_subscription_id) >= 6 else uuid.uuid4().hex[:6].upper()}"

        if monthly_fee <= 50.00:
            plan_line_desc = f"AP2 High-Throughput Batch Worker ({trade_vertical}) — Autonomous Recurring Subscription"
            memo_plan = f"Plan: High-Throughput Batch Worker (${monthly_fee:.2f}/mo)"
        elif monthly_fee > 100.00:
            plan_line_desc = f"AP2 Enterprise Cluster Node ({trade_vertical}) — Autonomous Recurring Subscription"
            memo_plan = f"Plan: Enterprise Cluster Node (${monthly_fee:.2f}/mo)"
        else:
            plan_line_desc = (
                f"AP2 Dedicated AI Service Gateway "
                f"({trade_vertical}) — Autonomous Recurring Subscription"
            )
            memo_plan = f"Plan: Dedicated AI Service Gateway (${monthly_fee:.2f}/mo)"

        private_memo = (
            f"AP2 Autonomous Commerce Protocol Node.\n"
            f"PayPal Sub: {paypal_subscription_id} | {memo_plan}\n"
            f"Endpoint: {allocated_did} | Vertical: {trade_vertical}\n"
            f"Mandate Proof Hash: {mandate_proof_hash}\n"
            f"Carrier: MCP over HTTPS (JSON-RPC 2.0)\n"
            f"Purchaser: {contractor_name} ({business_entity})"
        )

        return {
            "Purchase": {
                "PaymentType": "CreditCard",
                "AccountRef": {
                    "value": self.default_clearing_account_id,
                    "name": self.default_clearing_account_name,
                },
                "EntityRef": {
                    "value": self.vendor_id,
                    "name": self.vendor_name,
                    "type": "Vendor",
                },
                "TxnDate": date_str,
                "DocNumber": doc_number,
                "TotalAmt": float(f"{monthly_fee:.2f}"),
                "CurrencyRef": {
                    "value": "USD",
                    "name": "United States Dollar",
                },
                "PrivateNote": private_memo,
                "GlobalTaxCalculation": "NotApplicable",
                "Line": [
                    {
                        "Id": "1",
                        "LineNum": 1,
                        "Amount": float(f"{monthly_fee:.2f}"),
                        "DetailType": "AccountBasedExpenseLineDetail",
                        "Description": plan_line_desc,
                        "AccountBasedExpenseLineDetail": {
                            "AccountRef": {
                                "value": self.default_expense_account_id,
                                "name": self.default_expense_account_name,
                            },
                            "BillableStatus": "NotBillable",
                            "TaxCodeRef": {
                                "value": "NON",
                            },
                        },
                    }
                ],
            }
        }

    def format_vendor_payload(self) -> Dict[str, Any]:
        """
        Generates an authentic QuickBooks Online API v3 Vendor creation payload for AP2 Autonomous Node Network Inc.
        """
        return {
            "Vendor": {
                "DisplayName": self.vendor_name,
                "CompanyName": self.vendor_name,
                "PrintOnCheckName": self.vendor_name,
                "PrimaryEmailAddr": {
                    "Address": "billing@example.com",
                },
                "WebAddr": {
                    "URI": "https://ap2-commerce.org",
                },
                "PrimaryPhone": {
                    "FreeFormNumber": "+1 (800) 555-0199",
                },
                "BillAddr": {
                    "Line1": "AP2 Autonomous Node Network Inc.",
                    "City": "San Francisco",
                    "CountrySubDivisionCode": "CA",
                    "PostalCode": "94105",
                    "Country": "USA",
                },
                "TaxIdentifier": "XX-XXX8902",
                "AcctNum": "A2A-VENDOR-01",
            }
        }

    def export_full_qbo_package(
        self,
        contractor_name: str,
        business_entity: str,
        contractor_email: str,
        monthly_fee: float,
        paypal_subscription_id: str,
        allocated_did: str,
        mandate_proof_hash: str,
        trade_vertical: str,
    ) -> Dict[str, Any]:
        """
        Assembles the complete QBO export package with purchase payload, vendor metadata,
        and target API endpoint specifications.
        """
        synthetic_purchase_id = f"QBO-PURCHASE-{uuid.uuid4().hex[:8].upper()}"
        purchase_payload = self.format_purchase_expense_payload(
            contractor_name=contractor_name,
            business_entity=business_entity,
            contractor_email=contractor_email,
            monthly_fee=monthly_fee,
            paypal_subscription_id=paypal_subscription_id,
            allocated_did=allocated_did,
            mandate_proof_hash=mandate_proof_hash,
            trade_vertical=trade_vertical,
        )

        vendor_payload = self.format_vendor_payload()

        return {
            "entity": "QuickBooks_Online",
            "api_version": "v3",
            "purchase_id": synthetic_purchase_id,
            "target_endpoint": "https://quickbooks.api.intuit.com/v3/company/{realmId}/purchase",
            "http_method": "POST",
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            "payload": purchase_payload,
            "vendor_reference": vendor_payload,
            "account_mapping": {
                "expense_account": f"{self.default_expense_account_id} - {self.default_expense_account_name}",
                "clearing_account": f"{self.default_clearing_account_id} - {self.default_clearing_account_name}",
                "monthly_amount": monthly_fee,
                "currency": "USD",
            },
        }


qbo_exporter = QboExporter()
