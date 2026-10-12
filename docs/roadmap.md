# Macro Acceptance Contract (The North Star)
<!-- SPEC-001 v1.9.0 Pillar 3 | Mutability: BIMODAL ([INTENT] vs [MEASURED]) -->
<!-- Iron Invariant: NO TASK QUEUES. Ephemeral tasks belong exclusively in state.md -->

## Milestone M-001: Initial Operational Capability
* [INTENT]: Scaffold and bootstrap the repository under SPEC-001 v1.9.0 invariants. Verify zero test fixture drift.
* [MEASURED]: Scaffolding complete; initial evals verified via SHA-256 audit. Status: VERIFIED.

## Milestone S1-RESI: Sprint 1 — Resilience & Emergency Control (Advanced Webhooks & Revocation)
* [INTENT]: Implement full PayPal subscription lifecycle webhook handlers (`BILLING.SUBSCRIPTION.SUSPENDED`, `BILLING.SUBSCRIPTION.RE-ACTIVATED`, `PAYMENT.SALE.REFUNDED` with QBO v3 Credit Memo export). Implement cryptographic mandate revocation status list (`revoked_mandates`) with fail-closed enforcement in `verify_ap2_chains` and automated subscription cancellation.
* [MEASURED]: Complete. Verified via 581 passing tests (188 SDK + 393 project) with zero live network calls. Webhook suspension, reactivation, and refund handlers verified; mandate revocation status list with Ed25519/ES256 signature verification and auto-cancellation verified. Status: VERIFIED.

## Milestone S2-SETTLE: Sprint 2 — Two-Sided Marketplace & PayPal Payouts
* [INTENT]: Implement worker compute node operator registration and automated batch disbursements via PayPal Payouts REST API (`POST /v1/payments/payouts`). Support integer cents margin calculation (gross subscription revenue vs net operator payout vs platform margin) and record payout receipts in SQLite and AG Studio Fleet Ledger.
* [MEASURED]: Planned. Target: Zero floating-point rounding errors and verified mock ledger gate alignment.

## Milestone S3-NATIVE: Sprint 3 — Identity Attestation & Native AP2 Rail Simulation
* [INTENT]: Implement OpenID Connect (OIDC) Log in with PayPal identity attestation binding verified payer accounts to registered AP2 buyer keys during challenge onboarding. Build simulated native AP2 gateway charge rail (`POST /v1/ap2/gateway/charges`) and hardware enclave keystore abstraction in the buyer wallet.
* [MEASURED]: Planned. Target: Native SD-JWT ingestion at the gateway boundary with FIDO2/Passkey keystore emulation.

