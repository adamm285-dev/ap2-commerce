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
* [MEASURED]: Complete. Verified via 591 passing tests (188 SDK + 403 project). Strict Rule 6 integer-cents arithmetic with zero float drift; operator onboarding registry; automated monthly batch disbursements via PayPal Payouts REST API with QBO v3 Bill Payment export; AG Studio Fleet Ledger enrichment and REST endpoints verified. Status: VERIFIED.

## Milestone S3-NATIVE: Sprint 3 — Identity Attestation & Native AP2 Rail Simulation
* [INTENT]: Implement OpenID Connect (OIDC) Log in with PayPal identity attestation binding verified payer accounts to registered AP2 buyer keys during challenge onboarding. Build simulated native AP2 gateway charge rail (`POST /v1/ap2/gateway/charges`) and hardware enclave keystore abstraction in the buyer wallet.
* [MEASURED]: Complete. Verified via 608 passing tests (188 SDK + 420 project) with zero live network calls. PayPal OpenID Connect (OIDC) Log in with PayPal identity attestation and challenge nonce binding verified; Hardware Enclave & FIDO2/Passkey keystore abstraction (`EnclaveKeystore`, `SoftwareEnclaveKeystore`, `PasskeyAttestationKeystore`) verified; Native AP2 direct gateway charge rail (`POST /v1/ap2/gateway/charges`) with cryptographic mandate verification, integer minor units settlement, authentic QBO v3 Purchase export, and fail-closed revocation check verified. Status: VERIFIED.

## Milestone S4-AUDIT: Sprint 4 — Red-Team Security Hardening, Concurrency Leases & Buyer Wallet Ergonomics
* [INTENT]: Harden AP2 v0.2 mandate verification, subscription concurrency, and PayPal REST idempotency against red-team and security-audit attack classes. Implement cross-process SQLite purchase leases (`purchase_leases`), deterministic `PayPal-Request-Id` header binding on async REST subscription creation, buyer wallet dry-run (`preview_checkout`), step-up escalation, multi-merchant keyring pinning, and renewal receipt sync. Remediate all Round 1-4 red-team, Package 1-7, and `security-audit` run-1 findings while eliminating all unverified UI/backend fallback data.
* [MEASURED]: Complete. Verified via 792 passing tests, 9 skipped (188 vendored AP2 SDK conformance + 604 project security, concurrency, and integration tests) and 9/9 judge audit checks with zero live network calls (`MOCK_EXTERNAL_APIS=true`). 22 active mocks strictly documented and verified against code markers in `docs/MOCKS.md` (`python scripts/check_mocks.py`). Status: VERIFIED.

## Milestone S5-SUBMISSION: Sprint 5 — Interactive 3D Sponsor Stage & Final Hackathon Packaging
* [INTENT]: Build the interactive 5-station 3D sponsor pipeline stage (`Ap2ThreeDStoryView.tsx`), blend the 8-slide architecture walkthrough into `README.md`, synchronize `DEVPOST_SUBMISSION.md` and `DEMO_VIDEO_SCRIPT.md` with the 178s single-pass Achird studio narration (`48kHz`, `-1.9 dBTP`), and align all UI labels with AP2 v0.2 ES256 SD-JWT.
* [MEASURED]: Complete. Production frontend bundle (`npm run build`) compiles cleanly across 1,925 modules; 792 passed, 9 skipped in `pytest`; 9/9 judge audit checks green. Status: VERIFIED.
