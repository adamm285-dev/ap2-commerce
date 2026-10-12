# AP2 Autonomous Commerce &mdash; Agent Payments Protocol Operations Deck

> **Built on AP2 (Agent Payments Protocol) v0.2**, the open protocol Google created and donated to the FIDO Alliance in April 2026. It implements v0.2's Human Not Present flow from a desktop AI agent and extends v0.2 toward items on AP2's original roadmap:
> 1. **Recurring payments & subscriptions** (V1.x): monthly PayPal renewals checked against the owner's signed AP2 mandate, with advance cancellation.
> 2. **MCP-based implementation** (V1.x): a seller MCP server plus a separate buyer-wallet MCP server, so the LLM never holds signing keys.
> 3. **Real-time buyer–seller negotiation** (long-term vision): merchant-signed counter-offers within the buyer's budget.
>
> Uses **PayPal Subscriptions** and the **PayPal Agent Toolkit**, **AG Studio v3.0.0 & AG Grid Community**, **Bryntum Scheduler**, and an **OpenAPI 3.1.0 / APIMatic** contract. Parts of the dashboard run on seeded demo data; every simulated piece is declared in [`docs/MOCKS.md`](docs/MOCKS.md).

[![AG Studio: v3.0.0](https://img.shields.io/badge/AG%20Studio-v3.0.0-blue.svg)](https://www.ag-grid.com/studio/react/)
[![PayPal Agent Toolkit](https://img.shields.io/badge/PayPal-Agent%20Toolkit-003087.svg)](https://github.com/paypal/AI-Toolkit)
[![OpenAPI 3.1.0](https://img.shields.io/badge/OpenAPI-3.1.0-green.svg)](openapi.yaml)
[![Tests: 572 Passed](https://img.shields.io/badge/Tests-572%20Passed%2C%209%20Skipped-brightgreen.svg)](backend/tests/)
[![Judge Audit: 9/9 Passed](https://img.shields.io/badge/Judge%20Audit-9%2F9%20Passed-brightgreen.svg)](scripts/judge_audit_harness.py)

---

## 🌐 System Endpoints & Interfaces

| Resource | Protocol / Location | Description |
| :--- | :--- | :--- |
| **Interactive Operations Deck** | React 19 + AG Studio + Bryntum UI (`/portal/`) | Visual command center with a live protocol inspector. Fleet and schedule views use seeded demo data (M-009). |
| **Seller MCP Server** | MCP 2024-11-05, JSON-RPC 2.0 over stdio (`backend.mcp_server`) and HTTP (`/mcp`) | Hand-written MCP server exposing 8 seller tools |
| **Buyer Wallet MCP Server** | MCP over stdio, JSON-RPC 2.0 (`backend.wallet.mcp_server`) | Separate process holding the agent's key and the owner-signed limits; signs only checkouts that fit them |
| **Live SSE Wire Stream** | Server-Sent Events (`/sse`) | JSON-RPC 2.0 frames for the protocol inspector |
| **OpenAPI 3.1.0 Specification** | `openapi.yaml` & `openapi.json` | 48 paths (51 operations) covering negotiation, mandates, subscriptions and back-office export |
| **Interactive API Documentation**| Swagger UI (`/docs`) | REST endpoint documentation and schema explorer |
| **Agent Discovery Card** | JSON metadata (`/agents.json`) | Machine-readable capability and discovery descriptor |

---

## ⚡ Quickstart for Judges & Evaluators

> **⚠️ Quick Evaluation Note:** Run **`python scripts/judge_audit_harness.py`** first. It needs no API keys, runs in-process against a temporary database in about a second, and checks 9 protocol and operational invariants, including AP2 v0.2 ES256 SD-JWT mandate chains. Checks 7 and 8 report the seeded demo fleet, not real revenue.

### 0. Clone & Environment Setup
Configure the local mock environment, install dependencies, and launch the frontend:
```bash
cp .env.example .env
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
npm install
npm run dev
```

### 1. One-Click Judge Audit (No API Keys)
Run the 9-check audit in-process against the seller engine:
```bash
python scripts/judge_audit_harness.py
# 9/9 checks passed
```

### 2. Run the Full Automated Test Suite
```bash
pytest backend/tests/ -q -n 4
# 572 passed, 9 skipped (188 tests from Google's AP2 SDK + 384 project tests; the 9 skipped need live services: 4 call the PayPal sandbox, 5 probe a deployed server)
```
The 188 SDK tests in `backend/tests/conformance/` are byte-identical to the tests in Google's AP2 repository at the vendored commit. Tests run against temporary databases, never the development database.

### 3. Run the Buyer Agent CLI
Simulate a buyer agent negotiating and provisioning a compute node under owner-signed limits:
```bash
python -m backend.agents.llm_buyer_agent --budget 60 --tier ap2-gateway
```
By default this is a scripted, offline buyer (M-015). Pass `--provider` and `--model` to drive it with a real LLM.

### 4. Buy with a Desktop AI Agent (Seller MCP + Isolated Wallet MCP)
Claude Desktop runs two MCP servers side by side: the seller (`backend.mcp_server`) and the buyer's wallet (`backend.wallet.mcp_server`). The agent negotiates with the seller, asks the wallet to sign, and hands the signed AP2 v0.2 mandate chains back to the seller. The seller and the wallet never talk to each other directly.

The agent is an **untrusted courier** and never sees private keys. The wallet signs only checkouts that fit the owner's signed limits, even if the agent is talked into claiming a larger budget.

```bash
python scripts/setup_claude_desktop_demo.py --monthly-cap 60
```

The script:
1. Creates three separate keys under the gitignored `.ap2_local/`: merchant, buyer agent (created by the wallet process itself), and owner.
2. Enrolls the owner key through the challenge flow.
3. Has the owner sign $60/mo limits bound to the wallet's agent key.
4. Generates a Claude Desktop configuration (`claude_desktop_config.local.json`) with absolute paths.

Copy its entries into your Claude Desktop configuration and launch. The demo uses its own database (`backend/data/claude_desktop_demo.db`), never the dev database. Then instruct the agent: *"Check my wallet's spending limits, then buy the best AP2 compute plan you can within them."*

This flow has been verified by launching both servers exactly as the generated configuration does; it has not yet been run inside the Claude Desktop app itself.

---

## 1. Executive Summary: AP2 v0.2 and What Comes Next

AP2 v0.2 defines open and closed Checkout and Payment Mandates as SD-JWTs signed with ES256, for both Human Present and Human Not Present flows. Google donated AP2 to the FIDO Alliance in April 2026. AP2 Autonomous Commerce implements v0.2 with Google's SDK vendored in `backend/vendor/ap2/` (two documented fixes, listed in its `NOTICE`) and extends it where v0.2 stops.

The roadmap items below are quoted from AP2's original roadmap (September 2025), which was removed from the repository when v0.2 shipped.

| AP2 item | Where it stands in AP2 | What this project does |
| :--- | :--- | :--- |
| **Recurring payments & subscriptions** | V1.x roadmap item. v0.2 has an `AgentRecurrence` constraint but no standard renewal flow. | Monthly PayPal Subscriptions; every renewal webhook is re-checked against the owner's mandate, with advance cancellation |
| **Human Not Present purchases** | Shipped in v0.2 | Implemented: a desktop AI agent buys under owner-signed open mandates |
| **MCP-based implementations** | V1.x roadmap item ("detailed sequence diagrams for MCP-based implementations") | Two MCP servers: the seller, and a buyer wallet that keeps keys out of the LLM |
| **Real-time buyer–seller negotiation** | Long-term vision on the original roadmap | The seller counter-offers the best tier within the buyer's stated budget |

### Core Innovations:
- **Untrusted Courier Architecture (Prompt Injection Defense):** An LLM that holds signing keys can be steered by any text it reads, including the seller's own replies. Keys live in `backend.wallet.mcp_server`, a separate process. The LLM negotiates; the wallet verifies the checkout against the pinned merchant key, checks the price against the owner-signed limits, and raises `WalletRefusal` before signing if they don't fit. Tested: an agent that tells the seller its budget is $200 is refused at $79.99 because the owner signed $60 (`PAYMENT_CONSTRAINT_VIOLATION`).
- **Renewal Verification & Advance Cancellation:** In `backend/services/recurring_mandate_service.py`, every PayPal renewal webhook (`PAYMENT.SALE.COMPLETED`) is checked against the owner's stored mandate with Google's SDK: stored-mandate integrity, registry key, email binding, expiry, limits and the agreed price. PayPal reports a sale after the money moves, so after each authorized charge the server also checks whether the next charge would be allowed, and cancels the subscription in advance when the payment count, budget or term would run out. A price change or other out-of-mandate charge is caught after it happens: violations cancel the subscription, unverifiable charges suspend it, and refunds are manual. Tested in mock mode; not yet run against the PayPal sandbox.
- **Decoupled Purchase vs Recurring Windows:** The owner's authorization gives a 24-hour window to complete the initial checkout, while the recurring payment authority lasts 372 days (12 monthly payments).
- **Multi-Tier Counter-Offers:** When the buyer's budget cap is below the asking price ($60 cap vs the $79.99 Dedicated AI Service Gateway), the seller agent counter-offers the best tier within budget (*High-Throughput Batch Worker at $49.99/mo*) in a merchant-signed checkout. The buyer's wallet signs it only if the price fits the owner's limits.
- **AP2 Anti-Tamper Checks:** The purchase path verifies ES256 SD-JWT mandate chains with Google's SDK. Raising the agreed price by 1¢ ($79.99 &rarr; $80.00) or changing the payee fails with `invalid_mandate`, and the seller returns two merchant-signed error receipts (checkout and payment). The separate interactive anti-tamper playground (`/api/crypto/verify-tamper`) uses an Ed25519/HMAC demo signer with demo keys (M-014) and returns `401 Signature Mismatch: Budget Policy Violated`.
- **Self-Service Buyer Key Onboarding:** Buyer agents register Ed25519 or ES256 (P-256) public keys through a single-use challenge-response flow (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`).
- **Back-Office Export:** Builds QuickBooks Online v3 Purchase payloads mapped to GL account 6300 (Dues & Subscriptions: Software & SaaS) plus calendar payloads, and posts them to a configured webhook such as a Zapier catch hook. Without a webhook URL the export is a dry run (M-011).
- **AG Studio v3.0.0 & AG Grid Community Analytics:** Fleet ledger with floating column filters, View and Edit modes, and compute analytics read from SQLite (WAL mode). The fleet it shows is seeded demo data: 14 subscriptions, 13 active, $1,219.87 MRR and $14,638.44 ARR. Those rows are labelled `Demo data` (M-009) and aren't revenue.

---

## 2. Executive Architecture Walkthrough (8 Slides)

The 8-slide walkthrough reflects the codebase as of 2026-10-10:

| Slide | Title | Core Technical Point | Code Anchor |
| :---: | :--- | :--- | :--- |
| **01** | **AP2 v0.2 Baseline & Roadmap** | AP2 v0.2 (now under the FIDO Alliance) implemented with Google's SDK; Human Not Present implemented; recurring payments, MCP and negotiation extended | `backend/vendor/ap2/`, `backend/tests/conformance/` |
| **02** | **The Untrusted Courier Threat** | Why LLMs must never hold private signing keys | `backend/wallet/wallet.py`, `backend/tests/test_buyer_wallet.py` |
| **03** | **Two-Server MCP Architecture** | The wallet holds the agent key and owner-signed limits (never the owner's private key); overspending is refused before signing | `backend/wallet/mcp_server.py`, `scripts/setup_claude_desktop_demo.py` |
| **04** | **Recurring Billing & Renewal Enforcement** | Webhook re-verification, plus advance cancellation before the payment count, budget or term runs out | `backend/services/recurring_mandate_service.py`, `backend/server.py` |
| **05** | **Counter-Offers & Anti-Tamper** | Counter-offer to the $49.99 Batch Worker; 1¢ inflation rejected with `invalid_mandate` | `backend/services/ap2_service.py`, `backend/wallet/wallet.py` |
| **06** | **Demo Fleet Operations (Seeded Data)** | AG Studio v3.0.0 (`EnterpriseFleetLedger.tsx`), Bryntum Scheduler and QuickBooks GL 6300 payloads over seeded demo data | `src/components/EnterpriseFleetLedger.tsx`, `backend/services/backoffice/qbo_exporter.py` |
| **07** | **The Production Gap Report** | Disk keys, in-memory replay caches, no revocation, no native AP2 rail, renewal edge cases, 19 declared mocks | `backend/services/ap2_keys.py`, `docs/MOCKS.md` |
| **08** | **Empirical Verification** | 572 passing tests (188 SDK + 384 project); 9/9 judge checks in about a second | `pytest backend/tests/ -q -n 4`, `scripts/judge_audit_harness.py` |

---

## 3. Subsystem Architecture & Technology Integrations

- **PayPal Subscriptions & Agent Toolkit:** Subscriptions created through PayPal's REST API; `@paypal/react-paypal-js` buttons for human checkout; the Python PayPal Agent Toolkit for subscription lookups in live mode; webhook verification (PayPal's verify-webhook-signature API in live mode, a local HMAC in mock mode, M-003); cancel and suspend calls for renewal enforcement. Mock mode simulates PayPal calls (M-002).
- **AG Studio v3.0.0 & AG Grid Community:** Embedded operations console using `ag-studio-react`, floating column filters (34px row), and View / Edit modes, reading fleet data from SQLite. The fleet is seeded demo data (M-009).
- **MCP Servers & SSE Stream:** A hand-written MCP (2024-11-05) seller server over stdio and HTTP, a separate buyer-wallet MCP server over stdio, and a Server-Sent Events stream of JSON-RPC frames for the inspector.
- **Bryntum Workload Scheduler:** Dispatch calendar for compute shifts (Bryntum Scheduler 7.3.7 trial build). A demo button provisions a node through the backend and its card turns from `AWAITING PAYPAL` to active (M-019). The schedule itself is seeded (M-009).
- **Back-Office Export (Zapier-ready):** `dispatch_zapier_mcp` builds QuickBooks Online v3 expense payloads (GL account 6300) and calendar payloads, signs outbound envelopes with HMAC-SHA256, validates target URLs against SSRF, and posts to a configured webhook. Without one it's a dry run (M-011).
- **APIMatic & OpenAPI 3.1.0 Contract:** OpenAPI specification with 48 paths (51 operations) in `openapi.yaml` and `openapi.json`, plus `apimatic.json` for multi-language SDK generation.

---

## 4. The 9 Judge Audit Checks

1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** `initialize` and `tools/list` return the 8 registered seller tools.
2. **[CHECK 2] Standard AP2 Negotiation:** The \$79.99/mo Service Gateway under a \$100 budget cap, with ES256 SD-JWT mandate chains.
3. **[CHECK 3] Sub-Budget Counter-Offer:** A *Batch Worker* (\$49.99/mo) counter-offer when the cap is \$60.00.
4. **[CHECK 4] Anti-Tamper Verification:** 1¢ price inflation, payee changes and budget breaches are rejected by the AP2 verifier.
5. **[CHECK 5] Compute Node Provisioning:** Subscription verification and node endpoint allocation (`batch-01`, `gateway-01`, `cluster-01`). Endpoints are placeholders; nothing is provisioned (M-010).
6. **[CHECK 6] Back-Office ERP Payloads:** A QuickBooks Online v3 Purchase payload mapped to GL account 6300 (generated, not delivered).
7. **[CHECK 7] Fleet Telemetry Reconciliation:** 14 seeded demo subscriptions (13 active, 1 pending), \$1,219.87/mo MRR and \$14,638.44 ARR, reconciled to the cent.
8. **[CHECK 8] AG Studio & Bryntum Scheduling:** Loads the 14 seeded nodes from SQLite and checks the compute schedule.
9. **[CHECK 9] Buyer Key Onboarding:** A 300-second single-use challenge, a signed response, key enrollment, and rejection of a forged signature.

---

## 5. What's Simulated

Every stand-in for real behavior is declared in [`docs/MOCKS.md`](docs/MOCKS.md) (19 entries) and marked in the code with a `MOCK(M-NNN)` comment. `backend/tests/test_mocks_ledger.py` fails if the ledger and the markers disagree. Highlights: PayPal calls are simulated in mock mode, the fleet and schedule are seeded, back-office exports are dry runs without a webhook URL, and compute provisioning returns placeholder endpoints.

---

## 6. Technology Stack

- **Runtime & Build:** Node.js 22+ + Vite 8 + React 19 + TypeScript
- **Embedded Analytics:** AG Studio v3.0.0 (`ag-studio-react`, `ag-studio`) + AG Grid Community with floating filters
- **Payments:** PayPal Subscriptions (REST API), `@paypal/react-paypal-js`, PayPal Agent Toolkit (Python)
- **Workload Scheduling:** Bryntum Scheduler 7.3.7 (`@bryntum/scheduler` trial build)
- **API Specification:** OpenAPI 3.1.0 (`openapi.yaml` and `openapi.json`) + APIMatic SDK configuration (`apimatic.json`)
- **Backend Core:** FastAPI + Uvicorn + Python 3.13 + Pydantic v2
- **AP2:** Google's AP2 v0.2 SDK, vendored at commit `e1ea56db` with two documented fixes
- **Persistence:** SQLite in WAL mode (`a2a_commerce.db`) with a 5,000 ms busy timeout

---

## 7. License

Authored by Adam Murphy. See [`LICENSE`](LICENSE): all rights reserved while licensing terms are evaluated for the final release. The vendored AP2 SDK in `backend/vendor/ap2/` is Google's, under the Apache License 2.0.
