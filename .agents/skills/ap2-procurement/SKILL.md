---
name: ap2-procurement
description: Guide for autonomous agents and developers to inspect AP2 spending limits, dry-run ("paper-trade") checkouts, negotiate and purchase compute subscriptions over MCP, handle step-up escalations, and sync recurring renewal receipts.
---

# AP2 Autonomous Procurement & Buyer Wallet Skill

Use this skill whenever operating as (or testing) an autonomous buyer agent procuring compute capacity from the AP2 Seller Node (`backend.mcp_server`) alongside the isolated AP2 Buyer Wallet (`backend.wallet.mcp_server`).

## Core Security Rules

1. **Untrusted Courier Boundary:** The LLM / buyer agent never holds or imports the human owner's private key. All closed-mandate signing happens inside the isolated `ap2-buyer-wallet` process (`backend/wallet/`).
2. **Protect the Development Database:** Any CLI or one-off Python command that imports backend modules MUST set `A2A_DB_PATH` to a temporary database or demo database path—never `backend/data/a2a_commerce.db`.
3. **Offline / Mock Execution by Default:** Always keep `MOCK_EXTERNAL_APIS=true` unless the repository owner explicitly authorizes a live sandbox run.

---

## Workflow 1: Initialize the Isolated Two-Server MCP Environment

To provision three separated keys (merchant, buyer agent wallet, and enrolled owner) and generate a ready-to-run MCP configuration:

```bash
python scripts/setup_claude_desktop_demo.py --monthly-cap 60
```

This creates:
- `.ap2_local/wallet/agent_key.jwk` (created by the wallet process itself; private P-256 key)
- `.ap2_local/wallet/owner_public.jwk` (pinned owner public key—no private material)
- `.ap2_local/wallet/merchant_public.jwk` (or `merchant_keys.json` for multi-merchant pinning—no private material)
- `.ap2_local/wallet/owner_limits.json` (owner-signed AP2 v0.2 `OpenCheckoutMandate` and `OpenPaymentMandate` SD-JWTs)

---

## Workflow 2: Paper-Trading / Dry-Run Procurement (`preview_checkout`)

Before committing budget or locking a pessimistic reservation in `ledger.json`, run a read-only pre-flight check:

1. **Read Owner Spending Limits (`ap2-buyer-wallet`):**
   - Call `get_spending_limits` to inspect `buyer_email`, `monthly_budget_cap`, `allowed_tiers`, `allowed_merchants`, `remaining_budget_cents`, and `purchases_signed`.
2. **Negotiate with Seller (`ap2-seller-node`):**
   - Call `negotiate_tier_terms` with `buyer_email`, `tier_id` (e.g., `ap2-gateway`), and `monthly_budget_cap`.
   - If the requested tier exceeds the budget cap (e.g., \$79.99 vs. \$60.00 cap), the seller returns a merchant-signed counter-offer `checkout_jwt` (e.g., `ap2-batch` at \$49.99/mo) and `offer_id`.
3. **Dry-Run Pre-Flight (`ap2-buyer-wallet`):**
   - Call `preview_checkout` (or `sign_checkout` with `dry_run: true`) passing `checkout_jwt`.
   - The wallet verifies the owner's limits, verifies the merchant's ES256 signature against its pinned merchant keyring, and evaluates all AP2 checkout and payment constraints without signing or mutating `ledger.json`.
   - Inspect `status: "WOULD_SIGN"` and `budget_impact` (`signed_before_cents`, `signed_after_cents`, `remaining_after_cents`).

---

## Workflow 3: Live Mandate Closing & Subscription Settlement

1. **Sign Closed Mandates (`ap2-buyer-wallet`):**
   - Call `sign_checkout` with `checkout_jwt`.
   - Receives `checkout_mandate_chain` and `payment_mandate_chain` signed by the buyer agent's P-256 key.
2. **Settle Subscription (`ap2-seller-node`):**
   - Call `purchase_subscription` with `offer_id`, `buyer_email`, `checkout_mandate_chain`, and `payment_mandate_chain`.
3. **Provision Compute Node (`ap2-seller-node`):**
   - Call `provision_compute_node` with `subscription_id` and `buyer_email`.
   - If an unsubscribed or unapproved agent calls provisioning prematurely, inspect the returned `ap2_payment_challenge` (and `X-AP2-Payment-Required` header on HTTP endpoints) for structured AP2 procurement instructions.

---

## Workflow 4: Handling Refusals ("Humans at the Edges" Step-Up)

When `preview_checkout` or `sign_checkout` returns `isError: true` (`status: "REFUSED"`), inspect the `escalation` object in the response:
- **`PAYMENT_CONSTRAINT_VIOLATION`** (`action: "INCREASE_SPENDING_LIMITS"`):
  - Reports exact integer-cent deltas (`per_purchase_shortfall_cents`, `budget_shortfall_cents`, `required_max_per_purchase_cents`, `required_total_budget_cents`, `occurrences_shortfall`).
  - Present these exact figures to the human owner to request a step-up mandate.
- **`CHECKOUT_CONSTRAINT_VIOLATION`** (`action: "APPROVE_CHECKOUT_EXCEPTION"`):
  - Reports `requested_merchant_id` / `requested_tier_id` versus `allowed_merchants` / `allowed_tiers`.
- **`OWNER_LIMITS_EXPIRED`** (`action: "REAUTHORIZE_EXPIRED_LIMITS"`):
  - Reports `mandate_type` and `expired_at` timestamp so the owner can sign fresh open mandates.

---

## Workflow 5: Synchronizing Recurring Renewal Receipts

When a monthly PayPal renewal (`PAYMENT.SALE.COMPLETED`) is verified by the seller's `evaluate_sale`, the seller issues a merchant-signed `renewal_receipt_jwt` (`vct: "ap2.renewal_receipt.1"`):
- Pass `renewal_receipt_jwt` to the wallet's `record_renewal_receipt` tool.
- `INITIAL` sale receipts bind the initial charge without double-counting the checkout reservation; `VERIFIED` monthly renewal receipts are recorded idempotently by `sale_id` so `get_spending_limits` and future `sign_checkout` calls reflect true cumulative spend across the billing term.
