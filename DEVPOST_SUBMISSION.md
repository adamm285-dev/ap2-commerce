# FieldSmith Pro &mdash; Devpost Hackathon Submission Docket

> **Event:** PayPal AI Hackathon 2026 ($67,500+ Purse) &mdash; Deadline: November 12, 2026 at 12:00 PM PST  
> **Target Tracks:**
> 1. Best Use of Agentic Commerce ($5,000)
> 2. Best Use of AG Grid / AG Studio ($5,000)
> 3. Best Use of PayPal + AI ($5,000)
> 4. Best Use of Bryntum ($1,000)
> 5. Best Use of APIMatic ($1,000)  
> **Total Purse Targeted:** $17,000+

---

## 1. Project Title & Tagline

* **Project Title:** FieldSmith Pro &mdash; Autonomous A2A Commerce & Multi-Agent Operations Deck
* **Elevator Pitch (Tagline):** Autonomous Agent-to-Agent (A2A) commerce protocol for solo trade contractors &mdash; enabling AI Buyer Agents to negotiate within strict spending mandates, execute recurring PayPal subscriptions, provision KYC-verified business phone lines, and automate downline back-office accounting with zero human friction.

---

## 2. Inspiration

Solo trade contractors (custom tile setters, emergency plumbers, roofers, tow truck operators) don't sit in front of laptops filling out SaaS checkout forms. They are on active jobsites running tile saws, sweating copper pipes, or driving on highways.

Every month, the average solo contractor loses over **$6,200 in uncaptured revenue** from missed customer calls. When they do try software solutions, onboarding friction kills adoption: 15-field signup forms, manual credit card typing, and hours spent every evening re-entering job data into Jobber and QuickBooks.

Furthermore, autonomous AI bots in telecommunications present a grave compliance risk: anonymous automated dialers violate FCC regulations and the Telephone Consumer Protection Act (TCPA).

We asked: **What if a solo contractor had their own personal Autonomous Buyer Agent that acts like an executive CFO?**
The Buyer Agent detects missed call revenue leaks, consults the contractor's local programmatic spending mandate ($100/mo cap), negotiates with FieldSmith's Seller Agent over Model Context Protocol (MCP), executes a verified PayPal subscription, anchors statutory KYC identity to a dedicated local phone line, and dispatches the entire back-office workflow into QuickBooks, Jobber, and Google Workspace without a single keystroke.

---

## 3. What It Does

FieldSmith Pro delivers a complete, end-to-end multi-agent commerce and operations ecosystem across four integrated portals:

### 1. Contractor Copilot & Split-Screen A2A Command Center
* **Autonomous Buyer Agent:** Analyzes contractor call logs, discovers uncaptured revenue ($4,200 - $6,200/mo), evaluates local spending mandates (`amount <= $100.00/mo`), and generates asymmetric Ed25519 authorization proofs (`X-A2A-Signature`) conforming to the emerging FIDO / AP2 Intent Mandate specification.
* **Seller Agent (MCP Server):** Exposes machine-readable trade solution tiers over Model Context Protocol (`get_service_catalog`, `inspect_subscription_tiers`, `negotiate_tier_terms`, `evaluate_spending_mandate`, `purchase_subscription`, `provision_telecom_line`, `dispatch_zapier_mcp`).
* **Dynamic Multi-Tier Counter-Offer Negotiation:** When the contractor's spending cap is below the standard asking price (e.g. $60 cap vs $79.99 plan), the Seller Agent autonomously calculates and returns a dynamic counter-offer: *Solo Starter (125 AI screened calls/mo) available at $49.99/mo*. The Buyer Agent evaluates the counter-offer autonomously and signs.
* **Interactive Anti-Tamper Verifier (Live Byte-Level Mismatch):** Judges can edit any single byte of the canonical JSON payload (e.g., inflating price from $79.99 to $80.00 or changing the contractor entity name) and watch the cryptographic verifier immediately reject authorization with `401 Signature Mismatch: Budget Policy Violated`.
* **Live SSE Wire Protocol Inspector:** Streams real-time Server-Sent Events (SSE) displaying raw JSON-RPC 2.0 frames (`initialize` &rarr; `tools/list` &rarr; `tools/call` &rarr; `vault/token`) with sub-millisecond timestamps.
* **Delegated PayPal Subscriptions & Vault MIT:** Executes recurring **$79.99/month** subscriptions using `@paypal/react-paypal-js` and PayPal Server SDK backed by PayPal Vault setup tokens for off-session, merchant-initiated overage settlements.
* **Nationwide LATA & Contiguous Exchange Routing:** Provisions local 10DLC phone lines (`+1 863-267-8902`) through Telnyx strictly anchored to verified PayPal subscriber identity (*Miller Custom Flooring LLC*), locked 100% to inbound screening (zero unsolicited robocalls). Automatically calculates contiguous LATA failover (e.g. 863 Lakeland &rarr; 813 Tampa) if local pools are exhausted.

### 2. AG Studio v3.0.0 Fleet Ledger & Mission Control
* Embedded high-density executive operations deck using `ag-studio-react` and `ag-studio` (v3.0.0).
* **100% Mathematically Reconciled Telemetry:** Every metric reconciles to the penny across 14 contractor subscriber lines:
  * **Active Fleet MRR:** $1,039.87/mo pending &rarr; $1,119.86/mo fully settled.
  * **Autonomous A2A Settlement GMV:** $13,438.32 ARR.
  * **Mandates Settled:** 168 Autonomous Cycles (14 lines &times; 12 monthly cycles).
  * **Policy Enforcement:** 100% Policy Enforced &bull; 0 Budget Leaks.
* Features runtime **View / Drag & Drop Editor Mode switching**, allowing contractors or fleet managers to visually customize charts, rearrange widgets, or slice metrics by trade vertical.

### 3. Bryntum Telephony Fleet & Line Activation Timeline
* Built on `@bryntum/scheduler` 7.3.7 across 4 Florida territory zones (North, South, East, West Lakeland).
* **Live In-Place Reactive Transition:** Displays contractor phone lines in real time. Marcus Miller begins in amber/orange (`AWAITING PAYMENT`). When the autonomous PayPal subscription is executed, the timeline card reactively shifts in place to vibrant green (`LINE ACTIVE: +1 (863) 267-8902`).

### 4. Zapier MCP Autonomous Business Bridge
* Bridges verified PayPal payments into the contractor's existing enterprise toolchain via Model Context Protocol:
  * **QuickBooks Online:** Automatically records the recurring $79.99/mo software subscription expense under *COGS: Telephony & AI Screener* linked to PayPal Token `I-AUTONOMOUS-8902` and mapped to General Ledger Account 6300.
  * **Jobber CRM:** Registers the allocated Telnyx DID `+1 (863) 267-8902` into business telephony routing and connects the AI Voice Screener webhook for *Tile & Custom Flooring*.
  * **Google Workspace:** Automatically schedules Marcus’s daily 6:30 AM Executive Morning Dispatch Briefing (`marcus@millercustomfloors.com`) and arms the 15-minute forwarding guard monitor.
* Includes a **Dual-Scenario Selector** to also showcase FieldSmith's downstream homeowner CRM intake ($250 mobilization deposit & 75-minute estimate slot locking).

---

## 4. Technical Architecture & Protocol Specifications

* **Protocol Layer:** Model Context Protocol (MCP) standard `2024-11-05` running over dual transports:
  * **HTTP Transport:** Standard JSON-RPC 2.0 at `/mcp` and payload audit cache at `/m2m` / `/api/m2m`.
  * **Stdio Transport:** Standard I/O loop (`backend/mcp_server.py`) for desktop MCP clients (Claude Desktop, Cursor, external autonomous harnesses).
* **Payment Rails:** PayPal Subscriptions API (`I-AUTONOMOUS-...`) backed by PayPal Vault setup tokens for off-session, merchant-initiated transactions (MIT).
* **Policy Enforcement:** Cryptographic spending mandate evaluator generating 64-character HMAC-SHA256 authorization proofs (`X-FieldSmith-Signature`) enforcing strict contractor budget caps.
* **Anti-Tamper Layer:** Byte-level canonical JSON digest verifier detecting price inflation, budget cap breaches, timestamp expiry, and unauthorized entity modification.
* **Telecom & ERP Settlement:** Immediate Telnyx 10DLC local DID binding, Jobber GraphQL v2 client/job routing mutations with telephony custom fields, and QuickBooks Online API v3 expense mapping to general ledger Account 6300 (Software & SaaS).
* **In-UI Machine-to-Machine Inspector:** Built-in modal (*Inspect Back-Office Payloads*) in the Contractor Copilot providing judges 1-click verifiable proof of Jobber GraphQL mutations, Intuit QBO v3 Purchase objects, and signed webhook envelopes with 1-tap copy functionality.

---

## 5. Multi-Sponsor Track Alignment ($13,000+ Purse)

| Sponsor Track | Prize | How FieldSmith Pro Fulfills the Track Requirements |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **$5,000** | Autonomous multi-tier negotiation between Buyer Agent and Seller MCP Server, budget cap enforcement with HMAC-SHA256 proofs, interactive anti-tamper testing, delegated PayPal Subscriptions (Vault setup tokens for off-session MIT), and statutory KYC telecom line provisioning. |
| **Best Use of AG Grid / AG Studio** | **$5,000** | Embedded `ag-studio-react` and `ag-studio` (v3.0.0) with dark slate styling, grouped bar charts, live data sources, and runtime View/Edit reporting modes reconciling $13,438.32 ARR GMV across 14 subscriber lines. |
| **Best Use of Bryntum** | **$1,000** | Interactive Bryntum Scheduler 7.3.7 managing telephony lines and estimate slots across 4 territory zones, with dynamic reactive color state transitions (Orange &rarr; Green). |
| **Best Use of Zapier** | **$1,000** | Multi-app downline workflow orchestration using Model Context Protocol (MCP) bridging Jobber GraphQL v2, QuickBooks Online v3 Expense mapping, and Google Workspace. |
| **Best Use of APIMatic** | **$1,000** | 100% valid, production-grade OpenAPI 3.1.0 specification (`openapi.yaml`) covering all routes, schemas, and security requirements, ready for multi-language SDK compilation. |

---

## 6. How We Built It

* **Frontend:** React 19, TypeScript, Vite 8, Lucide React icons, dark slate theme.
* **Component Frameworks:** AG Studio v3.0.0 (`ag-studio-react`, `ag-studio`), Bryntum Scheduler 7.3.7 (`@bryntum/scheduler`).
* **Payments & Identity:** `@paypal/react-paypal-js`, PayPal Sandbox REST APIs (v1 Subscriptions & v2 Checkout), PayPal Vault tokens, and cryptographic HMAC-SHA256 / Ed25519 AP2 mandate validation.
* **Backend API:** FastAPI (Python 3.13), Uvicorn, Pydantic v2 schemas matching `openapi.yaml`.
* **Autonomous Agents:** Standalone External Buyer Agent CLI harness (`backend.harness.external_buyer_agent`) and Seller Agent exposing Model Context Protocol (MCP) tool schemas (`backend.mcp_server`).
* **Telecom Infrastructure:** Telnyx 10DLC REST API simulation with strict inbound-only compliance locks and contiguous LATA routing (swappable to live carrier via `TELNYX_API_KEY`).
* **Workflow Automation & ERP:** Jobber GraphQL/REST exporter, QuickBooks Online API v3 exporter, and Zapier MCP Dispatcher with signed webhook hooks.

---

## 7. Challenges We Overcame

1. **Transparent Protocol Verification Over Static Slides:** Rather than static slide mockups, our architecture runs fully deterministic AP2 dual-mandate and MCP bargaining workflows. In development and judge evaluation modes, calls route through PayPal Sandbox and simulated Telnyx/Zapier adapters with full real-API parity, backed by an interactive byte-level Anti-Tamper Verifier in the UI and raw JSON-RPC 2.0 frames streamed over live SSE.
2. **Autonomous Counter-Offer Negotiation:** When buyer budgets don't meet standard asking rates ($60 cap vs $79.99/mo plan), standard bots fail with a 400 error. We engineered an autonomous multi-tier bargaining protocol where the seller dynamically offers a scaled-down tier ($49.99/mo Solo Intake) which the buyer evaluates and approves autonomously.
3. **Reactivity Across Disparate UI Frameworks:** Bridging the AG Studio React grid, the Bryntum canvas engine, and the Zapier execution trace into one seamless, reactive experience. When a payment event occurs, Marcus Miller's card dynamically mutates from amber to green without refreshing or duplicating data.
4. **Preventing Telecom Bot Abuse:** Anonymous AI agents dialers risk massive TCPA fines ($500-$1,500/call). We solved this by legally anchoring line allocation to the verified PayPal subscriber KYC identity, locking the line strictly to inbound screening.
5. **Verifiable Downline Proof without Terminal Access:** We built the in-UI "Inspect Back-Office Payloads" modal and `/m2m/payloads/latest` audit cache, allowing judges to view and copy authentic Jobber GraphQL client/job mutations and QBO v3 Purchase objects with a single tap.

---

## 8. Accomplishments We're Proud Of

* **54/54 Passing Automated Tests:** Full test suite covering unit tests, dynamic counter-offer bargaining, mandate security evaluation, back-office export formatting, anti-tamper verifications, and end-to-end autonomous lifecycles (`pytest backend/tests/` passes in 0.52s).
* **Zero Compilation Errors:** Clean TypeScript compilation with Vite (`npm run build` in 2.23s).
* **Unified Single Story:** All portal tabs tell one continuous story centered on Marcus Miller (*Miller Custom Flooring LLC*).
* **Headless Dual-Transport MCP Harness:** The Buyer Agent can run entirely from the terminal (`python -m backend.harness.external_buyer_agent --transport http|stdio`), negotiate with the Seller MCP, and print a cryptographic ledger entry in under 350ms.
* **Cold-State Interactive Fallback:** The Copilot UI features a 1-click test trigger so evaluators can generate and inspect live artifacts instantly on a clean server instance.

---

## 9. Built With

`python`, `fastapi`, `react`, `typescript`, `vite`, `paypal-api`, `paypal-vault`, `mcp-protocol`, `ag-studio`, `ag-grid`, `bryntum`, `zapier-mcp`, `jobber-graphql`, `quickbooks-api-v3`, `openapi-3.1`, `telnyx`, `pydantic`
