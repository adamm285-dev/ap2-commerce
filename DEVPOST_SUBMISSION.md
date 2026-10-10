# AP2 Autonomous Commerce &mdash; Devpost Hackathon Submission Docket

> **Event:** PayPal AI Hackathon 2026 (\$67,500+ Purse)  
> **Target Tracks:**
> 1. Best Use of Agentic Commerce ($5,000)
> 2. Best Use of AG Grid / AG Studio ($5,000)
> 3. Best Use of PayPal + AI ($5,000)
> 4. Best Use of Bryntum ($1,000)
> 5. Best Use of Zapier ($1,000)
> 6. Best Use of APIMatic ($1,000)
> **Total Purse Targeted:** $18,000+

---

## 1. Project Title & Tagline

* **Project Title:** AP2 Autonomous Commerce &mdash; Agent Payments Protocol Operations Deck
* **Elevator Pitch (Tagline):** Built on Google's AP2 (Agent Payments Protocol) v0.2, actively prototyping what its official roadmap says comes next: recurring subscriptions, Human-Not-Present (HNP) autonomous purchases, Untrusted Courier MCP isolation, and dynamic agent-to-agent counter-offer negotiation for distributed AI compute.
* **Interactive Operations Deck:** `/portal/`
* **FastMCP Server Endpoint:** `/mcp` (Model Context Protocol JSON-RPC 2.0)
* **Untrusted Courier Buyer Wallet:** Stdio / JSON-RPC 2.0 (`backend.wallet.mcp_server`)
* **Live SSE Stream Endpoint:** `/sse` (Server-Sent Events)
* **Interactive OpenAPI Docs:** `/docs` (Swagger UI)

---

## 2. Inspiration & The AP2 V1 Roadmap

Google published the **AP2 (Agent Payments Protocol) v0.2** specification to define cryptographic Selective Disclosure JWT (SD-JWT) standards for agentic transactions. However, AP2 v0.2 targets single, human-present checkouts. On its public roadmap, AP2 highlights four major open problems for V1.x:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 AP2 AUTONOMOUS COMMERCE INNOVATION MATRIX                   │
├─────────────────────────┬─────────────────────────┬─────────────────────────┤
│ AP2 V1.x Roadmap Item   │ Official AP2 Status     │ AP2 Autonomous Commerce │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ 1. Recurring Payments   │ Open design question    │ Implemented via PayPal  │
│    & Subscriptions      │ on public roadmap       │ Vault MIT & Webhooks    │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ 2. Human-Not-Present    │ Stated milestone for    │ Fully autonomous buyer  │
│    (HNP) Purchases      │ post-v0.2 releases      │ agent under signed caps │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ 3. MCP Client / Wallet  │ Identified as ecosystem │ Two-process FastMCP     │
│    Isolation            │ requirement             │ architecture (Untrusted)│
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ 4. Dynamic Negotiation  │ Stated long-term vision │ Multi-tier fallback     │
│    & Counter-Offers     │ on roadmap              │ bargaining engine       │
└─────────────────────────┴─────────────────────────┴─────────────────────────┘
```

When procuring AI cloud compute, engineering organizations encounter severe bottlenecks:
1. **The Untrusted Courier Threat:** Giving an LLM direct access to corporate private signing keys exposes treasury funds to prompt injection and context leakage.
2. **The Recurring Billing Blindspot:** AP2 v0.2 has no protocol for recurring subscriptions; renewal webhooks arrive after money has moved, creating severe budget leak risk.
3. **Rigid Catalog Failures:** If an autonomous buyer's spending cap is slightly below standard pricing, transactions abort rather than negotiating an agreeable sub-budget tier.
4. **Disconnected Downline Accounting:** Once compute is provisioned, human finance teams are bogged down manually recording recurring SaaS expenses into ERPs (e.g. QuickBooks Online).

---

## 3. What It Does

AP2 Autonomous Commerce delivers an end-to-end multi-agent commerce and operations ecosystem:

### 1. Untrusted Courier Architecture (Two-Process MCP Model)
* **Threat Model Mitigation:** Private keys are isolated entirely outside the LLM context. In Claude Desktop, Claude operates strictly as an **Untrusted Courier** running between the local **Buyer Wallet MCP Server** (`backend.wallet.mcp_server`) and the **Seller Node MCP Server** (`backend.mcp_server`).
* **Deterministic Limits Enforcement:** The local wallet holds the agent's key and owner-signed spending limits—never the owner's private key. The wallet independently parses the merchant's signature on `checkout_jwt`. If an injection or hallucination attempts to purchase an unauthorized or over-budget tier, the wallet raises a hard `WalletRefusal` before any signature is generated.

### 2. Month-2 Renewal Verification & Advance Cancellation Engine
* **AP2-Enforced Recurring Billing:** Built in `backend/services/recurring_mandate_service.py`. On each PayPal `PAYMENT.SALE.COMPLETED` webhook, the engine re-verifies the stored owner mandate signature using Google's AP2 SDK, checking expiration, budget caps, cycle count limits (12 monthly payments), and agreed unit price.
* **Advance Cancellation:** Because webhooks report charges that already occurred, the engine evaluates the *next* billing cycle in advance. If the upcoming charge would breach authorization, it triggers immediate advance cancellation on PayPal before unauthorized funds can move.
* **Decoupled Authorization Windows:** The owner's initial authorization grants a 24-hour window to complete checkout, while the recurring payment authority extends for 372 days.

### 3. Dynamic Multi-Tier Counter-Offer Negotiation
* When the buyer agent's spending cap is below standard pricing ($60 cap vs $79.99 Dedicated Gateway), the Seller Agent autonomously calculates and returns a dynamic counter-offer: *High-Throughput Batch Worker (125 workload tasks/mo) available at $49.99/mo*. The Buyer Agent evaluates the counter-offer autonomously and signs.

### 4. Interactive Cryptographic Anti-Tamper Engine
* Evaluates ES256 SD-JWT and Ed25519 mandate chains. Altering even 1¢ ($79.99 &rarr; $80.00) or modifying payee identity immediately triggers `invalid_mandate` with dual-signed cryptographic error receipts.

### 5. AG Studio v3.0.0 & AG Grid Operations Fleet Ledger
* High-density executive operations deck using `ag-studio-react`, `ag-studio` (v3.0.0), and AG Grid Community with floating column filters.
* Live SQLite WAL data hydration reconciling **$14,638.44 annualized ARR** ($1,219.87 MRR across 13 active nodes, 14 total provisioned).
* Interactive View / Drag & Drop Editor modes for fleet managers.

### 6. Bryntum Workload Fleet & Dispatch Scheduler
* Evaluated with Bryntum Dispatch Scheduler trial build across regional workload zones.
* Manages 24/7 compute execution shifts with live in-place reactive color state transitions (Orange `AWAITING PAYMENT` &rarr; Green `NODE ACTIVE`).

### 7. Zapier MCP Autonomous Business Bridge
* Automatically records recurring subscription expenses in QuickBooks Online mapped to General Ledger Account 6300 (Software & SaaS) linked to PayPal Vault tokens and schedules health audits in Google Calendar.

---

## 4. Executive Slide Deck Summary (8-Slide Architecture)

| Slide | Title | Core Technical Innovation | Verified Code Anchor |
| :---: | :--- | :--- | :--- |
| **01** | **AP2 v0.2 Baseline & V1 Roadmap** | Working Google AP2 v0.2 implementation prototyping 4 public roadmap items | `backend/vendor/ap2/`, `backend/tests/conformance/` |
| **02** | **The Untrusted Courier Threat** | Threat model proving why LLMs must never possess private cryptographic signing keys | `backend/wallet/wallet.py`, `backend/tests/test_buyer_wallet.py` |
| **03** | **Two-Process MCP Architecture** | Buyer Wallet holds agent key and owner limits (never owner's private key); courier blocked on overspend | `backend/wallet/mcp_server.py`, `scripts/setup_claude_desktop_demo.py` |
| **04** | **Recurring Billing & Renewal Enforcement** | PayPal webhook re-verification + advance cancellation before unauthorized charges occur | `backend/services/recurring_mandate_service.py`, `backend/server.py` |
| **05** | **Dynamic Bargaining & Anti-Tamper** | Autonomous counter-offers ($49.99 Batch Worker) + 1¢ inflation rejection under real AP2 ES256 verifier | `backend/services/ap2_service.py`, `backend/wallet/wallet.py` |
| **06** | **Simulated Fleet Operations** | AG Studio v3.0.0 (`EnterpriseFleetLedger.tsx`) + Bryntum Scheduler + Zapier QBO GL 6300 export | `src/components/EnterpriseFleetLedger.tsx`, `backend/services/backoffice/qbo_exporter.py` |
| **07** | **The Production Gap Report** | Candid 4-pillar gap analysis: Hardware passkeys, shared state, revocation checks, and rail convergence | `backend/services/ap2_keys.py`, `backend/server.py` |
| **08** | **Empirical Verification** | 557 passing tests (188 SDK + 369 project), 9/9 zero-dependency judge checks in <0.2s | `pytest backend/tests/ -q -n 4`, `scripts/judge_audit_harness.py` |

---

## 5. Multi-Sponsor Track Alignment ($18,000+ Purse)

| Sponsor Track | Prize | How AP2 Autonomous Commerce Fulfills the Track Requirements |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **$5,000** | Autonomous multi-tier negotiation between Buyer Agent and Seller MCP Server, budget cap enforcement with HMAC-SHA256 proofs, interactive anti-tamper testing, delegated PayPal Subscriptions (Vault setup tokens for off-session MIT), and compute node provisioning. |
| **Best Use of AG Grid / AG Studio** | **$5,000** | Embedded `ag-studio-react` and `ag-studio` (v3.0.0) with AG Grid Community floating filters, live SQLite WAL data hydration, grouped bar charts, and runtime View/Edit reporting modes reconciling $14,638.44 ARR GMV across 13 active nodes (14 total). |
| **Best Use of PayPal + AI** | **$5,000** | Real-time FastMCP 2024-11-05 streamable HTTP/SSE wire protocol inspector, autonomous multi-turn negotiation, and intelligent autonomous counter-offer generation. |
| **Best Use of Bryntum** | **$1,000** | Evaluated with Bryntum Scheduler trial build managing 24/7 compute node execution shifts, workload timeline visualization, and live in-place reactive color state transitions (Orange &rarr; Green). |
| **Best Use of Zapier** | **$1,000** | Autonomous Model Context Protocol bridge (`dispatch_zapier_mcp` tool) executing QBO v3 (GL 6300 SaaS expense), operational monitoring routing, and SSRF-safe HMAC-SHA256 signed webhook envelopes. |
| **Best Use of APIMatic** | **$1,000** | Production-grade OpenAPI 3.1.0 specification with 33 endpoints (`openapi.yaml` and `openapi.json`), `apimatic.json` configuration for multi-language SDK compilation (Python, TypeScript, Go), and self-service Ed25519 cryptographic buyer key challenge-response onboarding. |

---

## 6. Verification & One-Click Judge Audit

### One-Click In-Memory Audit (Zero Dependencies)
Hackathon judges can verify all 9 critical operational and cryptographic checks with a single command in <0.2 seconds:
```bash
python scripts/judge_audit_harness.py
# 9/9 checks passed (100% green)
```

### Automated Test Suite
```bash
pytest backend/tests/ -q -n 4
# 557 passed, 9 skipped (100% green; 188 Google SDK tests + 369 project tests)
```

### Checkable Mocks Gate (SDCS Gate L)
```bash
python scripts/check_mocks.py
# docs/MOCKS.md matches the MOCK markers in the code (19 mocks verified)
```

---

## 7. The 9 Judge Audit Verification Checks

1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** Validates `initialize` and `tools/list` protocol handshake returning 8 registered seller tools.
2. **[CHECK 2] Standard AP2 Negotiation:** Evaluates $79.99/mo Service Gateway under $100 budget cap with ES256 SD-JWT cryptographic authorization proof.
3. **[CHECK 3] Sub-Budget Counter-Offer Bargaining:** Generates scaled-down *Batch Worker* ($49.99/mo) counter-offer when cap is $60.00.
4. **[CHECK 4] Anti-Tamper Verification:** Proves 1-cent inflation tampering, entity name alteration, and budget breaches are strictly rejected under Google's AP2 verifier.
5. **[CHECK 5] Compute Node Provisioning:** Validates subscription verification and compute node endpoint allocation (`batch-01`, `gateway-01`, `cluster-01`).
6. **[CHECK 6] Back-Office ERP Payloads:** Generates authentic QuickBooks Online v3 Purchase mapped to GL Account 6300.
7. **[CHECK 7] Financial Telemetry Reconciliation:** Reconciles 14 subscriber nodes (13 active, 1 pending), $1,219.87/mo MRR, and $14,638.44 ARR GMV to the penny.
8. **[CHECK 8] AG Studio & Bryntum Scheduling:** Hydrates 14 nodes from SQLite WAL and verifies 24/7 compute execution shifts.
9. **[CHECK 9] Dynamic Buyer Key Onboarding:** Generates 300s ephemeral Ed25519 challenge nonce, validates cryptographic signature, enrolls buyer key, and rejects forged signatures.

---

## 8. Built With

`paypal-subscriptions-api`, `paypal-vault`, `google-ap2-sdk`, `model-context-protocol-mcp`, `zapier-mcp`, `ag-studio-v3`, `ag-grid-community`, `bryntum-scheduler-trial`, `fastapi`, `python-3.13`, `react-19`, `typescript`, `vite-8`, `sqlite-wal`, `es256-sd-jwt`, `ed25519-cryptography`, `quickbooks-online-v3`, `openapi-3.1`
