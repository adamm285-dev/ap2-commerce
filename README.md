# AP2 Autonomous Commerce &mdash; Agent Payments Protocol Operations Deck

> **Built on Google's AP2 (Agent Payments Protocol) v0.2, prototyping what its official roadmap says comes next for V1.x:**  
> 1. **Recurring Subscriptions & Vault Binding**  
> 2. **Human-Not-Present (HNP) Autonomous Purchases**  
> 3. **Untrusted Courier MCP Isolation (Claude Desktop + Local Buyer Wallet MCP)**  
> 4. **Dynamic Agent-to-Agent Negotiation & Counter-Offers**  
>
> Built for the **PayPal AI Hackathon 2026** (\$67,500+ Prize Purse &bull; Targeting \$18,000+ Across 6 Sponsor Tracks)  
> Combining **PayPal Agentic Commerce & Vault**, **AG Studio v3.0.0 & AG Grid Community**, **Bryntum Scheduler**, **APIMatic**, and **Zapier MCP**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AG Studio: v3.0.0](https://img.shields.io/badge/AG%20Studio-v3.0.0-blue.svg)](https://www.ag-grid.com/studio/react/)
[![PayPal Agentic Commerce](https://img.shields.io/badge/PayPal-Agentic%20Commerce-003087.svg)](https://github.com/paypal/AI-Toolkit)
[![OpenAPI 3.1.0](https://img.shields.io/badge/OpenAPI-3.1.0-green.svg)](openapi.yaml)
[![Tests: 557 Passed](https://img.shields.io/badge/Tests-557%20Passed%20(100%25)-brightgreen.svg)](backend/tests/)
[![Judge Audit: 9/9 Passed](https://img.shields.io/badge/Judge%20Audit-9%2F9%20Passed%20(100%25)-brightgreen.svg)](scripts/judge_audit_harness.py)

---

## 🌐 System Endpoints & Interfaces

| Resource | Protocol / Location | Description |
| :--- | :--- | :--- |
| **Interactive Operations Deck** | React 19 + AG Studio + Bryntum UI (`/portal/`) | Full visual command center with live protocol inspector |
| **FastMCP Seller Server** | MCP 2024-11-05 JSON-RPC 2.0 (`/mcp`) | Model Context Protocol server exposing autonomous seller tools |
| **Untrusted Courier Buyer Wallet MCP** | Stdio / JSON-RPC 2.0 (`backend.wallet.mcp_server`) | Isolated local wallet holding agent keys and validating owner-signed limits |
| **Live SSE Wire Stream** | Server-Sent Events (`/sse`) | Real-time JSON-RPC 2.0 packet inspector frames |
| **OpenAPI 3.1.0 Specification** | `openapi.yaml` & `openapi.json` | 33 typed endpoints covering negotiation, mandates, and vault |
| **Interactive API Documentation**| Swagger UI (`/docs`) | Interactive REST endpoint documentation and schema explorer |
| **Agent Discovery Card** | JSON Metadata (`/agents.json`) | Machine-readable A2A capability and discovery descriptor |

---

## ⚡ Quickstart for Judges

> **⚠️ Judge Evaluation Note:** Execute **`python scripts/judge_audit_harness.py`** as your primary evaluation command. It requires **zero external API keys or configuration**, runs in <0.2 seconds, and asserts all 9 protocol, cryptographic (ES256 SD-JWT and Ed25519 dual mandates), and operational invariants directly.

### 0. Clone & Environment Setup
Run the initial setup to configure the local mock environment, install dependencies, and launch the frontend:
```bash
cp .env.example .env
pip install -r backend/requirements.txt
npm install
npm run dev
```

### 1. One-Click In-Memory Audit (Zero Dependencies)
Run the 9-step audit locally against the autonomous seller engine:
```bash
python scripts/judge_audit_harness.py
# 9/9 checks passed (100% green)
```

### 2. Run the Full Automated Test Suite
Run the comprehensive test suite across all cryptographic, negotiation, and persistence modules:
```bash
pytest backend/tests/ -q -n 4
# 557 passed, 9 skipped (188 Google SDK tests + 369 project tests; 9 live PayPal calls skipped)
```

### 3. Run Autonomous AI Buyer Agent CLI Simulation
Simulate an end-to-end LLM-driven buyer agent negotiating and provisioning a compute node under a spending mandate:
```bash
python -m backend.agents.llm_buyer_agent --budget 60 --tier ap2-gateway
```

### 4. Buy with Claude Desktop (Seller MCP + Buyer Wallet MCP)
Claude Desktop runs two MCP servers side by side: the seller (`backend.mcp_server`) and the buyer's wallet (`backend.wallet.mcp_server`). Claude negotiates with the seller, asks the wallet to sign, and hands the signed AP2 v0.2 mandate chains back to the seller. Claude is strictly an **untrusted courier** and never sees private keys. The wallet signs only checkouts that fit the owner's signed limits, even if Claude tells the seller a bigger budget.

```bash
python scripts/setup_claude_desktop_demo.py --monthly-cap 60
```

The script:
1. Creates three separate keys under the gitignored `.ap2_local/`: merchant, buyer agent (created by the wallet process itself) and owner.
2. Enrolls the owner key through the challenge flow.
3. Has the owner sign $60/mo limits bound to the wallet's agent key.
4. Writes `claude_desktop_config.local.json` with absolute paths.

Copy its two entries into Claude Desktop's `claude_desktop_config.json` and restart Claude Desktop. The demo uses its own database (`backend/data/claude_desktop_demo.db`), never the dev database. Then ask Claude: *"Check my wallet's spending limits, then buy the best AP2 compute plan you can within them."*

---

## 1. Executive Summary & The 4-Pillar AP2 V1 Roadmap Prototype

Google released the **AP2 (Agent Payments Protocol) v0.2** specification to standardize agent payments using Selective Disclosure JWTs (SD-JWT) and cryptographically verifiable intent/cart mandates. However, AP2 v0.2 targets single, human-present checkouts. AP2 Autonomous Commerce implements the v0.2 standard with Google's vendored SDK (`backend/vendor/ap2/`) and **actively prototypes the four open items on AP2's official V1 roadmap**:

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

### Core Innovations:
- **Untrusted Courier Architecture (Prompt Injection Defense):** Exposing private keys to LLMs creates catastrophic prompt injection vulnerabilities. We isolate keys in `backend.wallet.mcp_server`. The LLM coordinates negotiation, but the wallet independently parses the merchant's signature and raises a hard `WalletRefusal` if the courier is tricked into overspending.
- **Month-2 Renewal Verification & Advance Cancellation Engine:** In `backend/services/recurring_mandate_service.py`, every PayPal renewal webhook (`PAYMENT.SALE.COMPLETED`) is re-verified against the owner's stored mandate using Google's SDK. Because webhooks arrive after money has moved, the engine evaluates the *next* billing cycle in advance and cancels ahead of time so unauthorized renewal charges never occur.
- **Decoupled Purchase vs Recurring Windows:** The owner's authorization grants a 24-hour window to complete the initial checkout, while the recurring payment authority remains valid for 372 days (12 monthly payment cycles).
- **Dynamic Multi-Tier Counter-Offer Bargaining:** When the buyer's budget cap is below asking price ($60 cap vs $79.99 Gateway), the Seller Agent autonomously calculates and tenders a scaled alternative (*High-Throughput Batch Worker at $49.99/mo*) which the Buyer Agent verifies and signs autonomously.
- **Cryptographic Anti-Tamper Engine:** Validates ES256 SD-JWT and Ed25519 mandate chains. Altering a price by even 1¢ ($79.99 &rarr; $80.00) or tampering with payee identity immediately fails closed with `401 Signature Mismatch: Budget Policy Violated` and generates dual-signed error receipts.
- **Self-Service Buyer Key Onboarding:** Enables autonomous buyer agents to complete an asymmetric Ed25519 cryptographic challenge-response registration (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`).
- **Zapier MCP Downline Automation:** Automatically dispatches verified subscriptions into QuickBooks Online (recording recurring SaaS expenses mapped to GL Account 6300) and schedules health audits in Google Calendar.
- **AG Studio v3.0.0 & AG Grid Community Analytics:** High-density fleet ledger with floating column filters, interactive data refresh, and compute volume analytics reconciling **$14,638.44 annualized ARR** ($1,219.87 MRR across 13 active nodes) directly from SQLite WAL persistence.

---

## 2. Executive Slide Deck Summary (8-Slide Architecture)

The following 8-slide architecture walkthrough reflects the production codebase and verified audit proofs:

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

## 3. Multi-Sponsor Architecture & Prize Alignments (\$18,000+ Purse)

| Sponsor Track | Prize | Implementation & Technology |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **\$5,000** | `@paypal/react-paypal-js`<br/>`@paypal/paypal-server-sdk` | Autonomous AP2 mandate negotiation, counter-offer bargaining, delegated subscription approvals, and Vault MIT settlement. |
| **Best Use of AG Grid / AG Studio** | **\$5,000** | `ag-studio-react`<br/>`ag-studio` (v3.0.0)<br/>AG Grid Community | High-density grid telemetry with floating column filters, live SQLite WAL data hydration, and dual View/Edit reporting modes reconciling \$14,638.44 ARR across 13 active nodes (14 total). |
| **Best Use of PayPal + AI** | **\$5,000** | FastMCP 2024-11-05 Server<br/>SSE Wire Stream Inspector | Streamable HTTP/SSE wire protocol inspector, autonomous multi-turn negotiation, and intelligent sub-budget counter-offer generation. |
| **Best Use of Bryntum** | **\$1,000** | `@bryntum/scheduler` 7.3.7 (Trial Build) | Regional workload dispatch calendar managing 24/7 compute node shifts with live in-place reactive status transitions (Orange &rarr; Green). |
| **Best Use of Zapier** | **\$1,000** | Zapier MCP Protocol Bridge<br/>CloudEvents v1.0 | Automated back-office execution syncing recurring PayPal expenses into QuickBooks Online (GL Account 6300) via Model Context Protocol. |
| **Best Use of APIMatic** | **\$1,000** | OpenAPI 3.1.0 Contract<br/>Ed25519 Challenge-Response | Production-grade OpenAPI specification with 33 endpoints (`openapi.yaml` and `openapi.json`), `apimatic.json` configuration for multi-language SDK compilation, and self-service buyer key onboarding. |

---

## 4. The 9 Judge Audit Verification Checks

1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** Validates `initialize` and `tools/list` protocol handshake returning 8 registered seller tools.
2. **[CHECK 2] Standard AP2 Negotiation:** Evaluates \$79.99/mo Service Gateway under \$100 budget cap with ES256 SD-JWT cryptographic authorization proof.
3. **[CHECK 3] Sub-Budget Counter-Offer Bargaining:** Generates scaled-down *Batch Worker* (\$49.99/mo) counter-offer when cap is \$60.00.
4. **[CHECK 4] Anti-Tamper Verification:** Proves 1-cent inflation tampering, entity name alteration, and budget breaches are strictly rejected under Google's AP2 verifier.
5. **[CHECK 5] Compute Node Provisioning:** Validates subscription verification and compute node endpoint allocation (`batch-01`, `gateway-01`, `cluster-01`).
6. **[CHECK 6] Back-Office ERP Payloads:** Generates authentic QuickBooks Online v3 Purchase mapped to GL Account 6300.
7. **[CHECK 7] Financial Telemetry Reconciliation:** Reconciles 14 subscriber lines (13 active, 1 pending), \$1,219.87/mo MRR, and \$14,638.44 ARR GMV to the penny.
8. **[CHECK 8] AG Studio & Bryntum Scheduling:** Hydrates 14 nodes from SQLite WAL and verifies 24/7 compute execution shifts.
9. **[CHECK 9] Dynamic Buyer Key Onboarding:** Generates 300s ephemeral Ed25519 challenge nonce, validates cryptographic signature, enrolls buyer key, and rejects forged signatures.

---

## 5. Technology Stack

- **Runtime & Build:** Node.js 22+ / 24 + Vite 8 + React 19 + TypeScript
- **Embedded Analytics:** AG Studio v3.0.0 (`ag-studio-react`, `ag-studio`, `ag-charts-enterprise`) + AG Grid Community with custom floating filters
- **Payments:** PayPal Subscriptions SDK (`@paypal/react-paypal-js`, `@paypal/paypal-server-sdk`) & PayPal Vault MIT
- **Workload Scheduling:** Bryntum Scheduler 7.3.7 (`@bryntum/scheduler` trial build)
- **API Specification:** OpenAPI 3.1.0 (`openapi.yaml` and `openapi.json`) + APIMatic SDK configuration (`apimatic.json`)
- **Backend Core:** FastAPI + Uvicorn + Python 3.13 + Pydantic v2
- **Persistence:** SQLite WAL Mode (`a2a_commerce.db`) with 5000ms busy timeout

---

## 6. License

MIT License &mdash; Copyright &copy; 2026 AP2 Autonomous Commerce Authors.
