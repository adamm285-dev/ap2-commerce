# AP2 Autonomous Commerce &mdash; Agent Payments Protocol Operations Deck

> **Autonomous Agentic Commerce & AP2 (Agent Payments Protocol) for Distributed AI Compute**  
> Built for the **PayPal AI Hackathon 2026** (\$67,500+ Prize Purse &bull; Targeting \$18,000+ Across 6 Sponsor Tracks)  
> Combining **PayPal Agentic Commerce & Vault**, **AG Studio v3.0.0 & AG Grid Community**, **Bryntum Scheduler**, **APIMatic**, and **Zapier MCP**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AG Studio: v3.0.0](https://img.shields.io/badge/AG%20Studio-v3.0.0-blue.svg)](https://www.ag-grid.com/studio/react/)
[![PayPal Agentic Commerce](https://img.shields.io/badge/PayPal-Agentic%20Commerce-003087.svg)](https://github.com/paypal/AI-Toolkit)
[![OpenAPI 3.1.0](https://img.shields.io/badge/OpenAPI-3.1.0-green.svg)](openapi.yaml)
[![Tests: 505 Passed](https://img.shields.io/badge/Tests-505%20Passed%20(100%25)-brightgreen.svg)](backend/tests/)
[![Judge Audit: 9/9 Passed](https://img.shields.io/badge/Judge%20Audit-9%2F9%20Passed%20(100%25)-brightgreen.svg)](scripts/judge_audit_harness.py)

---

## 🌐 System Endpoints & Interfaces

| Resource | Protocol / Location | Description |
| :--- | :--- | :--- |
| **Interactive Operations Deck** | React 19 + AG Studio + Bryntum UI (`/portal/`) | Full visual command center with live protocol inspector |
| **FastMCP Seller Server** | MCP 2024-11-05 JSON-RPC 2.0 (`/mcp`) | Model Context Protocol server exposing autonomous seller tools |
| **Live SSE Wire Stream** | Server-Sent Events (`/sse`) | Real-time JSON-RPC 2.0 packet inspector frames |
| **OpenAPI 3.1.0 Specification** | `openapi.yaml` & `openapi.json` | 33 typed endpoints covering negotiation, mandates, and vault |
| **Interactive API Documentation**| Swagger UI (`/docs`) | Interactive REST endpoint documentation and schema explorer |
| **Agent Discovery Card** | JSON Metadata (`/agents.json`) | Machine-readable A2A capability and discovery descriptor |

---

## ⚡ Quickstart for Judges

> **⚠️ Judge Evaluation Note:** Execute **`python scripts/judge_audit_harness.py`** as your primary evaluation command. It requires **zero external API keys or configuration**, runs in <0.2 seconds, and asserts all 9 protocol, cryptographic (Ed25519/HMAC-SHA256 dual mandates), and operational invariants directly.

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
# 505 passed, 6 skipped (live PayPal credentials optional)
```

### 3. Run Autonomous AI Buyer Agent CLI Simulation
Simulate an end-to-end LLM-driven buyer agent negotiating and provisioning a compute node under a spending mandate:
```bash
python -m backend.agents.llm_buyer_agent --budget 60 --tier ap2-gateway
```

---

## 1. Executive Summary & The Problem

Autonomous software agents and developer teams hit severe compute capacity bottlenecks. Procuring dedicated worker nodes or specialized AI service gateways still suffers from critical failure modes:
1. **Human Onboarding Friction:** Autonomous agents cannot interact with 15-field checkout forms, manual credit card typing, or human verification captchas.
2. **Uncontrolled Budget Risk:** Enterprise spending mandates require mathematically enforceable, tamper-proof budget caps before an agent can commit company funds.
3. **Downline Integration Overhead:** Once an infrastructure subscription is active, manual entry is required to log accounting expenses into ERP systems (e.g. QuickBooks Online).
4. **Identity & Accountability:** Anonymous autonomous agents create counterparty risk unless commitments are cryptographically anchored to verified business entities.

**AP2 Autonomous Commerce introduces an Agentic Commerce & AP2 Protocol Ecosystem:**
- **Autonomous Buyer Agent:** Evaluates pipeline telemetry and workload queues, verifies programmatic spending mandates (`maxMonthlyBudget <= $100/mo`), and autonomously negotiates with service providers over Model Context Protocol.
- **Autonomous Multi-Tier Counter-Offer Bargaining:** When the buyer's budget cap is below the standard asking price ($60 cap vs $79.99 Dedicated Gateway), the Seller Agent autonomously offers a scaled tier (*High-Throughput Batch Worker at $49.99/mo*) which the Buyer Agent verifies and signs autonomously.
- **Cryptographic Anti-Tamper Engine:** Validates RFC 8032 Ed25519 Intent & Cart Mandates with HMAC-SHA256 authorization proofs (`X-AP2-Signature`). Any byte-level alteration (such as inflating price by 1¢ or altering buyer identity) is immediately rejected with `401 Signature Mismatch: Budget Policy Violated`.
- **Self-Service Buyer Key Onboarding:** Enables third-party autonomous buyer agents to complete an asymmetric Ed25519 cryptographic challenge-response registration (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`).
- **Live SSE Wire Protocol Stream:** Streams raw JSON-RPC 2.0 frames (`initialize` &rarr; `tools/list` &rarr; `tools/call` &rarr; `vault/token`) with sub-millisecond timestamps directly into a live packet inspector.
- **Compute Node Provisioning:** Automatically provisions dedicated compute node endpoints (`batch-01`, `gateway-01`, `cluster-01`) with assigned workload task quotas (125, 450, or 1,200 tasks/month).
- **Bryntum Workload Timeline Scheduling:** Visualizes 24/7 compute node execution shifts and workload allocations across regional cluster zones.
- **Zapier MCP Downline Automation:** Automatically executes downline synchronization into QuickBooks Online (recording recurring subscription expenses mapped to General Ledger Account 6300) and operational monitoring systems.
- **AG Studio v3.0.0 & AG Grid Community Analytics:** High-density fleet ledger with floating column filters, interactive data refresh, and compute volume analytics reconciling $13,438.32 ARR GMV across 14 simulated compute nodes directly from SQLite WAL persistence.

---

## 2. Multi-Sponsor Architecture & Prize Alignments (\$18,000+ Purse)

| Sponsor Track | Prize | Implementation & Technology |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **\$5,000** | `@paypal/react-paypal-js`<br/>`@paypal/paypal-server-sdk` | Autonomous AP2 mandate negotiation, counter-offer bargaining, delegated subscription approvals, and Vault MIT settlement. |
| **Best Use of AG Grid / AG Studio** | **\$5,000** | `ag-studio-react`<br/>`ag-studio` (v3.0.0)<br/>AG Grid Community | High-density grid telemetry with floating column filters, live SQLite WAL data hydration, and dual View/Edit reporting modes reconciling \$13,438.32 ARR across 14 simulated nodes. |
| **Best Use of PayPal + AI** | **\$5,000** | FastMCP 2024-11-05 Server<br/>SSE Wire Stream Inspector | Streamable HTTP/SSE wire protocol inspector, autonomous multi-turn negotiation, and intelligent sub-budget counter-offer generation. |
| **Best Use of Bryntum** | **\$1,000** | `@bryntum/scheduler` 7.3.7 (Trial Build) | Regional workload dispatch calendar managing 24/7 compute node shifts with live in-place reactive status transitions (Orange &rarr; Green). |
| **Best Use of Zapier** | **\$1,000** | Zapier MCP Protocol Bridge<br/>CloudEvents v1.0 | Automated back-office execution syncing recurring PayPal expenses into QuickBooks Online (GL Account 6300) via Model Context Protocol. |
| **Best Use of APIMatic** | **\$1,000** | OpenAPI 3.1.0 Contract<br/>Ed25519 Challenge-Response | Production-grade OpenAPI specification with 33 endpoints (`openapi.yaml` and `openapi.json`), `apimatic.json` configuration for multi-language SDK compilation, and self-service buyer key onboarding. |

---

## 3. The 9 Judge Audit Verification Checks

1. **[CHECK 1] MCP JSON-RPC 2.0 Handshake:** Validates `initialize` and `tools/list` protocol handshake returning registered seller tools.
2. **[CHECK 2] Standard AP2 Negotiation:** Evaluates \$79.99/mo Service Gateway under \$100 budget cap with HMAC-SHA256 cryptographic authorization proof.
3. **[CHECK 3] Sub-Budget Counter-Offer Bargaining:** Generates scaled-down *Batch Worker* (\$49.99/mo) counter-offer when cap is \$60.00.
4. **[CHECK 4] Anti-Tamper Verification:** Proves 1-cent inflation tampering, entity name alteration, and budget breaches are strictly rejected.
5. **[CHECK 5] Compute Node Provisioning:** Validates subscription verification and compute node endpoint allocation (`batch-01`, `gateway-01`, `cluster-01`).
6. **[CHECK 6] Back-Office ERP Payloads:** Generates authentic QuickBooks Online v3 Purchase mapped to GL Account 6300.
7. **[CHECK 7] Financial Telemetry Reconciliation:** Reconciles 14 simulated subscriber lines, \$1,119.86/mo MRR, and \$13,438.32 ARR GMV to the penny.
8. **[CHECK 8] AG Studio & Bryntum Scheduling:** Hydrates 14 nodes from SQLite WAL and verifies 24/7 compute execution shifts.
9. **[CHECK 9] Dynamic Buyer Key Onboarding:** Generates 300s ephemeral Ed25519 challenge nonce, validates cryptographic signature, enrolls buyer key, and rejects forged signatures.

---

## 4. Technology Stack

- **Runtime & Build:** Node.js 22+ / 24 + Vite 8 + React 19 + TypeScript
- **Embedded Analytics:** AG Studio v3.0.0 (`ag-studio-react`, `ag-studio`, `ag-charts-enterprise`) + AG Grid Community with custom floating filters
- **Payments:** PayPal Subscriptions SDK (`@paypal/react-paypal-js`, `@paypal/paypal-server-sdk`) & PayPal Vault MIT
- **Workload Scheduling:** Bryntum Scheduler 7.3.7 (`@bryntum/scheduler` trial build)
- **API Specification:** OpenAPI 3.1.0 (`openapi.yaml` and `openapi.json`) + APIMatic SDK configuration (`apimatic.json`)
- **Backend Core:** FastAPI + Uvicorn + Python 3.13 + Pydantic v2
- **Persistence:** SQLite WAL Mode (`ap2_commerce.db`) with 5000ms busy timeout

---

## 5. License

MIT License &mdash; Copyright &copy; 2026 AP2 Autonomous Commerce Authors.
