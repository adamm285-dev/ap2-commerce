# AP2 Autonomous Commerce: Agent Payments Protocol Operations Deck

> **Try it in 1 second (no API keys required):**
> ```bash
> git clone https://github.com/adamm285-dev/ap2-commerce.git
> cd ap2-commerce
> pip install -r backend/requirements.txt -r backend/requirements-dev.txt
> python scripts/judge_audit_harness.py
> # 9/9 checks passed in ~1s (in-process against a temporary SQLite database)
> ```

---

## 1. Project Title & Elevator Pitch

* **Project Title:** AP2 Autonomous Commerce: Cryptographic Agent Subscriptions
* **Elevator Pitch (Tagline):** Cryptographic AI agent commerce on FIDO AP2 v0.2 & PayPal Subscriptions: owner-signed SD-JWT budgets, dual-MCP wallet isolation & BI.
* **Created By (Team Member Contribution):**
  Solo creator and full-stack architect: designed and built the Dual-MCP zero-trust wallet/seller architecture, AP2 v0.2 ES256 mandate verification, PayPal Subscriptions and renewal engine, CSS 3D and AG Studio/Bryntum UI, and 792-test suite.

---

## 2. Inspiration

Imagine waking up at 3:00 AM to find that an autonomous coding agent hit a GPU memory limit, read a vendor prompt offering an "instant enterprise cluster upgrade," and upgraded its own plan from $49.99/mo to $499.99/mo on your corporate PayPal account. As enterprises move from chat assistants to autonomous agents that procure APIs, SaaS seats, and cloud compute on their own, giving an LLM direct access to payment credentials or signing keys creates an unpatchable prompt-injection surface.

The open **AP2 (Agent Payments Protocol v0.2)**, stewarded by the **FIDO Alliance** (originated with Google and donated to the FIDO Alliance on 28 April 2026), defines open and closed Checkout and Payment Mandates as ES256 SD-JWTs (with the agent's public key bound in `cnf.jwk`), including a Human-Not-Present flow where an agent buys under limits the owner signed in advance.

However, AP2 v0.2 leaves three critical items on its original roadmap open:
1. **Recurring payments & subscriptions (V1.x roadmap):** v0.2 defines an `AgentRecurrence` constraint, but has no standard PayPal subscription renewal verification or advance-cancellation flow.
2. **MCP-based wallet isolation (V1.x roadmap):** How to keep private signing keys out of the LLM process using Model Context Protocol (MCP) boundaries.
3. **Real-time buyer-seller negotiation (long-term vision):** How a seller agent can answer an over-cap request with a cheaper merchant-signed counter-offer that fits the buyer's mandate.

We built **AP2 Autonomous Commerce** for those three gaps: recurring PayPal billing under a capped mandate, a wallet MCP that signs while the model only carries tokens, and a seller that can answer an over-cap request with a cheaper signed offer. The seller operations deck shows that path. PayPal is the settlement rail. The public demo runs with `MOCK_EXTERNAL_APIS=true`, and every stand-in is listed in [`docs/MOCKS.md`](https://github.com/adamm285-dev/ap2-commerce/blob/main/docs/MOCKS.md).

---

## 3. What It Does

**The core rule: The model proposes; code decides.** The model never holds the signing key, the wallet enforces the cap, and the seller verifies the chain before any PayPal call.

### 1. Open Mandate Signing & Untrusted Courier Wallet (Dual-MCP Airgap)
In the sandbox, a non-agentic owner step signs two open mandates (`mandate.checkout.open.1` and `mandate.payment.open.1`) with an ES256 key: monthly cap, annual budget, recurrence, merchant id, and allowed SKUs. The buyer agent's public key is bound in `cnf.jwk`. In this demo the server signs that open mandate with a demo owner key (M-005); a passkey on the owner's machine is the production step.

At runtime, procurement is split across two separate OS processes speaking JSON-RPC 2.0 over MCP:
* **Seller MCP Server (`backend.mcp_server`):** Exposes 8 procurement tools (`negotiate_subscription`, `purchase_subscription`, `provision_compute_node`, `dispatch_zapier_mcp`, etc.).
* **Buyer Wallet MCP Server (`backend.wallet.mcp_server`):** Holds the agent's ES256 key and the owner-signed open mandates (never the owner's private key). When the LLM agent asks the wallet to sign a checkout, the wallet verifies the merchant's signature on `checkout_jwt` against the pinned merchant key, reads the price, tier, and payee from that verified token, and raises `WalletRefusal` (`PAYMENT_CONSTRAINT_VIOLATION`) if the checkout exceeds the owner's signed cap.

### 2. Recurring PayPal Subscriptions, Webhook Re-Verification & Advance Cancellation
In [`backend/services/recurring_mandate_service.py`](https://github.com/adamm285-dev/ap2-commerce/blob/main/backend/services/recurring_mandate_service.py), every PayPal `PAYMENT.SALE.COMPLETED` renewal webhook is checked against the owner's stored AP2 mandate using the vendored AP2 v0.2 SDK: stored-mandate integrity, enrolled registry key, email binding, expiry, total budget, the 12-payment count limit, and the agreed monthly rate.
Because PayPal reports a renewal sale after money moves, the server also performs **predictive advance cancellation** after each authorized charge: if the next monthly charge would exceed the payment count, cumulative budget, or 372-day recurring window, it calls PayPal's `/v1/billing/subscriptions/{id}/cancel` endpoint in advance before the next billing cycle fires.

### 3. Multi-Tier Counter-Offers & Local Back-Office Payloads
A $79.99 request under a $60 cap is answered with a merchant-signed $49.99 offer (`checkout_jwt`, `checkout_hash`, one-time nonce). After both mandate chains verify, the seller creates the PayPal subscription when live credentials are configured. In the demo it records a labeled mock subscription, writes a QuickBooks-shaped GL 6300 payload locally, and emits an HMAC-signed CloudEvents envelope. It does not post to QuickBooks, and it does not provision a live machine.

### 4. Interactive Operations Deck (CSS 3D, AG Studio v3, Bryntum Scheduler)
* **CSS 3D Agentic Pipeline (`Ap2ThreeDStoryView.tsx`):** A 4-station CSS 3D walkthrough illustrating happy-path counter-offer negotiation ($79.99 down to $49.99/mo or $120 down to $99.99/mo) versus a blocked over-budget attack.
* **Enterprise Fleet Ledger (`EnterpriseFleetLedger.tsx`):** Built with **AG Studio v3.0.0** (`ag-studio-react`), **AG Grid Community v36.2**, and **AG Charts v14.2**, featuring custom telemetry widgets, 34px floating column filters, and runtime switching across **Mission Control**, **Executive View**, and **Drag & Drop Editor** layouts over the 14 seeded demo subscriptions from SQLite WAL ($1,219.87/mo baseline active MRR, or $1,269.86/mo after a $49.99 demo purchase; explicitly labeled `Demo data`, M-009).
* **Compute Dispatch Calendar (`BryntumDispatchScheduler.tsx`):** Built with **Bryntum Scheduler 7.3.7 (trial build)** to visualize regional compute workload shifts, resource slot locking, and live node activation transitions upon PayPal settlement.

---

## 4. How We Built It (PayPal, AI & Sponsor Tools)

* **PayPal Developer Platform:**
  PayPal Subscriptions (`v1/billing/subscriptions`) with the Python `paypal-agent-toolkit` `1.1.0` package. The idempotency key is the checkout hash (`PayPal-Request-Id`). Live mode requires PayPal client id and secret; if either is missing, the process exits instead of silently pretending to be live. `MOCK_EXTERNAL_APIS=true` is the demo mode, checked by [`scripts/check_mocks.py`](https://github.com/adamm285-dev/ap2-commerce/blob/main/scripts/check_mocks.py). For human-present step-up checkout in the React UI, we integrate `@paypal/react-paypal-js` (`10.5.2`).
* **AI Models & Agent Protocols:**
  * **Buyer CLI Agent (`backend/agents/llm_buyer_agent.py`):** Supports Anthropic (`claude-3-5-sonnet`), OpenAI (`gpt-4o-mini`), and Gemini (`gemini-2.5-flash`) via tool-calling to drive MCP negotiation, plus a deterministic scripted offline mode (`M-015`) so judges can run the CLI without API keys.
  * **Desktop MCP Integration (`scripts/setup_claude_desktop_demo.py`):** Configures **Claude Desktop** to run `backend.mcp_server` and `backend.wallet.mcp_server` side-by-side over stdio JSON-RPC 2.0.
  * **Seller Copilot (`SellerCopilotView.tsx`):** Uses deterministic keyword-matched setup and simulation flows (`M-016`) so the UI walkthrough works offline with zero LLM latency.
  * **Studio Narration (`scripts/generate_hackathon_narration.py`):** Single-pass neural TTS narration (`Achird` voice, 48 kHz stereo).
* **AP2 v0.2 SDK (FIDO Alliance):** Vendored in [`backend/vendor/ap2/`](https://github.com/adamm285-dev/ap2-commerce/tree/main/backend/vendor/ap2) (at upstream commit `e1ea56db` with two documented compatibility fixes in [`backend/vendor/ap2/NOTICE`](https://github.com/adamm285-dev/ap2-commerce/blob/main/backend/vendor/ap2/NOTICE)) to parse, sign, and verify ES256 SD-JWT mandate chains.
* **Sponsor Integrations:**
  * **AG Grid / AG Studio / AG Charts:** `ag-studio-react` (`3.0.0`), `ag-grid-community` (`36.2.0`), and `ag-charts-react` (`14.2.0`) power the Enterprise Fleet Ledger and BI Suite, including custom cell status badges, custom KPI widgets, floating column filters, and interactive **Mission Control**, **Executive View**, and **Drag & Drop Editor** modes (built with AG Grid's `ag-dev` agent skill).
  * **Bryntum Scheduler:** `@bryntum/scheduler-trial` (`7.3.7`) powers the interactive compute workload dispatch timeline, resource slot booking, and real-time node activation transitions.
  * **APIMatic & OpenAPI 3.1.0:** [`openapi.yaml`](https://github.com/adamm285-dev/ap2-commerce/blob/main/openapi.yaml) and [`openapi.json`](https://github.com/adamm285-dev/ap2-commerce/blob/main/openapi.json) define 48 paths (51 operations) for agent negotiation, mandate verification, PayPal subscriptions, and fleet telemetry, paired with [`apimatic.json`](https://github.com/adamm285-dev/ap2-commerce/blob/main/apimatic.json) for developer portal configuration and multi-language SDK generation (`Python`, `TypeScript`, `Go`).
  * **Zapier-Ready CloudEvents Export:** [`backend/services/backoffice/qbo_exporter.py`](https://github.com/adamm285-dev/ap2-commerce/blob/main/backend/services/backoffice/qbo_exporter.py) formats QuickBooks Online v3 GL-6300 payloads and HMAC-SHA256 signed CloudEvents 1.0 envelopes for a configured Zapier catch hook (dry-run locally when no webhook URL is set, `M-011`).

---

## 5. What We Will Tell You Before You Find It (Transparency & Mock Ledger)

Every stand-in for real behavior in this repository is marked in the code with `# MOCK(M-NNN)` and documented in [`docs/MOCKS.md`](https://github.com/adamm285-dev/ap2-commerce/blob/main/docs/MOCKS.md) (22 entries). [`backend/tests/test_mocks_ledger.py`](https://github.com/adamm285-dev/ap2-commerce/blob/main/backend/tests/test_mocks_ledger.py) and `python scripts/check_mocks.py` fail the build if a mock marker is missing from the ledger or if a listed symbol does not exist.

* **What is 100% real and runs in-process on every test:**
  * Challenge-response enrollment of buyer/owner public keys (`GET /api/agent/keys/challenge`, `POST /api/agent/keys/register`).
  * ES256 SD-JWT open mandate minting (`mandate.checkout.open.1`, `mandate.payment.open.1`) with agent holder key bound in `cnf.jwk`.
  * Isolated Buyer Wallet MCP constraint checking (`WalletRefusal` on budget, SKU, or merchant mismatch) and closed mandate signing (`mandate.checkout.1`, `mandate.payment.1`).
  * Seller `verify_ap2_chains` cryptographic verification, checkout-hash binding, one-time nonce consumption, SQLite `purchase_leases` concurrency locking, and `PayPal-Request-Id` idempotency derivation.
  * Recurring webhook mandate re-verification and advance cancellation logic (`recurring_mandate_service.py`).
* **What is simulated in demo mode (`MOCK_EXTERNAL_APIS=true`):**
  * Hosted frontend (`https://ap2-commerce.fieldsmith.pro/`): Deployed on Cloudflare as a static **UI Walkthrough** (`M-009`). Run the backend locally (`python -m backend.server` or `python scripts/judge_audit_harness.py`) to execute the live Python cryptographic verifier.
  * PayPal settlement (`M-002`): Returns simulated subscription IDs in mock mode; live mode calls PayPal `/v1/billing/subscriptions` when `PAYPAL_CLIENT_ID` and `PAYPAL_SECRET` are set.
  * Server-signed demo owner limits (`M-005`..`M-007`): In mock mode, the server signs open mandates with a demo owner key as a stand-in for a hardware WebAuthn trusted surface; in live mode, those demo endpoints return `404`.
  * Compute node provisioning (`M-010`) and QuickBooks GL-6300 export (`M-011`): Return placeholder node DIDs and in-memory QBO v3 JSON payloads unless external endpoints are configured.
  * Fleet ledger and schedule (`M-009`, `M-018`): Seeded with 14 demo rows ($1,219.87/mo baseline active MRR across 13 active rows, or $1,269.86/mo with a $49.99 demo subscription) so the AG Studio and Bryntum views are populated on first launch.

---

## 6. Challenges We Ran Into (Four Engineering War Stories)

1. **Two Concurrent Purchases Under One $60 Budget Charged $99.98 (TOCTOU Race):**
   During adversarial testing, firing two concurrent $49.99 purchase requests using the same $60 open payment mandate passed signature verification simultaneously before either subscription was written to SQLite, resulting in $99.98 of subscriptions under a $60 cap. We fixed this by introducing an atomic SQLite `purchase_leases` lock keyed on `(open_payment_mandate_hash, buyer_email)` acquired *before* calling PayPal, paired with a deterministic `PayPal-Request-Id` derived from `checkout_hash` so concurrent replays are rejected with `PURCHASE_IN_PROGRESS`.
2. **The Word "yes" Buying a Subscription Without Cryptographic Receipts:**
   An early version of the Seller Copilot `/api/seller-copilot/chat` endpoint treated the chat message `"yes"` as confirmation to insert an active subscription row into `_COMPLETED_SUBSCRIPTIONS` without running `verify_ap2_chains`, leaving a subscription with no `checkout_receipt` or `payment_receipt`. We locked down the purchase path so no subscription row can ever be recorded or activated without verified ES256 checkout and payment mandate chains, and added a parameterized red-team regression test (`test_copilot_never_records_a_subscription_without_receipts`).
3. **A Rejected Purchase Burning the Buyer's Mandate Nonce:**
   Initially, the seller consumed the merchant checkout nonce as soon as the token was parsed, *before* checking whether the payment mandate satisfied the budget cap. If an agent submitted a malformed or over-budget payment mandate, the checkout nonce was burned and a valid retry failed with `NONCE_ALREADY_USED`. We reordered `verify_ap2_chains` so nonces are committed only after both the checkout and payment mandate chains pass every cryptographic and budget constraint check.
4. **188 Upstream AP2 Conformance Tests Forcing Two SDK Compatibility Fixes:**
   We vendored the upstream AP2 v0.2 Python SDK and its 188 conformance tests (`backend/tests/conformance/`). Running them under Python 3.13 exposed two upstream issues documented in [`backend/vendor/ap2/NOTICE`](https://github.com/adamm285-dev/ap2-commerce/blob/main/backend/vendor/ap2/NOTICE): `Constraint.from_dict` dispatching on subclass overrides, and SD-JWT disclosure array handling when selective disclosures are stripped. Fixing those cleanly brought all 188 upstream conformance tests to 100% pass alongside our 604 project tests.

---

## 7. Accomplishments That We're Proud Of

* **Zero-Trust Key Separation:** Proving end-to-end that an LLM buyer agent can negotiate a counter-offer and complete a subscription purchase over MCP without ever holding, importing, or viewing a private signing key.
* **Automated Test & Conformance Suite:**
  Running `python -m pytest backend/tests -q -n 4` executes **188 upstream AP2 v0.2 conformance tests** vendored and run in this suite plus **604 project security, wallet isolation, concurrency, and recurring-billing tests** (`792 passed, 9 skipped in 58.09s`).
* **One-Second Judge Audit Harness:**
  `python scripts/judge_audit_harness.py` runs 9 end-to-end invariant checks in-process against a temporary SQLite database in ~1 second with zero API keys required (noting that checks 7 and 8 validate reconciliation over the seeded demo fleet rows).

---

## 8. What We Learned

* **Prompt guardrails are not a payment boundary:** Any agent that holds a signing key in its own context or process can eventually be coaxed into signing an unintended payload. Moving constraint evaluation and signing into a separate Wallet MCP process (`backend.wallet.mcp_server`) turns spending limits from a prompt instruction into a deterministic cryptographic check.
* **Subscriptions require post-checkout mandate state:** One-time checkout mandates end when the first payment settles, but recurring subscriptions create an ongoing liability. Binding PayPal webhook verification to stored AP2 mandates and cancelling before the next billing cycle bridges single-checkout mandates with subscription billing.

---

## 9. What's Next for AP2 Autonomous Commerce

* **Hardware WebAuthn / Passkey Trusted Surface:** Replace the mock-gated server demo owner key with browser WebAuthn (FIDO2 passkey) hardware signing so human owners sign open mandates directly on their device enclave.
* **Live PayPal Sandbox Renewal Runs & Multi-Seller Federation:** Execute full multi-cycle renewal and advance-cancellation runs against the live PayPal Sandbox webhook simulator and expand key discovery across multiple independent seller MCP nodes.
* **Metered Usage & Overage Mandates:** Extend recurring monthly caps to support metered per-token and per-GPU-minute billing within an owner-signed ceiling.

---

## 10. Built With

`paypal-subscriptions-api`, `paypal-agent-toolkit`, `paypal-react-sdk`, `fido-ap2-protocol`, `model-context-protocol`, `claude-3-5-sonnet`, `ag-studio-v3`, `ag-grid-community`, `ag-charts`, `bryntum-scheduler-trial`, `apimatic`, `openapi-3.1`, `fastapi`, `python-3.13`, `react-19`, `typescript`, `css-3d`, `sqlite-wal`
