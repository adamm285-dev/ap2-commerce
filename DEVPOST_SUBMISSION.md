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
* **Elevator Pitch (Tagline):** Autonomous Agentic Commerce & AP2 (Agent Payments Protocol) engine for distributed AI compute &mdash; enabling AI Buyer Agents to negotiate within strict spending mandates, execute recurring PayPal subscriptions, provision dedicated compute node endpoints, and automate downline back-office accounting with zero human friction.
* **Interactive Operations Deck:** `/portal/`
* **FastMCP Server Endpoint:** `/mcp` (Model Context Protocol JSON-RPC 2.0)
* **Live SSE Stream Endpoint:** `/sse` (Server-Sent Events)
* **Interactive OpenAPI Docs:** `/docs` (Swagger UI)

---

## 2. Inspiration

Autonomous software agents and developer teams hit severe compute capacity bottlenecks. Procuring dedicated worker nodes or specialized AI service gateways still suffers from critical failure modes:
1. **Human Onboarding Friction:** Autonomous agents cannot interact with 15-field checkout forms, manual credit card typing, or human verification captchas.
2. **Uncontrolled Budget Risk:** Enterprise spending mandates require mathematically enforceable, tamper-proof budget caps before an agent can commit company funds.
3. **Downline Integration Overhead:** Once an infrastructure subscription is active, manual entry is required to log accounting expenses into ERP systems (e.g. QuickBooks Online).
4. **Identity & Accountability:** Anonymous autonomous agents create counterparty risk unless commitments are cryptographically anchored to verified business entities.

We asked: **What if an engineering organization had an Autonomous Buyer Agent that acts like an executive procurement officer?**
The Buyer Agent detects compute queue backlogs, consults the local programmatic spending mandate ($100/mo cap), negotiates with the AP2 Seller Node over Model Context Protocol (MCP), executes a verified PayPal subscription, provisions dedicated compute node endpoints, and dispatches the entire back-office accounting workflow into QuickBooks Online and Google Workspace without a single keystroke.

---

## 3. What It Does

AP2 Autonomous Commerce delivers a complete, end-to-end multi-agent commerce and operations ecosystem across four integrated portals:

### 1. Autonomous Buyer Agent & Agentic Commerce Command Center
* **Autonomous Buyer Agent:** Analyzes workload task queues, evaluates local spending mandates (`amount <= $100.00/mo`), and generates asymmetric Ed25519 authorization proofs (`X-AP2-Signature`) conforming to the Google & PayPal AP2 Intent Mandate specification.
* **Seller Agent (MCP Server):** Exposes machine-readable compute tiers over Model Context Protocol (`get_service_catalog`, `inspect_subscription_tiers`, `negotiate_tier_terms`, `evaluate_spending_mandate`, `purchase_subscription`, `provision_compute_node`, `dispatch_zapier_mcp`, `get_subscription_details`).
* **Dynamic Multi-Tier Counter-Offer Negotiation:** When the buyer's spending cap is below the standard asking price (e.g. $60 cap vs $79.99 Dedicated Gateway), the Seller Agent autonomously calculates and returns a dynamic counter-offer: *High-Throughput Batch Worker (125 workload tasks/mo) available at $49.99/mo*. The Buyer Agent evaluates the counter-offer autonomously and signs.
* **Interactive Anti-Tamper Verifier (Live Byte-Level Mismatch):** Judges can edit any single byte of the canonical JSON payload (e.g., inflating price from $79.99 to $80.00 or changing the buyer identity) and watch the cryptographic verifier immediately reject authorization with `401 Signature Mismatch: Budget Policy Violated`.
* **Live SSE Wire Protocol Inspector:** Streams real-time Server-Sent Events (SSE) displaying raw JSON-RPC 2.0 frames (`initialize` &rarr; `tools/list` &rarr; `tools/call` &rarr; `vault/token`) with sub-millisecond timestamps.
* **Delegated PayPal Subscriptions & Vault MIT:** Executes recurring **$79.99/month** subscriptions using `@paypal/react-paypal-js` and PayPal Server SDK backed by PayPal Vault setup tokens for off-session, merchant-initiated overage settlements.
* **Dedicated Compute Node Provisioning:** Automatically provisions dedicated compute node endpoints (`batch-01`, `gateway-01`, `cluster-01`) anchored directly to verified PayPal subscriber identity with workload task quotas (125, 450, or 1,200 tasks/month).
* **Self-Service Buyer Key Onboarding:** Cryptographic Ed25519 challenge-response enrollment (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`) allowing any third-party autonomous agent to register verified public keys.

### 2. AG Studio v3.0.0 & AG Grid Operations Fleet Ledger
* Embedded high-density executive operations deck using `ag-studio-react`, `ag-studio` (v3.0.0), and AG Grid Community with floating filters.
* **Full AG Grid Floating Column Filters:** Dynamic filtering across all columns (Subscriber, Plan, MRR, Status, Node Endpoint) with `floatingFilter: true` and 34px filter height.
* **Dynamic SQLite WAL Persistence:** Live asynchronous data refresh (`onRefreshData`) pulling directly from persistent database records with zero hardcoded metrics.
* **Simulated Live Fleet Telemetry:** Every metric reconciles to the penny across 14 simulated compute nodes:
  * **Active Fleet MRR:** $1,039.87/mo pending &rarr; $1,119.86/mo fully settled.
  * **Autonomous Agentic Commerce Settlement GMV:** $13,438.32 ARR.
  * **Mandates Settled:** 168 Autonomous Cycles (14 nodes &times; 12 monthly cycles).
  * **Policy Enforcement:** 100% Policy Enforced &bull; 0 Budget Leaks.
* Features runtime **View / Drag & Drop Editor Mode switching**, allowing fleet managers to visually customize charts, rearrange widgets, or slice metrics by compute workload.

### 3. Bryntum Workload Fleet & Dispatch Scheduler
* Built on `@bryntum/scheduler` 7.3.7 (evaluated with Bryntum Dispatch Scheduler trial build) across regional workload zones.
* **24/7 Compute Execution Shifts:** Synchronized directly with backend `/api/fleet/schedule` to display active monitoring shifts and allocated compute nodes.
* **Live In-Place Reactive Transition:** Displays subscriber node allocation in real time. A new node begins in amber/orange (`AWAITING PAYMENT`). When the autonomous PayPal subscription is executed, the timeline card reactively shifts in place to vibrant green (`NODE ACTIVE: gateway-01.ap2.net:8443`).

### 4. Zapier MCP Autonomous Business Bridge
* Bridges verified PayPal payments into enterprise accounting and monitoring via Model Context Protocol:
  * **QuickBooks Online:** Automatically records the recurring software subscription expense under *COGS: AI Infrastructure & Worker Nodes* linked to PayPal Token `I-A2A-VAULT-...` and mapped to General Ledger Account 6300.
  * **Operational Routing:** Registers the allocated node endpoint into operational monitoring.
  * **Google Workspace:** Automatically schedules the morning node health audit on Google Calendar.

---

## 4. Multi-Sponsor Track Alignment ($18,000+ Purse)

| Sponsor Track | Prize | How AP2 Autonomous Commerce Fulfills the Track Requirements |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **$5,000** | Autonomous multi-tier negotiation between Buyer Agent and Seller MCP Server, budget cap enforcement with HMAC-SHA256 proofs, interactive anti-tamper testing, delegated PayPal Subscriptions (Vault setup tokens for off-session MIT), and compute node provisioning. |
| **Best Use of AG Grid / AG Studio** | **$5,000** | Embedded `ag-studio-react` and `ag-studio` (v3.0.0) with AG Grid Community with floating filters, live SQLite WAL data hydration, grouped bar charts, and runtime View/Edit reporting modes reconciling $13,438.32 ARR GMV across 14 simulated compute nodes. |
| **Best Use of PayPal + AI** | **$5,000** | Real-time FastMCP 2024-11-05 streamable HTTP/SSE wire protocol inspector, autonomous multi-turn negotiation, and intelligent autonomous counter-offer generation. |
| **Best Use of Bryntum** | **$1,000** | Evaluated with Bryntum Scheduler trial build managing 24/7 compute node execution shifts, workload timeline visualization, and live in-place reactive color state transitions (Orange &rarr; Green). |
| **Best Use of Zapier** | **$1,000** | Autonomous Model Context Protocol bridge (`dispatch_zapier_mcp` tool) executing QBO v3 (GL 6300 SaaS expense), operational monitoring routing, and SSRF-safe HMAC-SHA256 signed webhook envelopes. |
| **Best Use of APIMatic** | **$1,000** | Production-grade OpenAPI 3.1.0 specification with 33 endpoints (`openapi.yaml` and `openapi.json`), `apimatic.json` configuration for multi-language SDK compilation (Python, TypeScript, Go), and self-service Ed25519 cryptographic buyer key challenge-response onboarding. |

---

## 5. Technical Architecture & Protocol Specifications

* **Protocol Layer:** Model Context Protocol (MCP) standard `2024-11-05` running over dual transports:
  * **Streamable HTTP & SSE Transport:** Standard JSON-RPC 2.0 at `/mcp`, SSE endpoint discovery at `/sse`.
  * **Stdio Transport:** Standard I/O loop (`backend/mcp_server.py`) for desktop MCP clients (Claude Desktop, Cursor, external autonomous harnesses).
* **Payment Rails:** PayPal Subscriptions API (`I-A2A-VAULT-...`) backed by PayPal Vault setup tokens for off-session, merchant-initiated transactions (MIT).
* **Policy Enforcement:** Cryptographic spending mandate evaluator generating 64-character HMAC-SHA256 authorization proofs (`X-AP2-Signature`) enforcing strict budget caps.
* **Anti-Tamper Layer:** Byte-level canonical JSON digest verifier detecting price inflation, budget cap breaches, timestamp expiry, and unauthorized entity modification.
* **ERP Settlement:** Immediate QuickBooks Online API v3 expense mapping to general ledger Account 6300 (Software & SaaS).
* **Persistent Database Layer:** SQLite WAL database engine (`ap2_commerce.db`) with 5000ms busy timeout, surviving process restarts across subscriptions, mandates, ledger commitments, processed webhook event IDs, and buyer key records.

---

## 6. Verification & One-Click Judge Audit

### One-Click In-Memory Audit (Zero Dependencies)
Hackathon judges can verify all 9 critical operational and cryptographic checks with a single command:
```bash
python scripts/judge_audit_harness.py
# 9/9 checks passed (100% green)
```

### Automated Test Suite
```bash
pytest backend/tests/ -q -n 4
# 227 passed, 6 skipped (100% green)
```

---

## 7. The 9 Judge Audit Verification Checks

1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** Validates `initialize` and `tools/list` protocol handshake returning 8 registered seller tools.
2. **[CHECK 2] Standard AP2 Negotiation:** Evaluates $79.99/mo Service Gateway under $100 budget cap with HMAC-SHA256 cryptographic authorization proof.
3. **[CHECK 3] Sub-Budget Counter-Offer Bargaining:** Generates scaled-down *Batch Worker* ($49.99/mo) counter-offer when cap is $60.00.
4. **[CHECK 4] Anti-Tamper Verification:** Proves 1-cent inflation tampering, entity name alteration, and budget breaches are strictly rejected.
5. **[CHECK 5] Compute Node Provisioning:** Validates subscription verification and compute node endpoint allocation (`batch-01`, `gateway-01`, `cluster-01`).
6. **[CHECK 6] Back-Office ERP Payloads:** Generates authentic QuickBooks Online v3 Purchase mapped to GL Account 6300.
7. **[CHECK 7] Financial Telemetry Reconciliation:** Reconciles 14 simulated subscriber nodes, $1,119.86/mo MRR, and $13,438.32 ARR GMV to the penny.
8. **[CHECK 8] AG Studio & Bryntum Scheduling:** Hydrates 14 nodes from SQLite WAL and verifies 24/7 compute execution shifts.
9. **[CHECK 9] Dynamic Buyer Key Onboarding:** Generates 300s ephemeral Ed25519 challenge nonce, validates cryptographic signature, enrolls buyer key, and rejects forged signatures.

---

## 8. Built With

`paypal-subscriptions-api`, `paypal-vault`, `model-context-protocol-mcp`, `zapier-mcp`, `ag-studio-v3`, `ag-grid-community`, `bryntum-scheduler-trial`, `fastapi`, `python-3.13`, `react-19`, `typescript`, `vite-8`, `sqlite-wal`, `ed25519-cryptography`, `hmac-sha256`, `quickbooks-online-v3`, `openapi-3.1`
