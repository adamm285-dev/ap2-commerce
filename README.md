# FieldSmith Pro &mdash; Autonomous A2A Commerce Portal & Multi-Agent Operations Deck

> **Autonomous Agent-to-Agent (A2A) Commerce for Solo Tradespeople**  
> Built for the **PayPal AI Hackathon 2026** (\$67,500+ Prize Purse &bull; Targeting \$17,000+ Across 5 Sponsor Tracks)  
> Combining **PayPal Agentic Commerce**, **AG Studio v3.0.0 & AG Grid Community**, **Bryntum Scheduler**, **APIMatic**, and **Zapier MCP**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AG Studio: v3.0.0](https://img.shields.io/badge/AG%20Studio-v3.0.0-blue.svg)](https://www.ag-grid.com/studio/react/)
[![PayPal Agentic Commerce](https://img.shields.io/badge/PayPal-Agentic%20Commerce-003087.svg)](https://github.com/paypal/AI-Toolkit)
[![Live Cloud Portal](https://img.shields.io/badge/Cloud%20Portal-Online%20(HTTP%20200)-success.svg)](https://api.fieldsmith.pro/portal/)
[![OpenAPI 3.1.0](https://img.shields.io/badge/OpenAPI-3.1.0-green.svg)](openapi.yaml)
[![Tests: 138 Passed](https://img.shields.io/badge/Tests-138%20Passed%20(100%25)-brightgreen.svg)](backend/tests/)
[![Judge Audit: 9/9 Passed](https://img.shields.io/badge/Judge%20Audit-9%2F9%20Passed%20(100%25)-brightgreen.svg)](scripts/judge_audit_harness.py)

---

## 🌐 Live Cloud Endpoints

| Resource | URL | Protocol / Format |
| :--- | :--- | :--- |
| **Interactive Web Portal** | [https://api.fieldsmith.pro/portal/](https://api.fieldsmith.pro/portal/) | React 19 + AG Studio + Bryntum UI |
| **FastMCP Seller Server** | `https://api.fieldsmith.pro/a2a/mcp` | MCP 2024-11-05 JSON-RPC 2.0 (A2A Hackathon Seller Protocol; core contractor signups at `/mcp`) |
| **Live SSE Wire Stream** | `https://api.fieldsmith.pro/sse` | Server-Sent Events (SSE) Wire Frames |
| **OpenAPI 3.1.0 Specification** | [https://api.fieldsmith.pro/openapi.json](https://api.fieldsmith.pro/openapi.json) | OpenAPI 3.1.0 JSON (33 Endpoints) |
| **Interactive API Documentation**| [https://api.fieldsmith.pro/docs](https://api.fieldsmith.pro/docs) | Swagger UI |
| **Agent Discovery Card** | [https://api.fieldsmith.pro/agents.json](https://api.fieldsmith.pro/agents.json) | Machine-Readable Agent Metadata |

---

## ⚡ Quickstart for Judges

> **⚠️ Judge Evaluation Note:** Please execute **`python scripts/judge_audit_harness.py --remote`** as your primary evaluation command. It requires **zero API keys or configuration**, runs instantly, and tests all 9 protocol, cryptographic (Ed25519/HMAC-SHA256), and operational invariants directly against the live public production API (`https://api.fieldsmith.pro`). The concurrent multi-agent stress test (`scripts/live_cloud_stress_test.py`) is designed for administrative load verification and requires an administrative key (`ADMIN_API_KEY`) for simulated sandbox buyer approval.

### 1. One-Click Live Cloud Audit (Recommended for Judges)
Verify all 9 critical operational and cryptographic checks against the live production deployment:
```bash
python scripts/judge_audit_harness.py --remote
```

### 2. Concurrent Multi-Agent Stress Test (Internal & Load Verification)
Launch 5 parallel autonomous buyer agents stressing the live cloud deployment simultaneously (requires admin key for Scenario 1 approval simulation):
```bash
python scripts/live_cloud_stress_test.py
```

### 3. Local In-Memory Audit (Zero Dependencies)
Run the exact same 9-step audit locally via in-memory mock client:
```bash
python scripts/judge_audit_harness.py
```

### 4. Run the Full Automated Test Suite
```bash
python -m pytest backend/tests/ -v
# 138/138 tests passing (100% green)
```

---

## 1. Executive Summary & The Problem

Solo trade contractors (flooring, plumbing, roofing, emergency towing) lose an estimated **\$6,200/month in revenue** from missed calls while on jobsites, operating machinery, or driving. Traditional SaaS platforms fail them because:
1. **Friction:** Solo tradesmen cannot afford the time for 15-field web forms, manual credit card inputs, and subscription onboarding wizards.
2. **Deposit & Calendar Friction:** Customers who call expect an immediate estimate, but contractors get double-booked without an upfront mobilization deposit.
3. **Downline Admin Fatigue:** Once a job is booked, contractors spend hours every night manually creating Jobber quotes, QuickBooks Online invoices, and calendar appointments.
4. **Telecom Robocall Abuse & KYC:** Rogue AI voice bots create statutory liability (TCPA / FCC compliance) if agents are provisioned anonymously without verified KYC identity.

**FieldSmith Pro introduces an Autonomous Agent-to-Agent (A2A) Commerce Ecosystem:**
- **Autonomous Buyer Agent:** Evaluates local telephony call logs, identifies uncaptured customer revenue, validates the contractor's programmatic spending mandate (`maxMonthlyBudget <= \$100/mo`), and autonomously negotiates with service providers.
- **Autonomous Multi-Tier Counter-Offer Bargaining:** When the contractor's budget cap is below the standard asking price (\$60 cap vs \$79.99 plan), the Seller Agent autonomously offers a scaled-down tier (*Solo Starter at \$49.99/mo*) which the Buyer Agent signs autonomously.
- **Cryptographic Anti-Tamper Engine:** Validates 64-character HMAC-SHA256 signatures (`X-FieldSmith-Signature`). Any byte-level alteration (such as inflating price by 1¢) is immediately intercepted and rejected with `401 Signature Mismatch: Budget Policy Violated`.
- **Self-Service Buyer Key Onboarding:** Enables third-party autonomous buyer agents to complete an asymmetric Ed25519 cryptographic challenge-response registration (`GET /api/agent/keys/challenge` & `POST /api/agent/keys/register`) with US contractor email gating.
- **Live SSE Wire Protocol Stream:** Streams raw JSON-RPC 2.0 frames (`initialize` &rarr; `tools/list` &rarr; `tools/call` &rarr; `vault/token`) with sub-millisecond timestamps directly into a live packet inspector.
- **Verified KYC Telecom Provisioning:** Anchors the verified PayPal subscriber identity directly to local Telnyx 10DLC DID line allocation (`+1 863-267-8902`) with automated contiguous LATA failover (e.g. 863 Lakeland &rarr; 813 Tampa).
- **Bryntum Territory Dispatch Scheduling:** Visualizes 24/7 AI voice screener shifts and locks 75-minute estimate windows across 4 territory zones upon verified PayPal customer deposits (evaluated with Bryntum Dispatch Scheduler trial build).
- **Zapier MCP Downline Automation:** Automatically executes a 3-step action chain into Jobber (GraphQL v2 client mutation), QuickBooks Online (API v3 purchase expense mapped to GL Account 6300), and Google Calendar (dispatch appointment).
- **AG Studio v3.0.0 & AG Grid Community Analytics:** Full-fidelity fleet ledger with floating column filters, interactive data refresh, and trade impact analytics reconciling \$13,438.32 ARR GMV across 14 simulated subscriber lines directly from SQLite WAL persistence.

---

## 2. Multi-Sponsor Architecture & Prize Alignments (\$17,000+ Purse)

| Sponsor Track | Prize | Implementation & Technology |
| :--- | :--- | :--- |
| **Best Use of Agentic Commerce** | **\$5,000** | `@paypal/react-paypal-js`<br/>`@paypal/paypal-server-sdk` | Autonomous A2A negotiation, counter-offer bargaining, delegated subscription approvals, and Vault MIT overage settlement. |
| **Best Use of AG Grid / AG Studio** | **\$5,000** | `ag-studio-react`<br/>`ag-studio` (v3.0.0)<br/>AG Grid Community | High-density grid telemetry with floating column filters, grouped bar charts, live SQLite WAL data hydration, and dual View/Edit reporting modes reconciling \$13,438.32 ARR across 14 simulated lines. |
| **Best Use of PayPal + AI** | **\$5,000** | FastMCP 2024-11-05 Server<br/>SSE Wire Stream Inspector | Streamable HTTP/SSE wire protocol inspector, live cloud deployment (`https://api.fieldsmith.pro`), US-domestic NANP gating, and intelligent autonomous counter-offer generation. |
| **Best Use of Bryntum** | **\$1,000** | `@bryntum/scheduler` 7.3.7 (Trial Build) | 4-zone territory dispatch calendar managing 24/7 AI voice screener shifts, 75-minute customer estimate window booking, and live in-place reactive color mutations (Orange &rarr; Green &rarr; Blue). |
| **Best Use of APIMatic** | **\$1,000** | OpenAPI 3.1.0 Contract<br/>Ed25519 Challenge-Response | Production-grade OpenAPI specification with 33 endpoints (`openapi.yaml` and `openapi.json`), `apimatic.json` configuration for multi-language SDK compilation (Python, TypeScript, Go), and self-service buyer key onboarding. |

---

## 3. The 9 Judge Audit Verification Checks

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

## 4. Technology Stack

- **Runtime & Build:** Node.js 22+ / 24 + Vite 8 + React 19 + TypeScript
- **Embedded Analytics:** AG Studio v3.0.0 (`ag-studio-react`, `ag-studio`, `ag-charts-enterprise`) + AG Grid Community with custom floating filters
- **Payments:** PayPal Subscriptions SDK (`@paypal/react-paypal-js`, `@paypal/paypal-server-sdk`) & PayPal Vault MIT
- **Dispatch Scheduling:** Bryntum Scheduler 7.3.7 (`@bryntum/scheduler` trial build)
- **API Specification:** OpenAPI 3.1.0 (`openapi.yaml` and `openapi.json`) + APIMatic SDK configuration (`apimatic.json`)
- **Backend Core:** FastAPI + Uvicorn + Python 3.13 + Pydantic v2
- **Persistence:** SQLite WAL Mode (`a2a_database.db`) with 5000ms busy timeout
- **Cloud Deployment:** Google Cloud Platform VM (`35.231.247.43`) + Caddy Reverse Proxy + Cloudflare TLS (`api.fieldsmith.pro`)

---

## 5. License

MIT License &mdash; Copyright &copy; 2026 Floorsmith LLC.
