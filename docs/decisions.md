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

## REJ-003: Optimistic Unserialized Purchase Verification Across Processes
- **The Claim:** Checking open-mandate settlement totals (`get_open_mandate_settlement_totals`) and active buyer subscriptions before `await paypal_service.create_subscription(...)` and recording settlement afterwards prevents budget overruns and duplicate active subscriptions.
- **The Measurement:** Because live PayPal subscription creation yields to the event loop across network I/O and the MCP seller server (`backend/mcp_server.py`) runs in a separate OS process from the FastAPI HTTP server (`backend/server.py`), concurrent purchases read identical pre-settlement snapshots and overspent a $60.00 owner ceiling to 9,998 cents ($99.98) while leaving two `ACTIVE` subscriptions for the same buyer. Replaced by cross-process SQLite `BEGIN IMMEDIATE` leases (`purchase_leases` table, 120s TTL, keyed by `mandate:<hash>` and `buyer:<email>`) acquired after `verify_ap2_chains` with post-lease settlement snapshot re-verification (`backend/tests/test_purchase_concurrency.py`).
- **What Would Reopen It:** Moving all mandate verification, payment gateway execution, and ledger settlement into a single atomic serializable database transaction or external distributed consensus coordinator with zero out-of-band network awaits.

## REJ-004: PayPal Agent Toolkit Synchronous Wrapper for Subscription Creation
- **The Claim:** Creating live subscriptions through `paypal_sub_handlers.create_subscription(client, params)` in the PayPal Agent Toolkit with a fallback to `httpx` REST provides resilient subscription creation.
- **The Measurement:** The Agent Toolkit wrapper uses synchronous `requests.post` without a timeout (blocking the `asyncio` event loop past `PURCHASE_LEASE_TTL_SECONDS`) and cannot attach a custom `PayPal-Request-Id` header. When a Toolkit POST timed out after reaching PayPal, falling back to direct REST sent a second request under a new idempotency context, creating duplicate subscriptions. Replaced by async `httpx` direct REST exclusively for `create_subscription` with a deterministic `PayPal-Request-Id` (`ap2-sub-<checkout_hash[:32]>`) preserved across 401 token-refresh retries (`backend/tests/test_purchase_concurrency.py`).
- **What Would Reopen It:** An upstream update to the PayPal Agent Toolkit providing native `async` non-blocking HTTP execution, explicit request timeouts, and first-class `PayPal-Request-Id` header pass-through.

## REJ-005: Synthetic Fallback Fields and Optimistic UI Trace Stubs
- **The Claim:** Populating missing PayPal response fields (`payer_id`, `vault_id`, `status="ACTIVE"`) or missing backend `protocol_trace` payloads with placeholder IDs (`I-AUTONOMOUS-8902`, `PROOF-MOCK`) keeps demos resilient when external services are offline.
- **The Measurement:** Violated Rule 2 (fail closed) and the Mocks policy by reporting unverified or failed calls as `ACTIVE` / `VERIFIED` subscriptions and fabricating PayPal identifiers that PayPal never sent (`backend/tests/test_security_regressions.py` Section 7). Removed all synthetic fallback fields in live code paths, restricted mock-only shortcuts to declared `MOCK(M-NNN)` gates, and updated the UI and Seller Copilot to fail closed and report missing fields honestly.
- **What Would Reopen It:** Never for undeclared production or live paths; simulated behavior is permissible only when explicitly gated behind `MOCK_EXTERNAL_APIS=true`, marked with `# MOCK(M-NNN)`, and tracked in `docs/MOCKS.md`.

## REJ-006: Self-Asserted Mock OIDC Email Attestation as Mandate Revocation Authority
- **The Claim:** Allowing any caller whose OIDC email matches a subscription's `contractor_email` to revoke the mandate (`revoke_mandate`) provides convenient account-level emergency revocation.
- **The Measurement:** In mock mode (`M-023` / `M-024`), OIDC tokens are signed with a local secret rather than PayPal's RS256 JWKS, allowing any registered key to self-assert a victim's email during key registration and revoke another buyer's mandate (`backend/tests/test_ap2_redteam_round4.py`). Restricted mandate revocation strictly to cryptographic proof of possession of the key that signed the mandate (`owner_kid` / `agent_kid`) or verified administrator credentials (`admin_token`).
- **What Would Reopen It:** Live mode with cryptographic RS256 OIDC ID token verification against PayPal's public JWKS (`https://api-m.paypal.com/v1/oauth2/certs`) where email ownership is attested by PayPal's production identity provider.
