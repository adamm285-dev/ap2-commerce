# Negative Episodic Memory (The Graveyard)
<!-- SPEC-001 v1.9.0 Pillar 6 | Mutability: APPEND-ONLY -->
<!-- Mandatory 3-part schema: Claim -> Measurement -> Reopen Condition -->

## REJ-001: Monolithic Session Diary Ingestion
- **The Claim:** Ingesting all past session logs on Turn 1 boot provides comprehensive historical context.
- **The Measurement:** Exhausted 28k tokens of context window within 3 conversational turns; induced severe context drift and hallucinated file boundaries.
- **What Would Reopen It:** LLM architecture with sub-linear attention latency and zero needle-in-a-haystack degradation beyond 1M tokens.

## REJ-002: Detect-Only Renewal Enforcement
- **The Claim:** Verifying each `PAYMENT.SALE.COMPLETED` webhook against the owner's mandate, and cancelling on a violation, keeps recurring charges within the owner's limits.
- **The Measurement:** PayPal reports a sale after the money has moved, so detect-only enforcement always lets the first out-of-mandate charge through (e.g. payment 13 of 12, or a charge after the mandate expires). Replaced by advance cancellation: after each authorized charge, `backend/services/recurring_mandate_service.py` cancels the subscription if the next charge could not be authorized (payments, budget or term exhausted). Covered by `backend/tests/test_recurring_mandate_renewals.py`.
- **What Would Reopen It:** A payment rail that consults the merchant (or the AP2 mandate) before each recurring charge, so authorization happens before money moves.
