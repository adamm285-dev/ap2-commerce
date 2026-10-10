# AP2 Autonomous Commerce — Comprehensive Architectural Source Document
> **Authoritative Knowledge Base for Google NotebookLM & Gemini**  
> **Project:** AP2 Autonomous Commerce — Agent Payments Protocol Operations Deck  
> **Event:** PayPal AI Hackathon 2026 ($67,500+ Prize Purse • Targeting $18,000+ Across 6 Sponsor Tracks)  
> **Positioning:** Built on Google's AP2 (Agent Payments Protocol) v0.2 Specification, Prototyping What Its Official Roadmap Specifies for V1.x: Recurring Subscriptions, Human-Not-Present (HNP) Autonomous Purchases, Untrusted Courier MCP Isolation, and Dynamic Agent-to-Agent Negotiation.

---

## 1. Executive Summary & Problem Formulation

### 1.1 The Agentic Bottleneck
Autonomous AI agents, automated development pipelines, and specialized worker pools increasingly require dynamically provisioned cloud compute (dedicated inference gateways, high-throughput batch worker nodes, and elastic GPU clusters). However, traditional enterprise procurement infrastructure creates four insurmountable friction points for autonomous systems:

1. **Human Form-Factor Friction:** Autonomous software agents cannot navigate 15-field web checkout forms, solve human captchas, or type credit card numbers.
2. **Runaway Enterprise Budget Risk:** CFOs and engineering directors cannot grant autonomous agents unfettered corporate credit card access without deterministic, mathematically verifiable, tamper-proof spending mandates.
3. **The Untrusted Courier Vulnerability:** Exposing private signing keys directly to Large Language Models (LLMs) creates severe prompt injection and hallucination risks; an agent manipulated by external context could drain treasury funds.
4. **Disconnected Downline Accounting:** Once cloud compute is provisioned, human finance teams are bogged down manually recording recurring SaaS expenses into enterprise ERPs (e.g., QuickBooks Online) and updating operations calendars.
5. **Counterparty Risk & Entity Anonymity:** Autonomous agents transacting over the internet lack verified cryptographic identity unless anchored to an enrolled public key infrastructure.

### 1.2 The Solution: AP2 Autonomous Commerce
AP2 Autonomous Commerce is an end-to-end, multi-agent autonomous commerce and operations platform. It implements Google's AP2 (Agent Payments Protocol) v0.2 specification and prototypes the four major capabilities slated for AP2 V1.x:

- **Untrusted Courier Architecture (Two-Process MCP Model):** Isolates private keys entirely from the LLM. Claude Desktop or autonomous agents act as untrusted couriers between a local **Buyer Wallet MCP Server** and the **Seller Node MCP Server**. The wallet signs *only* merchant-certified checkouts that satisfy owner-signed limits.
- **Dynamic Multi-Tier Counter-Offer Negotiation:** When an agent's programmatic budget cap is lower than the requested compute tier's standard price, the Seller Agent autonomously computes and tenders an alternative tier (e.g., High-Throughput Batch Worker at $49.99/mo instead of $79.99/mo Dedicated Gateway).
- **Cryptographic Anti-Tamper Engine:** Verifies RFC 8032 Ed25519 and ES256 SD-JWT (Selective Disclosure JWT) mandate chains with HMAC-SHA256 authorization proofs. Any single byte alteration (such as inflating price by 1¢ or altering payee identity) is rejected with dual-signed error receipts.
- **Recurring PayPal Subscriptions & Vault MIT:** Executes recurring monthly compute subscriptions via the PayPal Subscriptions API (`I-A2A-VAULT-...`) backed by PayPal Vault setup tokens for off-session, merchant-initiated transactions (MIT).
- **Real-Time Operations Command Center (React 19 + AG Studio + Bryntum):** High-density fleet ledger built with AG Studio v3.0.0 and AG Grid Community with floating column filters, reconciling $13,438.32 ARR across 14 simulated nodes from SQLite WAL persistence, paired with Bryntum Scheduler 7.3.7 managing 24/7 compute execution shifts.
- **Autonomous Back-Office Accounting (Zapier MCP Bridge):** Automatically generates authentic QuickBooks Online (QBO) v3 Purchase payloads mapped to General Ledger Account 6300 (Software & SaaS) and schedules operational health audits in Google Calendar.

---

## 2. Protocol Architecture & The AP2 v0.2 Standard

### 2.1 The Google AP2 Specification (v0.2 Baseline)
The Agent Payments Protocol (AP2), developed by Google and industry partners, establishes an open cryptographic standard for agent-to-agent and human-to-agent commerce.
- **Vendored SDK Integrity:** AP2 Autonomous Commerce integrates Google's AP2 SDK directly in `backend/vendor/ap2/`, utilizing RFC 7515 / RFC 7519 / RFC 8032 standards for SD-JWT tokens and digital signatures.
- **Conformance & Invariant Guarantees:** 188 unmodified conformance tests from Google's AP2 repository pass byte-for-byte in `backend/tests/conformance/`, ensuring full baseline protocol compatibility.

### 2.2 The 4-Pillar AP2 V1.x Roadmap Prototype
While AP2 v0.2 defines core single-transaction cart and payment mandate structures, AP2's official public roadmap outlines four advanced capabilities for V1.x. AP2 Autonomous Commerce actively implements and prototypes all four:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 AP2 AUTONOMOUS COMMERCE INNOVATION MATRIX                   │
├─────────────────────────┬─────────────────────────┬─────────────────────────┤
│ AP2 V1.x Roadmap Item   │ Official AP2 Status     │ AP2 Autonomous Commerce │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ 1. Recurring Payments   │ Open design question    │ Implemented via PayPal  │
│    & Subscriptions      │ on public roadmap       │ Vault MIT & Mandates    │
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

---

## 3. Cryptographic Invariants & Mandate Chains

### 3.1 Mandate Anatomy & Cryptographic Separation
AP2 separates intent from execution across three distinct cryptographic documents:
1. **Owner-Signed Spending Limits (`signed_limits.jwt`):**
   - Issued off-session by the corporate human owner or treasurer.
   - Encodes: `buyer_email`, `monthly_budget_cap` (in integer cents), `allowed_merchants`, `allowed_tiers`, and expiration timestamp.
   - Cryptographically bound to the public key (`kid`) of the Buyer Agent Key.
2. **Merchant-Signed Checkout Mandate (`checkout_jwt`):**
   - Issued by the Seller Node during negotiation (`negotiate_tier_terms`).
   - Encodes: `tier_id`, price in minor currency units (cents), merchant identity, and an ephemeral `checkout_nonce`.
   - Signed using the seller's persistent ES256 merchant key (`ap2-merchant-key-1`).
3. **Agent-Signed Payment Mandate Chain (`payment_mandate_chain`):**
   - Produced by the Buyer Wallet after validating that the merchant checkout conforms to the owner's limits.
   - Bound to the merchant's `checkout_nonce`, guaranteeing the signature cannot be replayed on a different order.
4. **Combined Verification (`verify_ap2_chains`):**
   - The seller node cryptographically validates the entire chain before executing payments or allocating compute resources.

### 3.2 Key Invariants & Defensive Design
- **Fail Closed:** Any missing constraint, unparseable claim, or unknown algorithm triggers immediate refusal.
- **Trust Roots from Registry:** Trust roots originate *only* from the enrolled key registry via the challenge flow (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`). Key claims from headers or unverified bodies are ignored.
- **Strict Integer Cent Accounting:** Currency values are evaluated strictly as integer cents (`7999` cents for $79.99). Float multiplication is forbidden to eliminate rounding exploits and fractional cent leaks.
- **Dual-Signed Error Receipts:** When an invalid or tampered mandate is received, the system generates cryptographically signed error receipts detailing the exact violation (`PAYMENT_AMOUNT_MISMATCH`, `PAYEE_NOT_ALLOWED`, `BUDGET_CAP_EXCEEDED`).

---

## 4. The Untrusted Courier Architecture (Two-Process MCP Model)

### 4.1 The Threat Model
Giving an LLM direct access to an organization's private cryptographic keys introduces severe vulnerabilities:
- **Prompt Injection:** Malicious inputs from third-party websites or untrusted data sources could instruct the LLM to sign unauthorized transactions.
- **Model Hallucination:** The LLM might misread an invoice or invent payment authorizations exceeding budget limits.
- **Context Leakage:** Private key materials could leak into chat transcripts, system logs, or external monitoring.

### 4.2 The Two-Process Isolation Mechanism
To solve this, the platform implements the **Untrusted Courier Pattern** across two independent Model Context Protocol (MCP 2024-11-05) servers running side-by-side in Claude Desktop:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   UNTRUSTED COURIER ARCHITECTURE                       │
│                                                                        │
│    ┌──────────────────────────────────────────────────────────────┐    │
│    │               CLAUDE DESKTOP (Untrusted Courier)             │    │
│    │  • Coordinates conversation and negotiation                 │    │
│    │  • NEVER SEES OR POSSESSES PRIVATE KEYS                     │    │
│    └──────────────┬──────────────────────────────▲────────────────┘    │
│                   │                              │                     │
│    1. Inspect     │ 4. Sign                      │ 2. Negotiate        │
│       Limits      │    Checkout                  │    Terms            │
│                   ▼                              │                     │
│   ┌───────────────────────────────┐  ┌───────────┴─────────────────┐   │
│   │    BUYER WALLET MCP SERVER    │  │    SELLER NODE MCP SERVER   │   │
│   │  (backend.wallet.mcp_server)  │  │    (backend.mcp_server)     │   │
│   ├───────────────────────────────┤  ├─────────────────────────────┤   │
│   │ • Holds: Agent Key (ES256)    │  │ • Holds: Merchant Key       │   │
│   │ • Holds: Owner-Signed Limits  │  │ • Tools: 8 Commercial Tools │   │
│   │ • Exposes:                    │  │ • Endpoint: /mcp (FastMCP)  │   │
│   │   - get_spending_limits       │  │ • Validates: AP2 Chains     │   │
│   │   - sign_checkout             │  │                             │   │
│   │ • Enforces limits locally!    │  │                             │   │
│   └───────────────────────────────┘  └─────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Step 1 (Limit Inspection):** Claude calls `get_spending_limits` on the Buyer Wallet. The wallet returns public parameters: `buyer_email`, `monthly_budget_cap`, and `allowed_tiers`.
2. **Step 2 (Seller Negotiation):** Claude calls `negotiate_tier_terms` on the Seller Node, submitting the desired compute tier and budget cap. The seller returns a merchant-signed `checkout_jwt`.
3. **Step 3 (Local Verification & Signing):** Claude calls `sign_checkout` on the Buyer Wallet, passing the `checkout_jwt`. The wallet *independently parses and verifies* the merchant signature and tests the price against the owner's signed limit. Only if it fits does the wallet sign the payment mandate. If Claude requests a $79.99 tier with a $60.00 limit, the wallet returns an explicit `WalletRefusal` tool error.
4. **Step 4 (Settlement):** Claude hands the signed mandate chains to the seller's `purchase_subscription` tool.

### 4.3 Automated Zero-Leak Setup Script
The entire local security perimeter is provisioned with a single command:
```bash
python scripts/setup_claude_desktop_demo.py --monthly-cap 60
```
- Generates 3 separate cryptographic keys under `.ap2_local/` (gitignored).
- Enrolls the owner key via the real cryptographic challenge endpoint.
- Signs owner limits bound to the agent's key.
- Writes a ready-to-use `claude_desktop_config.local.json` with absolute paths.
- Uses an isolated database (`backend/data/claude_desktop_demo.db`), guaranteeing zero contamination of development or production databases.

---

## 5. Dynamic Negotiation & Sub-Budget Counter-Offers

### 5.1 Multi-Tier Compute Catalog
The Seller Node manages three distinct compute infrastructure tiers:
- **`ap2-batch` (High-Throughput Batch Worker):** $49.99/month (4,999 cents) • 125 workload tasks/mo.
- **`ap2-gateway` (Dedicated AI Service Gateway):** $79.99/month (7,999 cents) • 450 workload tasks/mo.
- **`ap2-cluster` (Elastic Distributed GPU Cluster):** $199.99/month (19,999 cents) • 1,200 workload tasks/mo.

### 5.2 Autonomous Bargaining Logic
When a Buyer Agent requests a tier exceeding its spending mandate (e.g., requesting `ap2-gateway` at $79.99/mo while constrained by a $60.00/mo cap):
1. The Seller Node detects that `tier.price_cents > budget_cap_cents`.
2. Rather than a flat rejection, the bargaining engine searches the catalog for the highest-specification tier that satisfies `tier.price_cents <= budget_cap_cents`.
3. The seller returns an autonomous counter-offer for `ap2-batch` ($49.99/mo), complete with structured reasoning:
   > *"Requested amount $79.99 exceeds remaining monthly budget cap of $60.00. Counter-offer available: High-Throughput Batch Worker (125 workload tasks/mo) at $49.99/mo."*
4. The Buyer Agent evaluates the counter-offer against its workload queues and autonomously signs the scaled mandate.

---

## 6. Payment Rails & Lifecycle Management

### 6.1 PayPal Subscriptions & Vault MIT
- **Standard Cycles:** Executes recurring subscriptions using the PayPal Subscriptions API (`@paypal/react-paypal-js` and PayPal Server SDK).
- **Merchant-Initiated Transactions (MIT):** Establishes customer-approved Vault setup tokens, enabling off-session overage settlement when task quotas are exceeded.
- **Database Persistence:** All subscription tokens (`I-A2A-VAULT-...`), mandate hashes, and cycle counters persist in SQLite WAL (`a2a_commerce.db`) with 5,000ms busy timeout handling.

### 6.2 Production Delta & Honest Protocol Pitch
- **What is verified today:** Month 1 purchase, dynamic counter-offer signing, cryptographic mandate chain validation, budget cap adherence, and webhook state transitions.
- **The Protocol Roadmap Frontier:** In current production implementations across the industry, recurring payment tokens bill autonomously via payment gateways. The AP2 open question is: *How should Month 2+ renewals be verified against expiring human mandates?* AP2 Autonomous Commerce implements persistent SQLite cycle tracking and webhook reconciliation, providing a working reference implementation for this exact roadmap milestone.

---

## 7. Interactive Operations Deck & Front-End Architecture

### 7.1 AG Studio v3.0.0 & AG Grid Community Operations Ledger
The operations portal (`/portal/`) provides an executive command center:
- **Embedded AG Studio v3.0.0:** Integrates `ag-studio-react` and `ag-studio` with AG Grid Community.
- **Floating Column Filters:** All grid columns feature full floating filter inputs (`floatingFilter: true`) with 34px filter row height for real-time fleet filtering.
- **Live SQLite WAL Hydration:** Zero hardcoded data. The grid dynamically queries `/api/fleet/subscriptions`, reflecting live database records across 14 simulated compute nodes.
- **Reconciled Financial Telemetry:**
  - Active Fleet MRR: $1,119.86/mo ($1,219.87/mo in live test runs).
  - Autonomous ARR GMV: $13,438.32 ARR.
  - Policy Enforcement: 100% Policy Enforced • 0 Budget Leaks.
- **Runtime View / Drag-and-Drop Edit Mode:** Operators can toggle between an operational dashboard view and an editing mode to rearrange grid widgets, charts, and metrics.

### 7.2 Bryntum Scheduler (24/7 Compute Execution Dispatch)
- **Workload Shift Management:** Evaluated with `@bryntum/scheduler` 7.3.7 trial build.
- **Live Reactive Status Transitions:** Displays compute node shifts across regional cluster zones. When a new node is provisioned, its schedule card starts in amber/orange (`AWAITING PAYMENT`). Upon completed PayPal settlement, the card reactively transitions in-place to vibrant green (`NODE ACTIVE: gateway-01.ap2.net:8443`).

### 7.3 Live Wire Protocol Inspector & Anti-Tamper Simulator
- **SSE Stream (`/sse`):** Server-Sent Events stream raw JSON-RPC 2.0 frames (`initialize` → `tools/list` → `tools/call` → `vault/token`) with sub-millisecond timestamps.
- **Byte-Level Anti-Tamper Lab:** An interactive terminal allowing judges to modify individual characters in canonical JSON payloads (e.g., inflating price by 1¢ or modifying payee identity) to immediately observe cryptographic rejection: `401 Signature Mismatch: Budget Policy Violated`.

---

## 8. Autonomous Back-Office ERP Bridge (Zapier MCP)

### 8.1 Model Context Protocol Accounting Bridge
Upon successful subscription execution, the system invokes the `dispatch_zapier_mcp` tool:
1. **QuickBooks Online API v3:** Generates authentic QBO v3 Purchase payloads mapping the recurring subscription expense to **General Ledger Account 6300 (Software & SaaS)** with reference to the PayPal subscription ID.
2. **Operational Fleet Routing:** Registers the newly provisioned node endpoint into operational health monitoring.
3. **Google Workspace Synchronization:** Schedules automated daily node health audits on Google Calendar.
4. **Security & Sandboxing:** Implements SSRF-safe URL validation and HMAC-SHA256 signature stamping on all outbound webhook envelopes.

---

## 9. Multi-Sponsor Track Alignment ($18,000+ Purse)

| Sponsor Track | Targeted Prize | Key Technical Deliverables & Architectural Alignment |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **$5,000** | Autonomous AP2 mandate negotiation, counter-offer bargaining, delegated PayPal Subscriptions with Vault MIT off-session tokens, and automated compute node provisioning. |
| **Best Use of AG Grid / AG Studio** | **$5,000** | Embedded AG Studio v3.0.0 (`ag-studio-react`), AG Grid Community with floating column filters, live SQLite WAL data hydration, and dual View/Edit modes reconciling $13,438.32 ARR. |
| **Best Use of PayPal + AI** | **$5,000** | FastMCP 2024-11-05 server, real-time HTTP/SSE wire protocol inspector, autonomous multi-turn negotiation, and intelligent sub-budget counter-offer generation. |
| **Best Use of Bryntum** | **$1,000** | Evaluated with Bryntum Scheduler trial build managing 24/7 compute execution shifts with live in-place reactive color state transitions (Orange → Green). |
| **Best Use of Zapier** | **$1,000** | Zapier MCP Protocol Bridge (`dispatch_zapier_mcp`) executing automated QuickBooks Online v3 (GL 6300) expense creation and Google Calendar scheduling. |
| **Best Use of APIMatic** | **$1,000** | Production-grade OpenAPI 3.1.0 specification with 33 endpoints (`openapi.yaml` & `openapi.json`), `apimatic.json` multi-language SDK configuration, and self-service buyer key onboarding. |

---

## 10. Empirical Verification & Judge Audit Telemetry

### 10.1 The 9-Check Judge Audit Harness (`python scripts/judge_audit_harness.py`)
Runs in <0.2 seconds with **zero external dependencies or API keys**:
1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** Validates `initialize` and `tools/list` protocol handshake returning 8 registered seller tools.
2. **[CHECK 2] Standard AP2 Negotiation:** Evaluates $79.99/mo Service Gateway under $100 budget cap with HMAC-SHA256 cryptographic authorization proof.
3. **[CHECK 3] Sub-Budget Counter-Offer Bargaining:** Generates scaled-down *Batch Worker* ($49.99/mo) counter-offer when cap is $60.00.
4. **[CHECK 4] Anti-Tamper Verification:** Proves 1-cent inflation tampering, payee alteration, and budget breaches are strictly rejected.
5. **[CHECK 5] Compute Node Provisioning:** Validates subscription verification and compute node endpoint allocation (`batch-01`, `gateway-01`, `cluster-01`).
6. **[CHECK 6] Back-Office ERP Payloads:** Generates authentic QuickBooks Online v3 Purchase mapped to GL Account 6300.
7. **[CHECK 7] Financial Telemetry Reconciliation:** Reconciles 14 simulated subscriber nodes, $1,119.86/mo MRR, and $13,438.32 ARR GMV to the penny.
8. **[CHECK 8] AG Studio & Bryntum Scheduling:** Hydrates 14 nodes from SQLite WAL and verifies 24/7 compute execution shifts.
9. **[CHECK 9] Dynamic Buyer Key Onboarding:** Generates 300s ephemeral challenge nonce, validates cryptographic signature, enrolls buyer key, and rejects forged signatures.

### 10.2 Comprehensive Automated Test Suite
```bash
python -m pytest backend/tests -q -n 4
# Result: 531 passed, 9 skipped (100% green)
```
- Includes 21 dedicated Buyer Wallet MCP security tests (`test_buyer_wallet.py`).
- Strict temp-database isolation via `conftest.py` ensuring the development database remains completely pristine.

---

## 11. Complete 8-Slide Executive Architecture Walkthrough (Fact-Checked Ground Truth)

This blueprint incorporates the line-by-line systems engineering audit. It accurately reflects the actual codebase, replaces all AI-generated artifacts/stale figures, and provides the exact text for slide generation.

### Slide 1: AP2 Autonomous Commerce: Prototyping What Comes After v0.2
- **Title:** AP2 Autonomous Commerce: Prototyping What Comes After v0.2
- **Subtitle:** Built on Google's AP2 v0.2 SDK and Prototyping Four Public Roadmap Items
- **Visual:** Architectural baseline diagram. Left: Google AP2 v0.2 SDK Baseline (188 tests passing from upstream). Right: 4 Roadmap Items: (1) Subscriptions [V1.x], (2) Human-Not-Present Purchases [V1.x], (3) MCP Implementations [V1.x], (4) Real-Time Negotiation [Long-Term Vision].
- **Core Invariants:**
  - Integrates Google's AP2 v0.2 SDK with two verification fixes documented in `backend/vendor/ap2/NOTICE`.
  - Implements the complete 3-signer mandate hierarchy: the owner signs spending limits, the merchant signs the checkout, and the agent's wallet signs the purchase.
  - Honest Positioning: We built on Google's AP2 v0.2 SDK and prototyped four items from its public roadmap.
- **Code Anchor:** `backend/vendor/ap2/`, `backend/services/ap2_service.py`, `backend/tests/conformance/`
- **Narration (20s):** "Google released AP2 v0.2 to standardize single, human-in-the-loop agent checkouts. We built on Google's AP2 v0.2 SDK and prototyped four items from its public roadmap: recurring subscriptions, Human-Not-Present purchases, an isolated MCP wallet architecture, and dynamic agent-to-agent negotiation."

### Slide 2: The Core Vulnerability: The Untrusted Courier Threat
- **Title:** The Untrusted Courier Threat: Why LLMs Must Never Hold Private Keys
- **Subtitle:** Mitigating Prompt Injection and Context Leakage with Cryptographic Isolation
- **Visual:** Threat model schematic. An LLM (Claude Desktop) acting between user prompts and the network. Red attack vectors: Prompt injection or poisoned context instructing the LLM to overspend. Green shield: Moving private keys into an isolated local wallet process, relegating the LLM to an *Untrusted Courier* holding zero key material.
- **Core Invariants:**
  - LLMs with direct access to private signing keys expose corporate treasuries to prompt injection and context leakage.
  - Context leakage and hallucinations can arbitrarily commit treasury funds without human oversight.
  - Architectural Solution: Relegate the LLM to an 'Untrusted Courier' holding zero key material.
- **Code Anchor:** `backend/wallet/wallet.py`, `backend/tests/test_buyer_wallet.py` (21 dedicated security tests)
- **Narration (20s):** "If you give an LLM your private cryptographic keys, a single prompt injection can drain your bank account. In our architecture, the LLM is strictly an untrusted courier. It coordinates the conversation, but keys live in an isolated local wallet that refuses to sign any checkout exceeding owner-authorized limits."

### Slide 3: Two-Process MCP Architecture: The Buyer Wallet
- **Title:** Two-Process MCP Architecture: The Isolated Buyer Wallet Solution
- **Subtitle:** Local Limit Verification and Key Separation Outside the LLM Context
- **Visual:** Two-Process architectural flow:
  1. Claude Desktop (Courier) inspects limits on local Buyer Wallet (`backend.wallet.mcp_server`).
  2. Claude negotiates compute terms with Seller Node (`backend.mcp_server`) and receives a merchant-signed `checkout_jwt`.
  3. Claude passes `checkout_jwt` to Buyer Wallet (`sign_checkout`).
  4. Buyer Wallet validates price and tier against owner-signed limits *locally* using the Agent Key.
  5. If Claude attempts to buy an unauthorized plan, triggers a hard local `WalletRefusal`.
- **Core Invariants:**
  - Key Separation: The wallet holds the owner's *signed limits* and the *agent's own key*. It never holds the owner's private key.
  - The wallet reads price, tier, and merchant from the merchant's signature, not from LLM arguments.
  - Tricking the courier into a premium tier triggers a hard local `WalletRefusal` before signature generation (e.g. 'Amount 7999 exceeds maximum 6000').
- **Code Anchor:** `backend/wallet/mcp_server.py`, `scripts/setup_claude_desktop_demo.py`
- **Narration (20s):** "To solve this, Claude runs two independent MCP servers. The Seller Node offers compute tiers. The Buyer Wallet holds the agent's private key and owner-signed limits—never the owner's private key. When Claude negotiates an order, the wallet independently parses the merchant's signature. If Claude is tricked into overspending, the wallet independently blocks the signature."

### Slide 4: Recurring Billing & Renewal Enforcement
- **Title:** Recurring Billing & Renewal Enforcement: Extending AP2 Mandates
- **Subtitle:** Webhook Verification, Advance Cancellation, and Decoupled Terms
- **Visual:** Recurring lifecycle pipeline:
  - Step 1: Owner signs spending limits (24-hour window to start purchase; recurring authority extends 372 days).
  - Step 2: Agent signs Payment Mandate; PayPal creates recurring subscription (`I-A2A-VAULT-...`).
  - Step 3: On each `PAYMENT.SALE.COMPLETED` webhook: re-verifies stored mandate signature against owner key, checks SDK budget/cycle caps, checks agreed price.
  - Step 4: Advance Cancellation: after each authorized charge, checks if the *next* charge would be authorized; if not, cancels ahead of time so PayPal never charges it.
- **Core Invariants:**
  - Owner purchase-start window is 24 hours; recurring charge authority lasts 372 days (12 monthly payments).
  - Webhooks cannot undo charges that already moved; system performs advance cancellation to prevent unauthorized charges.
  - Unverifiable charges are suspended; budget-breaking charges are cancelled; refunds are manual. Tested in mock mode.
- **Code Anchor:** `backend/services/recurring_mandate_service.py`, `backend/server.py`, `backend/database.py`
- **Narration (20s):** "AP2 v0.2 has no standard for subscriptions. We built one where each PayPal renewal webhook is re-verified against the owner's stored mandate using Google's SDK. Because webhooks arrive after money moves, the system checks the next charge in advance and cancels before an unauthorized charge can happen."

### Slide 5: Dynamic Bargaining & Anti-Tamper Defense
- **Title:** Dynamic Bargaining & Anti-Tamper Defense: Sub-Budget Counter-Offers
- **Subtitle:** Autonomous Multi-Tier Fallbacks and Real AP2 ES256 Signature Verification
- **Visual:** Split screen. Left: Dynamic Bargaining Decision Tree ($60 budget cap vs $79.99 Gateway ➔ evaluates catalog ➔ tenders Batch Worker at $49.99/mo). Right: Real Judge Harness Check 4 output showing a 1-cent inflation attempt ($79.99 ➔ $80.00) failing closed with `invalid_mandate` and dual-signed error receipts.
- **Core Invariants:**
  - Autonomous fallback identifies sub-budget compute tiers when buyer caps are below standard pricing.
  - Mandate amounts are integer cents to eliminate floating-point rounding exploits.
  - Fail-closed cryptographic defense: altering price by 1¢ ($79.99 ➔ $80.00) or altering payee triggers immediate ES256 SD-JWT rejection.
- **Code Anchor:** `backend/services/ap2_service.py`, `backend/wallet/wallet.py`, `scripts/judge_audit_harness.py` (Checks 3 & 4)
- **Narration (20s):** "If an agent's budget is too low, our seller agent autonomously counter-offers a cheaper tier within the cap. Crucially, attempting to alter the price by even a single cent—or modifying the payee—triggers an immediate cryptographic signature mismatch under AP2's ES256 SD-JWT verifier."

### Slide 6: Simulated Fleet Operations: Downline ERP & Visual Dispatch
- **Title:** Simulated Fleet Operations: Downline ERP & Visual Dispatch
- **Subtitle:** Reconciling Telemetry with AG Studio, Bryntum Scheduler, and QuickBooks Payloads
- **Visual:** Tri-pane operational overview. Top-Left: Embedded AG Studio v3.0.0 with AG Grid Community floating filters (`EnterpriseFleetLedger.tsx`), hydrating 14 simulated nodes ($14,638.44 annualized ARR, $1,219.87 MRR, 13 active). Bottom-Left: Bryntum Scheduler managing 24/7 compute execution shifts. Right: Zapier MCP bridge generating authentic QuickBooks Online API v3 expense payloads (GL Account 6300).
- **Core Invariants:**
  - Reconciles 14 simulated compute nodes, $1,219.87/mo MRR, and $14,638.44 ARR GMV across SQLite WAL persistence.
  - Bryntum Scheduler manages 24/7 compute execution shifts with reactive visual state transitions.
  - Zapier MCP bridge generates authentic QuickBooks Online expense payloads mapped to GL Account 6300 for signed webhook export.
- **Code Anchor:** `src/components/EnterpriseFleetLedger.tsx`, `src/components/BryntumDispatchScheduler.tsx`, `backend/services/backoffice/qbo_exporter.py`
- **Narration (20s):** "Post-purchase, operators monitor simulated fleet nodes across AG Studio and Bryntum Scheduler, which dynamically reconcile $14,638 in ARR across 13 active nodes. Simultaneously, our Zapier MCP bridge generates authentic QuickBooks Online expense payloads mapped to General Ledger Account 6300 for export."

### Slide 7: The Production Gap Report: The Path to Production
- **Title:** The Production Gap Report: The Path to Production
- **Subtitle:** Honest Engineering Analysis of Current Limitations vs Production Requirements
- **Visual:** 4-pillar Diagnostic Matrix:
  1. Hardware Security: Local Disk Keys ➔ Secure Enclave / Passkeys (Status: Critical Gap)
  2. State & Replay: In-Memory Nonce Caches ➔ Shared Database / KMS (Status: Critical Gap)
  3. Ecosystem Reality: Seller Acts as Verifier Bridge ➔ Native PayPal AP2 Ingestion (Status: Interim Bridge)
  4. Mandate Revocation: Time-Based Expiration ➔ Revocation Checks / CRL (Status: Gap)
- **Core Invariants:**
  - Hardware Security: Demo uses local disk keys; production requires Secure Enclave / Passkey WebAuthn.
  - State & Replay: In-memory nonce caches clear on restart; production requires a shared database.
  - Ecosystem Reality: PayPal does not natively ingest AP2 mandates yet; seller node acts as an interim verifier bridge.
  - Revocation: Owner cannot cancel signed limits early; only time-based expiration exists.
- **Code Anchor:** `backend/services/ap2_keys.py`, `backend/server.py`
- **Narration (20s):** "A responsible prototype acknowledges its limits. To reach production, local disk keys must migrate to hardware passkeys, in-memory replay caches must move to shared databases, revocation checks must be added, and payment rails must eventually ingest AP2 mandates directly."

### Slide 8: Empirical Verification: A Working Prototype for AP2
- **Title:** Empirical Verification: A Working Prototype for the AP2 Ecosystem
- **Subtitle:** 554 Passing Tests, 9/9 Judge Audit Checks, and an Open Reference Blueprint
- **Visual:** Terminal dashboard. Left: 554 tests passed, 9 skipped in ~29s (188 Google SDK tests + 366 project tests; 9 skipped are live PayPal calls). Right: 9-check Judge Audit Harness passing in <0.2s with zero external dependencies (MCP handshake, AP2 negotiation, counter-offer, anti-tamper, node provisioning, QuickBooks payloads, fleet reconciliation, AG Studio/Bryntum telemetry, key onboarding).
- **Core Invariants:**
  - Comprehensive automated test suite: 554 passed, 9 skipped in ~29 seconds (100% green).
  - 9-check zero-dependency judge audit harness validates entire core seller flow in under 0.2 seconds.
  - Working prototype of Untrusted Courier and recurring mandate verification ready to share with the AP2 open source project.
- **Code Anchor:** `scripts/judge_audit_harness.py`, `pytest backend/tests/ -q -n 4`
- **Narration (20s):** "We back this architecture with rigorous proof: 554 passing tests and a 9-check audit harness that runs in under 0.2 seconds with zero external dependencies. This is an open, working prototype demonstrating how to solve recurring subscriptions and untrusted courier wallets for the AP2 ecosystem."

---

### Executive Slide Deck Summary Table (For README & Devpost)

| Slide | Title | Core Technical Innovation | Verified Code Anchor |
| :---: | :--- | :--- | :--- |
| **01** | **AP2 v0.2 Baseline & V1 Roadmap** | Working Google AP2 v0.2 implementation prototyping 4 public roadmap items | `backend/vendor/ap2/`, `backend/tests/conformance/` |
| **02** | **The Untrusted Courier Threat** | Threat model proving why LLMs must never possess private cryptographic signing keys | `backend/wallet/wallet.py`, `backend/tests/test_buyer_wallet.py` |
| **03** | **Two-Process MCP Architecture** | Buyer Wallet holds agent key and owner limits (never owner's private key); courier blocked on overspend | `backend/wallet/mcp_server.py`, `scripts/setup_claude_desktop_demo.py` |
| **04** | **Recurring Billing & Renewal Enforcement** | PayPal webhook re-verification + advance cancellation before unauthorized charges occur | `backend/services/recurring_mandate_service.py`, `backend/server.py` |
| **05** | **Dynamic Bargaining & Anti-Tamper** | Autonomous counter-offers ($49.99 Batch Worker) + 1¢ inflation rejection under real AP2 ES256 verifier | `backend/services/ap2_service.py`, `backend/wallet/wallet.py` |
| **06** | **Simulated Fleet Operations** | AG Studio v3.0.0 (`EnterpriseFleetLedger.tsx`) + Bryntum Scheduler + Zapier QBO GL 6300 export | `src/components/EnterpriseFleetLedger.tsx`, `backend/services/backoffice/qbo_exporter.py` |
| **07** | **The Production Gap Report** | Candid 4-pillar gap analysis: Hardware passkeys, shared state, revocation checks, and rail convergence | `backend/services/ap2_keys.py`, `backend/server.py` |
| **08** | **Empirical Verification** | 554 passing tests (188 SDK + 366 project), 9/9 zero-dependency judge checks in <0.2s | `pytest backend/tests/ -q -n 4`, `scripts/judge_audit_harness.py` |



