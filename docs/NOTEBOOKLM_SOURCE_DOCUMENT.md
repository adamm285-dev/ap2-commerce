# AP2 Autonomous Commerce — Architectural Source Document
> **Knowledge base for Google NotebookLM & Gemini. Every claim here was checked against the codebase on 2026-10-10. Do not add technologies, metrics or features that are not in this document; Section 12 lists common mistakes to avoid.**
> **Project:** AP2 Autonomous Commerce — Agent Payments Protocol Operations Deck
> **Event:** PayPal AI Hackathon 2026 ($67,500 in cash prizes plus Render credits; deadline November 12, 2026, 12:00 PM PST)
> **Positioning:** Built on AP2 (Agent Payments Protocol) v0.2, the open protocol Google created and donated to the FIDO Alliance in April 2026. Implements v0.2's Human Not Present flow from a desktop AI agent, and extends v0.2 toward AP2's original roadmap: recurring payments and subscriptions, MCP-based implementations, and real-time buyer–seller negotiation.

---

## 1. Executive Summary & Problem Formulation

### 1.1 The Agentic Bottleneck
Autonomous AI agents and automated pipelines increasingly need to buy services such as cloud compute on their own. Today's payment tools create five friction points for them:

1. **Checkout Built for People:** Web checkouts expect a person typing card details. An agent that fills them in must hold the card number, and anyone who can steer the agent can steer the card.
2. **Runaway Budget Risk:** Finance teams can't give an agent a corporate card without limits the agent cannot exceed and a verifiable record of who authorized what.
3. **The Untrusted Courier Problem:** An LLM that holds private signing keys can be manipulated by text it reads (prompt injection) into signing payments its owner never approved.
4. **Disconnected Back-Office Accounting:** After a purchase, people still record recurring expenses in accounting systems (e.g., QuickBooks Online) by hand.
5. **Counterparty Identity:** Agents transacting over the internet have no verified identity unless their keys are enrolled with the party they trade with.

### 1.2 The Solution: AP2 Autonomous Commerce
AP2 Autonomous Commerce is a buyer–seller agent commerce prototype built on AP2 v0.2 with Google's own SDK:

- **Untrusted Courier Architecture (Two MCP Servers):** Claude Desktop (or another agent) carries messages between a **Seller MCP Server** and a separate **Buyer Wallet MCP Server**. The LLM never holds keys. The wallet signs only merchant-signed checkouts that fit the owner's signed limits.
- **Sub-Budget Counter-Offers:** When the buyer's budget cap is below a tier's price, the seller counter-offers the best tier within budget (e.g., the $49.99/mo High-Throughput Batch Worker instead of the $79.99/mo Dedicated AI Service Gateway).
- **AP2 Mandate Verification:** The purchase path verifies ES256 SD-JWT mandate chains with Google's SDK. Raising the price by 1¢ or changing the payee is rejected with `invalid_mandate` and two merchant-signed error receipts.
- **Recurring Payments with Renewal Enforcement:** Monthly PayPal Subscriptions. Every renewal webhook is checked against the owner's signed mandate, and the subscription is cancelled in advance before the payment count, budget or term would run out.
- **Operations Dashboard (React 19 + AG Studio + Bryntum):** Fleet ledger built with AG Studio v3.0.0 and AG Grid Community, plus a Bryntum Scheduler dispatch calendar. **The fleet shown is seeded demo data** (14 subscriptions, 13 active, $1,219.87 MRR, $14,638.44 ARR), not revenue.
- **Back-Office Export:** Builds QuickBooks Online v3 Purchase payloads mapped to General Ledger account 6300 (Dues & Subscriptions: Software & SaaS) and posts them to a configured webhook such as a Zapier catch hook. Without a webhook URL it is a dry run.

---

## 2. Protocol Architecture & The AP2 v0.2 Standard

### 2.1 The AP2 Specification (v0.2 Baseline)
AP2 was created by Google and donated to the FIDO Alliance in April 2026, alongside Mastercard's Verifiable Intent framework. FIDO's Payments Technical Working Group now builds on both. AP2 v0.2, released April 28, 2026, defines open and closed Checkout and Payment Mandates as SD-JWTs signed with ES256, for Human Present and Human Not Present flows.
- **Vendored SDK:** Google's AP2 SDK is vendored in `backend/vendor/ap2/` at upstream commit `e1ea56db`, under the Apache License 2.0, with two documented fixes listed in its `NOTICE` file.
- **SDK Tests:** The 188 tests in `backend/tests/conformance/` are byte-identical to the tests in Google's AP2 repository at that commit, and all pass.

### 2.2 Where This Project Sits Relative to AP2's Roadmap
AP2's original roadmap (September 2025) listed V1.x areas and a long-term vision. It was removed from the repository when v0.2 shipped. The items below are quoted from it:

| AP2 item | Where it stands in AP2 | What this project does |
| :--- | :--- | :--- |
| **Recurring payments & subscriptions** | V1.x roadmap item. v0.2 has an `AgentRecurrence` constraint but no standard renewal flow. | Monthly PayPal Subscriptions; every renewal webhook is re-checked against the owner's mandate, with advance cancellation |
| **Human Not Present purchases** | Shipped in v0.2 | Implemented: a desktop AI agent buys under owner-signed open mandates |
| **MCP-based implementations** | V1.x roadmap item ("detailed sequence diagrams for MCP-based implementations") | Two MCP servers: the seller, and a buyer wallet that keeps keys out of the LLM |
| **Real-time buyer–seller negotiation** | Long-term vision on the original roadmap | The seller counter-offers the best tier within the buyer's stated budget |

---

## 3. Mandate Chains & Cryptographic Invariants

### 3.1 The Three Signers
1. **Owner-Signed Open Mandates (the spending limits):**
   - An open Checkout Mandate (`mandate.checkout.open.1`) and an open Payment Mandate (`mandate.payment.open.1`), SD-JWTs signed with the owner's ES256 key.
   - Constraints: maximum price per purchase, total budget, monthly recurrence (up to 12 payments), the allowed merchant and payee, and the allowed compute tiers.
   - Bound to the wallet's agent key (`cnf`), so only that wallet can use them.
   - The open Checkout Mandate expires after 24 hours (the purchase window); the open Payment Mandate lasts 372 days (12 monthly payments).
2. **Merchant-Signed Checkout (`checkout_jwt`):**
   - Issued by the seller during negotiation (`negotiate_tier_terms`), signed with the merchant's ES256 key (`kid` `ap2-merchant-key-1`).
   - Contains the tier, the price in integer cents, the merchant identity and a nonce.
   - If no merchant key is configured, the server generates a throwaway key at startup (declared mock M-008).
3. **Agent-Signed Closed Mandates:**
   - The wallet produces a closed Checkout Mandate (`mandate.checkout.1`) and a closed Payment Mandate (`mandate.payment.1`), signed with the agent key, only after checking the merchant's checkout against the owner's limits.
   - Bound to the merchant (audience) and the checkout's nonce, so they cannot be replayed on a different order.
4. **Seller Verification (`verify_ap2_chains`):** The seller verifies the whole chain with Google's SDK before creating the subscription or allocating compute.

### 3.2 Key Invariants
- **Fail Closed:** A missing constraint, unparseable claim or unknown algorithm is refused.
- **Trust Roots from the Registry:** Owner and buyer keys are trusted only after enrollment through the single-use challenge flow (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`, Ed25519 or ES256 P-256 keys). Keys supplied in headers or request bodies are ignored.
- **Integer Cents:** Mandate amounts are integer cents (`7999` = $79.99).
- **Signed Error Receipts:** A rejected mandate returns `invalid_mandate` plus two merchant-signed error receipts (checkout and payment) with the reason, for example `PAYMENT_AMOUNT_MISMATCH`.
- **Wallet Refusal Codes:** The wallet refuses with codes such as `PAYMENT_CONSTRAINT_VIOLATION`, `CHECKOUT_CONSTRAINT_VIOLATION`, `OWNER_LIMITS_EXPIRED` and `AGENT_KEY_MISMATCH`, and signs nothing.

---

## 4. The Untrusted Courier Architecture (Two MCP Servers)

### 4.1 The Threat Model
Giving an LLM private signing keys or card numbers creates these risks:
- **Prompt Injection:** Text the LLM reads (a web page, a document, or the seller's own replies) can instruct it to sign a payment the owner never approved. In agent-to-agent commerce the counterparty writes text your agent reads.
- **Model Error:** The LLM can misread terms or overstate its own budget.
- **Context Leakage:** Key material in the context can leak into transcripts, logs or outbound requests.

### 4.2 The Two-Server Isolation Mechanism
Claude Desktop runs two independent MCP servers side by side. The seller and the wallet never talk to each other directly; the LLM carries the merchant-signed checkout between them.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   UNTRUSTED COURIER ARCHITECTURE                       │
│                                                                        │
│    ┌──────────────────────────────────────────────────────────────┐    │
│    │            CLAUDE DESKTOP (Untrusted Courier)                │    │
│    │  • Coordinates the conversation and negotiation              │    │
│    │  • NEVER HOLDS PRIVATE KEYS                                  │    │
│    └──────────────┬───────────────────────────────┬───────────────┘    │
│                   │                               │                    │
│    1. Read limits │                               │ 2. Negotiate       │
│    3. Sign        │                               │ 4. Purchase        │
│       checkout    │                               │                    │
│                   ▼                               ▼                    │
│   ┌───────────────────────────────┐  ┌─────────────────────────────┐   │
│   │   BUYER WALLET MCP SERVER     │  │   SELLER MCP SERVER         │   │
│   │  (backend.wallet.mcp_server)  │  │   (backend.mcp_server)      │   │
│   ├───────────────────────────────┤  ├─────────────────────────────┤   │
│   │ • Holds: agent key (ES256)    │  │ • Holds: merchant key       │   │
│   │ • Holds: owner-signed limits  │  │ • 8 seller tools            │   │
│   │ • Tools: get_spending_limits, │  │ • Verifies AP2 chains       │   │
│   │          sign_checkout        │  │   before purchase           │   │
│   │ • Enforces limits locally     │  │                             │   │
│   └───────────────────────────────┘  └─────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Step 1 (Read Limits):** Claude calls `get_spending_limits` on the wallet. It returns the buyer email, maximum price per purchase, remaining budget, purchases signed so far, allowed merchants and tiers, and when the purchase window and billing term expire.
2. **Step 2 (Negotiate):** Claude calls `negotiate_tier_terms` on the seller with the desired tier and budget cap. The seller returns a merchant-signed `checkout_jwt`, or a counter-offer if the price is over budget.
3. **Step 3 (Verify & Sign):** Claude passes the `checkout_jwt` to the wallet's `sign_checkout`. The wallet verifies the merchant's signature against the pinned merchant key, reads price, tier and merchant from that signature (not from Claude's arguments), and checks them against the owner's limits. Only then does it sign.
4. **Step 4 (Purchase):** Claude hands the signed mandate chains to the seller's `purchase_subscription` tool, which verifies them before creating the subscription.

**Tested attack:** Claude tells the seller its budget is $200 when the owner signed only $60. The seller issues a $79.99 checkout, and the wallet refuses with `PAYMENT_CONSTRAINT_VIOLATION` ("Amount 7999 exceeds maximum 6000"). Nothing is signed.

**What it doesn't stop:** A manipulated agent can still spend up to the owner's limit on something the owner didn't want. The limit is the most that can be lost, so it should be small.

### 4.3 One-Command Setup
```bash
python scripts/setup_claude_desktop_demo.py --monthly-cap 60
```
- Creates three separate keys under the gitignored `.ap2_local/`: merchant, buyer agent (created by the wallet process itself) and owner.
- Enrolls the owner key through the challenge endpoint.
- Has the owner sign limits bound to the agent's key.
- Writes `claude_desktop_config.local.json` with absolute paths.
- Uses its own database (`backend/data/claude_desktop_demo.db`), never the development database.
- Verified by launching both servers exactly as the generated configuration does; not yet run inside the Claude Desktop app itself.

---

## 5. Negotiation & Sub-Budget Counter-Offers

### 5.1 Compute Catalog
- **`ap2-batch` (High-Throughput Batch Worker):** $49.99/month (4,999 cents), 125 workload tasks/month.
- **`ap2-gateway` (Dedicated AI Service Gateway):** $79.99/month (7,999 cents), 450 workload tasks/month.
- **`ap2-cluster` (Enterprise Cluster Node):** $179.99/month (17,999 cents), 1,200 workload tasks/month.

### 5.2 Counter-Offer Logic
When a buyer asks for a tier above its stated budget (e.g., `ap2-gateway` at $79.99/mo with a $60.00/mo cap):
1. The seller sees that the tier's price exceeds the cap.
2. Instead of a flat rejection, it counter-offers the best tier within budget: the High-Throughput Batch Worker at $49.99/mo.
3. The response explains that the requested plan lists at $79.99/mo, above the $60.00 cap, and offers the down-tier.
4. The agent can accept. The wallet signs only if $49.99 fits the owner's signed limits.

---

## 6. Payment Rails & Lifecycle Management

### 6.1 PayPal Subscriptions
- **Subscriptions:** Created through PayPal's Subscriptions REST API. Human buyers use `@paypal/react-paypal-js` buttons. In live mode, the Python PayPal Agent Toolkit looks up subscription details.
- **Mock Mode:** PayPal calls are simulated (M-002) and buyer approval is simulated (M-004). Mock subscription IDs look like `I-A2A-VAULT-...`; the name is a label, and no PayPal Vault token is created.
- **Webhooks:** Signatures are checked with PayPal's verify-webhook-signature API in live mode and a local HMAC in mock mode (M-003).
- **Persistence:** Subscriptions, stored mandates and renewal records live in SQLite in WAL mode (`a2a_commerce.db`) with a 5,000 ms busy timeout.

### 6.2 Renewal Enforcement (Month 2 and Beyond)
- **On every `PAYMENT.SALE.COMPLETED`:** the server re-checks the stored owner mandate (integrity, registry key, email binding), its expiry, the SDK limits (budget and payment count) and the agreed price.
- **Advance cancellation:** PayPal reports a sale after the money moves, so detection alone can't stop a bad charge. After each authorized charge, the server checks whether the next charge would be allowed and cancels the subscription in advance when the payment count, budget or term would run out.
- **After-the-fact cases:** A price change or other out-of-mandate charge is caught after it happens. Violations cancel the subscription, unverifiable charges suspend it, and refunds are manual.
- **Scope:** Applies to agent-bought subscriptions; subscriptions a person approved in PayPal are left alone.

### 6.3 What Is Verified Today
- **Verified (automated tests, mock mode):** first purchase, counter-offer signing, AP2 chain verification, wallet refusals, renewal checks and advance cancellation.
- **Not yet verified:** renewal webhooks against the live PayPal sandbox (the subscription ID field in the sale payload is assumed), and a run inside the Claude Desktop app.
- **Not yet built:** renewing the owner's mandate after payment 12 (the subscription cancels and year two needs new limits), and checking the spacing between charges.

---

## 7. Operations Dashboard & Front-End Architecture

### 7.1 AG Studio v3.0.0 & AG Grid Community Fleet Ledger
- **Embedded AG Studio v3.0.0:** `ag-studio-react` and `ag-studio` with AG Grid Community, at `/portal/`.
- **Floating Column Filters:** Every grid column has a floating filter (`floatingFilter: true`, 34px filter row).
- **View / Edit Modes:** Operators can switch between viewing the dashboard and rearranging its widgets.
- **Data Source:** The grid reads `/api/fleet/subscriptions` from SQLite. That fleet is **seeded demo data** (M-009), and the frontend shows hardcoded sample data before backend data arrives (M-018).
- **Demo Fleet Figures:** 14 subscriptions (13 active, 1 pending deposit), $1,219.87/mo MRR, $14,638.44 ARR. These are reconciled to the cent but are not revenue.

### 7.2 Bryntum Scheduler (Compute Dispatch Calendar)
- **Build:** `@bryntum/scheduler` 7.3.7 trial build.
- **Status Transitions:** A demo button provisions a node through the backend, and its schedule card changes from `AWAITING PAYPAL` (amber) to active (green). The button stands in for a real payment event (M-019); the schedule itself is seeded (M-009).

### 7.3 Protocol Inspector & Anti-Tamper Playground
- **SSE Stream (`/sse`):** Streams the JSON-RPC 2.0 frames (`initialize` → `tools/list` → `tools/call`) for the inspector.
- **Anti-Tamper Playground:** An interactive view where judges change characters in a signed JSON payload (e.g., +1¢ or a different payee) and see it rejected with `401 Signature Mismatch: Budget Policy Violated`. It uses a separate Ed25519/HMAC demo signer with demo keys (M-014), not the AP2 purchase path.

---

## 8. Back-Office Export (Zapier-Ready)

### 8.1 What `dispatch_zapier_mcp` Does
The `dispatch_zapier_mcp` seller tool (called by the buyer agent script or any MCP client after a purchase):
1. **QuickBooks Online v3:** Builds a Purchase payload mapping the subscription expense to General Ledger account 6300 (Dues & Subscriptions: Software & SaaS), referencing the PayPal subscription ID.
2. **Fleet Routing:** Records the provisioned node endpoint for monitoring.
3. **Calendar:** Builds a payload for a recurring node health check.
4. **Security:** Validates target URLs against SSRF and signs outbound envelopes with HMAC-SHA256.

### 8.2 Limits
- Without a webhook URL, the export is a dry run with no network call. Workflows other than onboarding return made-up ERP, QuickBooks and calendar IDs (M-011).
- The "workload dispatch" scenario is simulated entirely in the browser (M-020).
- The back-office run log now shows what the backend returned, including dry runs labelled as dry runs and the backend's own signature and delivery ID.

---

## 9. Prize Track Alignment

| Prize | Amount | What this project offers |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** (main prize) | $5,000 | AP2 mandate negotiation, counter-offers, an isolated buyer wallet, and recurring PayPal subscriptions checked against the owner's mandate |
| **Best Use of PayPal + AI** (main prize) | $5,000 | MCP seller server driven by a desktop AI agent, PayPal Subscriptions and webhooks, the PayPal Agent Toolkit, and renewal enforcement |
| **AG Grid** (sponsor) | $5,000 (1st) | Embedded AG Studio v3.0.0 (`ag-studio-react`), AG Grid Community with floating filters, View / Edit modes |
| **Bryntum** (sponsor) | $1,000 | Bryntum Scheduler (trial build) dispatch calendar with status transitions |
| **APIMatic** (sponsor) | $1,000 + 6-month subscription | OpenAPI 3.1.0 specification with 48 paths (51 operations) and `apimatic.json` SDK configuration |

There is no Zapier prize. The main prizes also include 1st ($12,000), 2nd ($8,000), 3rd ($5,000), Most Creative, Most Impactful and Best Demo Delivery ($5,000 each).

---

## 10. Verification & Judge Audit

### 10.1 The 9-Check Judge Audit (`python scripts/judge_audit_harness.py`)
Runs in-process against a temporary database in about a second, with no API keys:
1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** `initialize` and `tools/list` return the 8 seller tools.
2. **[CHECK 2] Standard AP2 Negotiation:** The $79.99/mo Service Gateway under a $100 budget cap, with ES256 SD-JWT mandate chains.
3. **[CHECK 3] Sub-Budget Counter-Offer:** A *Batch Worker* ($49.99/mo) counter-offer when the cap is $60.00.
4. **[CHECK 4] Anti-Tamper Verification:** 1¢ price inflation, payee changes and budget breaches rejected with `invalid_mandate` and signed error receipts.
5. **[CHECK 5] Compute Node Provisioning:** Subscription verification and placeholder node endpoints (`batch-01`, `gateway-01`, `cluster-01`); nothing is actually provisioned (M-010).
6. **[CHECK 6] Back-Office Payloads:** A QuickBooks Online v3 Purchase payload mapped to GL account 6300 (generated, not delivered).
7. **[CHECK 7] Fleet Telemetry:** The 14 seeded demo subscriptions, $1,219.87/mo MRR and $14,638.44 ARR, reconciled to the cent.
8. **[CHECK 8] AG Studio & Bryntum Data:** Loads the 14 seeded nodes and the compute schedule.
9. **[CHECK 9] Buyer Key Onboarding:** A 300-second single-use challenge, signature verification, key enrollment, and rejection of a forged signature.

### 10.2 Automated Test Suite
```bash
python -m pytest backend/tests -q -n 4
# Result: 572 passed, 9 skipped in under a minute
```
- 188 tests are Google's AP2 SDK tests (byte-identical to upstream); 384 are project tests.
- The 9 skipped tests need live services (4 call the PayPal sandbox, 5 probe a deployed server) and run only when explicitly enabled.
- Includes 21 buyer wallet tests (`test_buyer_wallet.py`) and 23 renewal enforcement tests (`test_recurring_mandate_renewals.py`).
- `conftest.py` points every test at a temporary database, so the development database is never touched.

### 10.3 Declared Mocks
Every stand-in for real behavior is listed in `docs/MOCKS.md` (19 entries, M-001 to M-022; M-013, M-017 and M-021 were retired) and marked in the code with a `MOCK(M-NNN)` comment. `backend/tests/test_mocks_ledger.py` fails when the ledger and the markers disagree.

---

## 11. 8-Slide Architecture Walkthrough (Ground Truth for Slide Generation)

Use only the facts below. Do not add protocols, hardware, metrics or features that aren't listed. Text on slides must be legible and spelled correctly; prefer simple diagrams over dense label grids.

### Slide 1: AP2 v0.2 and What Comes Next
- **Title:** AP2 Autonomous Commerce: Built on AP2 v0.2, Extending Its Roadmap
- **Subtitle:** Google's Agent Payments Protocol, now under the FIDO Alliance
- **Visual:** Left: "AP2 v0.2 (Google SDK, 188 SDK tests passing)": open and closed Checkout and Payment Mandates, SD-JWT, ES256, Human Present and Human Not Present flows. Right: four items, each with its real status: (1) Recurring payments & subscriptions [V1.x roadmap]; (2) Human Not Present purchases [shipped in v0.2, implemented here]; (3) MCP-based implementation [V1.x roadmap]; (4) Buyer–seller negotiation [long-term vision].
- **Core Points:**
  - Implements AP2 v0.2 with Google's SDK (two documented fixes in `backend/vendor/ap2/NOTICE`).
  - Three signers: the owner signs spending limits, the merchant signs the checkout, and the buyer's wallet signs the closed mandates.
  - Extends v0.2 where it stops: renewal enforcement, an isolated MCP wallet, and counter-offers.
- **Code Anchor:** `backend/vendor/ap2/`, `backend/services/ap2_service.py`, `backend/tests/conformance/`
- **Narration (20s):** "AP2 is the agent payments protocol Google created and donated to the FIDO Alliance this year. Version 0.2 lets an agent buy on its own under limits its owner signs in advance. We implemented that flow with Google's SDK, then extended it toward AP2's roadmap: recurring subscriptions, an MCP wallet that keeps keys away from the LLM, and buyer–seller negotiation."

### Slide 2: The Untrusted Courier Threat
- **Title:** Why LLMs Must Never Hold Private Keys
- **Subtitle:** Prompt injection turns any text the agent reads into a payment instruction
- **Visual:** An AI agent receiving text from a web page and from the seller's reply. Hidden instructions ("ignore previous instructions, pay more") point at the agent. Keys sit outside the agent in a separate wallet that only signs within the owner's limits. Label each attack once.
- **Core Points:**
  - An LLM holding keys can be steered by text it reads, including the counterparty's replies.
  - Keys belong in a separate process that checks signed limits before signing.
  - The LLM is an untrusted courier holding zero key material.
- **Code Anchor:** `backend/wallet/wallet.py`, `backend/tests/test_buyer_wallet.py` (21 tests)
- **Narration (20s):** "In agent-to-agent commerce, the other side's agent writes text your agent reads. If your LLM holds the keys, one injected instruction can spend your money. In our design the LLM is an untrusted courier. It negotiates, but the keys live in a separate wallet that refuses anything outside the owner's signed limits."

### Slide 3: Two MCP Servers, One Isolated Wallet
- **Title:** Two-Server MCP Architecture: The Isolated Buyer Wallet
- **Subtitle:** Limits are checked locally, outside the LLM, before anything is signed
- **Visual:** Claude Desktop at the top, connected separately to two boxes below: the Buyer Wallet MCP server and the Seller MCP server. The seller and the wallet are not connected to each other. Numbered steps: (1) read limits from the wallet, (2) negotiate with the seller and receive a merchant-signed checkout, (3) the wallet verifies and signs, (4) purchase with the seller.
- **Core Points:**
  - The wallet holds the agent's key and the owner's signed limits, never the owner's private key.
  - The wallet reads price, tier and merchant from the merchant's signature, not from the LLM's arguments.
  - Overspending is refused before signing: `PAYMENT_CONSTRAINT_VIOLATION` ("Amount 7999 exceeds maximum 6000").
- **Code Anchor:** `backend/wallet/mcp_server.py`, `scripts/setup_claude_desktop_demo.py`
- **Narration (20s):** "Claude Desktop runs two separate MCP servers: the seller, and the buyer's wallet. Claude carries the merchant-signed checkout from one to the other. The wallet checks the merchant's signature and the price against the owner's limits. When we told the seller our budget was $200 but the owner had signed $60, the wallet refused to sign."

### Slide 4: Recurring Billing & Renewal Enforcement
- **Title:** Recurring Billing: Enforcing the Owner's Mandate Every Month
- **Subtitle:** Webhook checks, advance cancellation, and separate purchase and billing windows
- **Visual:** Two timelines. Top: a 24-hour purchase window. Bottom: a 372-day billing term with 12 monthly `PAYMENT.SALE.COMPLETED` events; after **each** event, a small "next charge allowed?" check; after the last authorized payment, a "cancel in advance" marker before the 13th charge.
- **Core Points:**
  - Every renewal webhook is re-checked against the owner's stored mandate with Google's SDK.
  - PayPal reports a sale after the money moves, so the server cancels in advance when the payment count, budget or term would run out.
  - A price change or other out-of-mandate charge is caught after it happens: it cancels; unverifiable charges suspend; refunds are manual. Tested in mock mode.
- **Code Anchor:** `backend/services/recurring_mandate_service.py`, `backend/server.py`, `backend/database.py`
- **Narration (20s):** "AP2 v0.2 has no standard for subscriptions. We built one on PayPal Subscriptions. Every renewal is re-checked against the owner's signed mandate. Because PayPal reports a charge after the money moves, we check the next charge in advance and cancel before the payment count, budget or term runs out."

### Slide 5: Counter-Offers & Tamper Rejection
- **Title:** Counter-Offers and Tamper Rejection
- **Subtitle:** Merchant-signed counter-offers within budget; a 1¢ change is rejected
- **Visual:** Left: "$60 cap" → "$79.99 Dedicated AI Service Gateway" (crossed out) → "$49.99 High-Throughput Batch Worker" (accepted). Right: two real outputs, trimmed: the judge harness line `Tamper Test (+1¢ Inflation $79.99 -> $80.00): REJECTED (invalid_mandate)` and the wallet refusal `{"status": "REFUSED", "error": "PAYMENT_CONSTRAINT_VIOLATION"}`. Use only these codes.
- **Core Points:**
  - The seller counter-offers the best tier within the buyer's stated budget.
  - Mandate amounts are integer cents.
  - Raising the price by 1¢ or changing the payee is rejected with `invalid_mandate` and two merchant-signed error receipts (checkout and payment).
- **Code Anchor:** `backend/agents/seller_agent.py`, `backend/services/ap2_service.py`, `scripts/judge_audit_harness.py` (Checks 3 & 4)
- **Narration (20s):** "When the buyer's budget is too low, the seller counter-offers the best plan that fits, in a merchant-signed checkout. If anyone raises the price by a single cent or swaps the payee, AP2 verification rejects the mandate and the seller returns signed error receipts explaining why."

### Slide 6: Demo Fleet Operations (Seeded Data)
- **Title:** Demo Fleet Operations: Dashboard, Dispatch and Accounting Payloads
- **Subtitle:** AG Studio, Bryntum Scheduler and QuickBooks payloads over seeded demo data
- **Visual:** Use real screenshots of the AG Studio fleet ledger and the Bryntum Scheduler, with a visible "Demo data" label. Right: a QuickBooks Online Purchase payload mapped to GL account 6300 marked "generated (dry run)". Do not generate fake tables, times or timestamps.
- **Core Points:**
  - AG Studio v3.0.0 and AG Grid Community show a seeded fleet: 14 subscriptions, 13 active, $1,219.87 MRR, $14,638.44 ARR (demo data, not revenue).
  - Bryntum Scheduler shows the compute dispatch calendar; a demo button triggers status changes.
  - Back-office export builds QuickBooks payloads for GL account 6300 and sends them to a configured webhook; without one it is a dry run.
- **Code Anchor:** `src/components/EnterpriseFleetLedger.tsx`, `src/components/BryntumDispatchScheduler.tsx`, `backend/services/backoffice/qbo_exporter.py`
- **Narration (20s):** "After a purchase, operators see the fleet in AG Studio and Bryntum Scheduler. The fleet here is seeded demo data, and we label it that way. The back-office export builds QuickBooks expense payloads mapped to account 6300, ready to send to a Zapier hook once one is configured."

### Slide 7: The Production Gap Report
- **Title:** The Production Gap Report
- **Subtitle:** What a production version still needs
- **Visual:** A 2x2 matrix plus a short list. Matrix: (1) Keys: files on disk → hardware-backed keys / passkeys. (2) Replay protection: in-memory caches → shared store. (3) Rails: the seller verifies AP2 → payment networks verify AP2 directly. (4) Revocation: expiry only → a mandate status (revocation) list. List: renewal of limits after payment 12, charge-spacing checks, sandbox verification of renewal webhooks, 19 declared mocks in `docs/MOCKS.md`.
- **Core Points:**
  - Keys are files on disk today; production needs hardware-backed keys.
  - Replay and challenge caches live in memory and clear on restart; production needs a shared store.
  - PayPal doesn't verify AP2 mandates yet, so the seller verifies them; the owner can't revoke limits early, only wait for them to expire.
- **Code Anchor:** `backend/services/ap2_keys.py`, `backend/services/ap2_service.py`, `docs/MOCKS.md`
- **Narration (20s):** "A responsible prototype names its limits. Keys sit on disk and need hardware backing. Replay caches live in memory and need a shared store. Payment networks don't verify AP2 yet, so our seller does. Mandates can't be revoked early, renewals haven't run against the PayPal sandbox, and every remaining mock is declared."

### Slide 8: Verification
- **Title:** Verification: Tests, Judge Audit and Declared Mocks
- **Subtitle:** 572 passing tests, 9/9 judge checks, 19 declared mocks
- **Visual:** Three panels. Left: "572 passed, 9 skipped": 188 Google AP2 SDK tests + 384 project tests; the 9 skipped need live services (PayPal sandbox, deployed server). Middle: "9/9 judge checks, about 1 second, no API keys." Right: "19 declared mocks in docs/MOCKS.md, checked by a test."
- **Core Points:**
  - The 188 SDK tests are byte-identical to Google's upstream tests.
  - The judge audit runs in-process against a temporary database with no API keys.
  - Every simulated piece is declared, and a test fails if the declarations drift from the code.
- **Code Anchor:** `scripts/judge_audit_harness.py`, `backend/tests/`, `docs/MOCKS.md`
- **Narration (20s):** "Everything here is backed by tests: 572 passing, including Google's own 188 AP2 SDK tests unchanged, and a 9-check judge audit that runs in about a second with no API keys. And because prototypes fake things, every simulated piece is declared in a mock ledger that a test keeps honest."

---

## 12. Accuracy Guardrails (Common Mistakes to Avoid)

This project does **not** use or claim any of the following. Do not depict them:
- FastMCP (the MCP servers are hand-written JSON-RPC).
- PayPal Vault tokens or Vault MIT (payments use PayPal Subscriptions).
- Secure enclaves, TEEs, hardware keys, WebAuthn or FIDO2 authentication (keys are files on disk today; this is a listed gap).
- Zero-knowledge proofs, multi-signature schemes, blockchain addresses or `0x` hex identifiers.
- TLS/Noise channel specifications, mDNS/DHT discovery, JSON-LD, or auction-based bidding.
- RSA keys (AP2 signatures here are ES256).
- Daily or weekly billing, or usage-based pricing (billing is monthly).
- An "AP2 V1.x working group" or a submitted standards contribution (FIDO's group is the Payments Technical Working Group; this project hasn't submitted anything).
- Error codes such as `BUDGET_CAP_EXCEEDED` or `PAYEE_NOT_ALLOWED` (use `invalid_mandate`, `PAYMENT_AMOUNT_MISMATCH`, `PAYMENT_CONSTRAINT_VIOLATION`).
- Real revenue or ARR (the fleet figures are seeded demo data).
- Floating-point dollar amounts in mandate payloads (amounts are integer cents).

---

### Slide Summary Table (For README & Devpost)

| Slide | Title | Core Technical Point | Code Anchor |
| :---: | :--- | :--- | :--- |
| **01** | **AP2 v0.2 Baseline & Roadmap** | AP2 v0.2 (now under the FIDO Alliance) implemented with Google's SDK; Human Not Present implemented; recurring payments, MCP and negotiation extended | `backend/vendor/ap2/`, `backend/tests/conformance/` |
| **02** | **The Untrusted Courier Threat** | Why LLMs must never hold private signing keys | `backend/wallet/wallet.py`, `backend/tests/test_buyer_wallet.py` |
| **03** | **Two-Server MCP Architecture** | The wallet holds the agent key and owner-signed limits (never the owner's private key); overspending is refused before signing | `backend/wallet/mcp_server.py`, `scripts/setup_claude_desktop_demo.py` |
| **04** | **Recurring Billing & Renewal Enforcement** | Webhook re-verification, plus advance cancellation before the payment count, budget or term runs out | `backend/services/recurring_mandate_service.py`, `backend/server.py` |
| **05** | **Counter-Offers & Anti-Tamper** | Counter-offer to the $49.99 Batch Worker; 1¢ inflation rejected with `invalid_mandate` | `backend/services/ap2_service.py`, `backend/wallet/wallet.py` |
| **06** | **Demo Fleet Operations (Seeded Data)** | AG Studio v3.0.0 (`EnterpriseFleetLedger.tsx`), Bryntum Scheduler and QuickBooks GL 6300 payloads over seeded demo data | `src/components/EnterpriseFleetLedger.tsx`, `backend/services/backoffice/qbo_exporter.py` |
| **07** | **The Production Gap Report** | Disk keys, in-memory replay caches, no revocation, no native AP2 rail, renewal edge cases, 19 declared mocks | `backend/services/ap2_keys.py`, `docs/MOCKS.md` |
| **08** | **Verification** | 572 passing tests (188 SDK + 384 project); 9/9 judge checks in about a second; 19 declared mocks | `pytest backend/tests/ -q -n 4`, `scripts/judge_audit_harness.py` |
