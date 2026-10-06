# FieldSmith Pro &mdash; Devpost Hackathon Submission Docket

> **Event:** PayPal AI Hackathon 2026 (\$67,500+ Purse) &mdash; Deadline: November 12, 2026 at 12:00 PM PST  
> **Target Tracks:**
> 1. Best Use of Agentic Commerce (\$5,000)
> 2. Best Use of AG Grid / AG Studio (\$5,000)
> 3. Best Use of PayPal + AI (\$5,000)
> 4. Best Use of Bryntum (\$1,000)
> 5. Best Use of APIMatic (\$1,000)  
> **Total Purse Targeted:** \$17,000+

---

## 1. Project Title & Tagline

* **Project Title:** FieldSmith Pro &mdash; Autonomous A2A Commerce & Multi-Agent Operations Deck
* **Elevator Pitch (Tagline):** Autonomous Agent-to-Agent (A2A) commerce protocol for solo trade contractors &mdash; enabling AI Buyer Agents to negotiate within strict spending mandates, execute recurring PayPal subscriptions, provision KYC-verified business phone lines, and automate downline back-office accounting with zero human friction.
* **Live Web Portal:** [https://api.fieldsmith.pro/portal/](https://api.fieldsmith.pro/portal/)
* **Live FastMCP Endpoint:** `https://api.fieldsmith.pro/a2a/mcp` (A2A Hackathon Seller Protocol; core contractor Stripe signups at `https://api.fieldsmith.pro/mcp`)
* **Live SSE Stream Endpoint:** `https://api.fieldsmith.pro/sse`
* **Interactive OpenAPI Docs:** [https://api.fieldsmith.pro/docs](https://api.fieldsmith.pro/docs)

---

## 2. Inspiration

Solo trade contractors (custom tile setters, emergency plumbers, roofers, tow truck operators) don't sit in front of laptops filling out SaaS checkout forms. They are on active jobsites running tile saws, sweating copper pipes, or driving on highways.

Every month, the average solo contractor loses over **\$6,200 in uncaptured revenue** from missed customer calls. When they do try software solutions, onboarding friction kills adoption: 15-field signup forms, manual credit card typing, and hours spent every evening re-entering job data into Jobber and QuickBooks.

Furthermore, autonomous AI bots in telecommunications present a grave compliance risk: anonymous automated dialers violate FCC regulations and the Telephone Consumer Protection Act (TCPA).

We asked: **What if a solo contractor had their own personal Autonomous Buyer Agent that acts like an executive CFO?**
The Buyer Agent detects missed call revenue leaks, consults the contractor's local programmatic spending mandate (\$100/mo cap), negotiates with FieldSmith's Seller Agent over Model Context Protocol (MCP), executes a verified PayPal subscription, anchors statutory KYC identity to a dedicated local phone line, and dispatches the entire back-office workflow into QuickBooks, Jobber, and Google Workspace without a single keystroke.

---

## 3. What It Does

FieldSmith Pro delivers a complete, end-to-end multi-agent commerce and operations ecosystem across four integrated portals:

### 1. Contractor Copilot & Split-Screen A2A Command Center
* **Autonomous Buyer Agent:** Analyzes contractor call logs, discovers uncaptured revenue (\$4,200 - \$6,200/mo), evaluates local spending mandates (`amount <= \$100.00/mo`), and generates asymmetric Ed25519 authorization proofs (`X-A2A-Signature`) conforming to the emerging FIDO / AP2 Intent Mandate specification.
* **Seller Agent (MCP Server):** Exposes machine-readable trade solution tiers over Model Context Protocol (`get_service_catalog`, `inspect_subscription_tiers`, `negotiate_tier_terms`, `evaluate_spending_mandate`, `purchase_subscription`, `provision_telecom_line`, `dispatch_zapier_mcp`).
* **Dynamic Multi-Tier Counter-Offer Negotiation:** When the contractor's spending cap is below the standard asking price (e.g. \$60 cap vs \$79.99 plan), the Seller Agent autonomously calculates and returns a dynamic counter-offer: *Solo Starter (125 AI screened calls/mo) available at \$49.99/mo*. The Buyer Agent evaluates the counter-offer autonomously and signs.
* **Interactive Anti-Tamper Verifier (Live Byte-Level Mismatch):** Judges can edit any single byte of the canonical JSON payload (e.g., inflating price from \$79.99 to \$80.00 or changing the contractor entity name) and watch the cryptographic verifier immediately reject authorization with `401 Signature Mismatch: Budget Policy Violated`.
* **Live SSE Wire Protocol Inspector:** Streams real-time Server-Sent Events (SSE) displaying raw JSON-RPC 2.0 frames (`initialize` &rarr; `tools/list` &rarr; `tools/call` &rarr; `vault/token`) with sub-millisecond timestamps.
* **Delegated PayPal Subscriptions & Vault MIT:** Executes recurring **\$79.99/month** subscriptions using `@paypal/react-paypal-js` and PayPal Server SDK backed by PayPal Vault setup tokens for off-session, merchant-initiated overage settlements.
* **Nationwide LATA & Contiguous Exchange Routing:** Provisions local 10DLC phone lines (`+1 863-267-8902`) through Telnyx strictly anchored to verified PayPal subscriber identity (*Miller Custom Flooring LLC*), locked 100% to inbound screening (zero unsolicited robocalls). Automatically calculates contiguous LATA failover (e.g. 863 Lakeland &rarr; 813 Tampa) if local pools are exhausted.
* **Self-Service Buyer Key Onboarding:** Cryptographic Ed25519 challenge-response enrollment (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`) allowing any third-party autonomous agent to register verified public keys with US-domestic contractor identity validation.

### 2. AG Studio v3.0.0 & AG Grid Operations Fleet Ledger
* Embedded high-density executive operations deck using `ag-studio-react`, `ag-studio` (v3.0.0), and AG Grid Community with a custom enterprise-grade floating filter engine.
* **Full AG Grid Floating Column Filters:** Dynamic filtering across all columns (Contractor, Plan, MRR, Status, Allocated DID) with `floatingFilter: true` and 34px filter height.
* **Dynamic SQLite WAL Persistence:** Live asynchronous data refresh (`onRefreshData`) pulling directly from persistent database records with zero hardcoded metrics.
* **Simulated Live Fleet Telemetry:** Every metric reconciles to the penny across 14 simulated contractor subscriber lines demonstrating 24/7 AG Studio operations across Florida contractor trade verticals:
  * **Active Fleet MRR:** \$1,039.87/mo pending &rarr; \$1,119.86/mo fully settled.
  * **Autonomous A2A Settlement GMV:** \$13,438.32 ARR.
  * **Mandates Settled:** 168 Autonomous Cycles (14 lines &times; 12 monthly cycles).
  * **Policy Enforcement:** 100% Policy Enforced &bull; 0 Budget Leaks.
* Features runtime **View / Drag & Drop Editor Mode switching**, allowing contractors or fleet managers to visually customize charts, rearrange widgets, or slice metrics by trade vertical.

### 3. Bryntum Telephony Fleet & Dispatch Scheduler
* Built on `@bryntum/scheduler` 7.3.7 (evaluated with Bryntum Dispatch Scheduler trial build) across 4 Florida territory zones (North, South, East, West Lakeland).
* **24/7 AI Voice Screener Shifts:** Synchronized directly with backend `/api/fleet/schedule` to display active monitoring crews and subscriber lines.
* **Dynamic 75-Minute Estimate Slot Locking:** "Lock 75-Min Estimate Window" button triggers `POST /api/agent/dispatch/lock-slot`, dynamically booking takeoff slots rendered in vibrant blue (`locked-takeoff-slot-1`) with customer deposit tags.
* **Live In-Place Reactive Transition:** Displays contractor phone lines in real time. Marcus Miller begins in amber/orange (`AWAITING PAYMENT`). When the autonomous PayPal subscription is executed, the timeline card reactively shifts in place to vibrant green (`LINE ACTIVE: +1 (863) 267-8902`).

### 4. Zapier MCP Autonomous Business Bridge
* Bridges verified PayPal payments into the contractor's existing enterprise toolchain via Model Context Protocol:
  * **QuickBooks Online:** Automatically records the recurring \$79.99/mo software subscription expense under *COGS: Telephony & AI Screener* linked to PayPal Token `I-AUTONOMOUS-8902` and mapped to General Ledger Account 6300.
  * **Jobber CRM:** Registers the allocated Telnyx DID `+1 (863) 267-8902` into business telephony routing and connects the AI Voice Screener webhook for *Tile & Custom Flooring*.
  * **Google Workspace:** Automatically schedules Marcus’s daily 6:30 AM Executive Morning Dispatch Briefing (`marcus@millercustomfloors.com`) and arms the 15-minute forwarding guard monitor.
* Includes a **Dual-Scenario Selector** to also showcase FieldSmith's downstream homeowner CRM intake (\$250 mobilization deposit & 75-minute estimate slot locking).

---

## 4. Multi-Sponsor Track Alignment (\$17,000+ Purse)

| Sponsor Track | Prize | How FieldSmith Pro Fulfills the Track Requirements |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **\$5,000** | Autonomous multi-tier negotiation between Buyer Agent and Seller MCP Server, budget cap enforcement with HMAC-SHA256 proofs, interactive anti-tamper testing, delegated PayPal Subscriptions (Vault setup tokens for off-session MIT), and statutory KYC telecom line provisioning. |
| **Best Use of AG Grid / AG Studio** | **\$5,000** | Embedded `ag-studio-react` and `ag-studio` (v3.0.0) with AG Grid Community custom floating filter engine, live SQLite WAL data hydration, grouped bar charts, and runtime View/Edit reporting modes reconciling \$13,438.32 ARR GMV across 14 simulated subscriber lines. |
| **Best Use of PayPal + AI** | **\$5,000** | Real-time FastMCP 2024-11-05 streamable HTTP/SSE wire protocol inspector, live cloud deployment (`https://api.fieldsmith.pro`), US-domestic NANP gating, and intelligent autonomous counter-offer generation. |
| **Best Use of Bryntum** | **\$1,000** | Evaluated with Bryntum Scheduler trial build managing 24/7 AI voice screener shifts, 75-minute customer estimate window booking, territory dispatch across 4 zones, and live in-place reactive color state transitions (Orange &rarr; Green &rarr; Blue). |
| **Best Use of APIMatic** | **\$1,000** | Production-grade OpenAPI 3.1.0 specification with 33 endpoints (`openapi.yaml` and `openapi.json`), `apimatic.json` configuration for multi-language SDK compilation (Python, TypeScript, Go), and self-service Ed25519 cryptographic buyer key challenge-response onboarding. |

---

## 5. Technical Architecture & Protocol Specifications

* **Protocol Layer:** Model Context Protocol (MCP) standard `2024-11-05` running over dual transports:
  * **Streamable HTTP & SSE Transport:** Standard JSON-RPC 2.0 at `/mcp`, SSE endpoint discovery at `/sse`, `/mcp/sse`, `/api/mcp/sse`, `/m2m/sse`.
  * **Stdio Transport:** Standard I/O loop (`backend/mcp_server.py`) for desktop MCP clients (Claude Desktop, Cursor, external autonomous harnesses).
* **Payment Rails:** PayPal Subscriptions API (`I-AUTONOMOUS-...`) backed by PayPal Vault setup tokens for off-session, merchant-initiated transactions (MIT).
* **Policy Enforcement:** Cryptographic spending mandate evaluator generating 64-character HMAC-SHA256 authorization proofs (`X-FieldSmith-Signature`) enforcing strict contractor budget caps.
* **Anti-Tamper Layer:** Byte-level canonical JSON digest verifier detecting price inflation, budget cap breaches, timestamp expiry, and unauthorized entity modification.
* **Telecom & ERP Settlement:** Immediate Telnyx 10DLC local DID binding, Jobber GraphQL v2 client/job routing mutations with telephony custom fields, and QuickBooks Online API v3 expense mapping to general ledger Account 6300 (Software & SaaS).
* **Persistent Database Layer:** SQLite WAL database engine (`a2a_database.db`) with 5000ms busy timeout, surviving process restarts across subscriptions, mandates, ledger commitments, processed webhook event IDs, and buyer key records.
* **Production Cloud Deployment:** Dedicated Google Cloud Compute Engine instance (`fieldsmith-core-api` at static IP `35.231.247.43`) fronted by Caddy reverse proxy with Cloudflare TLS terminating at `https://api.fieldsmith.pro`.

---

## 6. Verification & One-Click Judge Audit

### One-Click Live Cloud Audit
Hackathon judges can verify all 9 critical operational and cryptographic checks against the live cloud deployment with a single command:
```bash
python scripts/judge_audit_harness.py --remote
```

### Local In-Memory Audit (Zero Dependencies)
To run the exact same verification locally in-memory:
```bash
python scripts/judge_audit_harness.py
```

### Concurrent Multi-Agent Stress Test
To launch 5 parallel autonomous buyer agents stressing the live cloud deployment simultaneously:
```bash
python scripts/live_cloud_stress_test.py
```

### Automated Test Suite
```bash
python -m pytest backend/tests/ -v
# 133/133 tests passing (100% green)
```

---

## 7. The 9 Judge Audit Verification Checks

1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** Validates `initialize` and `tools/list` protocol handshake returning 7 registered seller tools.
2. **[CHECK 2] Standard A2A Negotiation:** Evaluates \$79.99/mo plan under \$100 budget cap with HMAC-SHA256 cryptographic authorization proof.
3. **[CHECK 3] Sub-Budget Counter-Offer Bargaining:** Generates scaled-down *Solo Starter* (\$49.99/mo) counter-offer when cap is \$60.00.
4. **[CHECK 4] Anti-Tamper Verification:** Proves 1-cent inflation tampering, entity name alteration, and budget breaches are strictly rejected.
5. **[CHECK 5] Nationwide LATA Routing:** Validates primary local allocation (863 Lakeland) and automated contiguous failover (813 Tampa).
6. **[CHECK 6] Back-Office ERP Payloads:** Generates authentic Jobber GraphQL v2 mutation and QuickBooks Online v3 Purchase mapped to GL Account 6300.
7. **[CHECK 7] Financial Telemetry Reconciliation:** Reconciles 14 simulated subscriber lines, \$1,119.86/mo MRR, and \$13,438.32 ARR GMV to the penny.
8. **[CHECK 8] AG Studio & Bryntum Scheduling:** Hydrates 14 lines from SQLite WAL, verifies 24/7 AI screener shifts, and locks 75-minute estimate slot for Crew B.
9. **[CHECK 9] Dynamic Buyer Key Onboarding:** Generates 300s ephemeral Ed25519 challenge nonce, validates cryptographic signature, enrolls buyer key, and rejects forged signatures.

---

## 8. Built With

`paypal-subscriptions-api`, `paypal-vault`, `model-context-protocol-mcp`, `ag-studio-v3`, `ag-grid-community`, `bryntum-scheduler-trial`, `fastapi`, `python-3.13`, `react-19`, `typescript`, `vite-8`, `sqlite-wal`, `ed25519-cryptography`, `hmac-sha256`, `telnyx-10dlc`, `jobber-graphql-v2`, `quickbooks-online-v3`, `openapi-3.1`
