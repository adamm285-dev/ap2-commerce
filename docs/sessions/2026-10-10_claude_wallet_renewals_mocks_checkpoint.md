# Engineering Shift Handoff
<!-- Flight Recorder: Immutable historical log. Do NOT ingest on system boot. -->

## Date & Session
- Timestamp: 2026-10-10
- Shift Focus: Buyer wallet MCP + Claude Desktop config, month-2 renewal enforcement, mock ledger + gate, M-013/M-017 fixes (Claude Code session; pre-compact checkpoint)

## Completed Actions
- fba1d02: `backend/wallet/` buyer wallet MCP server (holds only the agent key; verifies owner-signed limits and merchant-signed checkout with the vendored AP2 SDK before signing); `scripts/setup_claude_desktop_demo.py` (merchant/agent/owner keys under gitignored `.ap2_local/`, owner key enrolled via challenge flow, absolute-path Claude Desktop config, own demo DB); merchant key loadable from `AP2_MERCHANT_PRIVATE_KEY_FILE` (fails closed).
- 9bd2513: open payment mandate lasts 372 days (12 x 31) while the purchase window stays 24 h; every `PAYMENT.SALE.COMPLETED` re-verifies the stored owner mandate (hash, registry key, email binding), expiry, SDK limits and agreed price; first sale binds to the purchase settlement; advance cancel after the last authorized payment; violations cancel, unverifiable charges suspend; human-approved subscriptions ignored.
- 7198301 + 63377d3: `docs/MOCKS.md` ledger, MOCK markers, `scripts/check_mocks.py` + `backend/tests/test_mocks_ledger.py`; M-013 Vault capture deleted (reported failed captures as COMPLETED); M-017 frontend fake-success fallbacks replaced with honest errors; M-020/M-021 added.

## Key Decisions
- A webhook cannot stop the charge it reports, so renewals are protected by advance cancellation, not detection alone. Refunds stay manual.
- Wallet runs as a separate process and imports no seller code (tested); tier, price, merchant and nonce come from the merchant signature, never from caller arguments.
- Dev DB never touched: setup script and tests use their own databases.

## Open Items
- Claude Desktop flow verified only by launching both servers as the generated config does; not yet run inside the Claude Desktop app.
- `billing_agreement_id` in PayPal's sale payload is assumed, not verified against sandbox.
- Mandates are not renewed at payment 12 (subscription cancels; year 2 needs new limits); spacing between charges is not checked.
- M-021 (back-office log labels dry runs VERIFIED) and M-020 remain mocks by design until fixed.
- README/Devpost claims cleanup still pending (Zapier prize, "FastMCP", Ed25519 framing); NotebookLM slide fixes were handed to the owner.
- Public-repo readiness: history holds the retired HMAC secret, a business email and phone number; plan a fresh-history publish.
- `TESTING=1` grants admin on the fleet ledger endpoint (test bypass in product code).
