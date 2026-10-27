# AP2 Autonomous Commerce — Official Hackathon Demo Video Script & Screen Layout Guide

> **Target Duration:** 2 minutes (120 seconds)  
> **Target Event:** PayPal AI Hackathon 2026  
> **Live Demo URL:** `https://ap2-commerce.fieldsmith.pro/`  
> **Resolution:** 1080p (`1920x1080` @ 60fps, 100% browser zoom)  
> **Structure:** 5 Acts covering all 6 prize tracks + live terminal proof so judges immediately see both the interactive operations deck and the real cryptographic/test execution underneath.

---

## 🖥️ Recommended Screen Layout During Recording

Judges penalize videos that look like static click-through mockups, and they also penalize videos where dense tables are squished into half a screen. Use a **Two-Workspace Switch (`Alt + Tab`)** at `1920x1080`:

```text
+-----------------------------------------------------------------------------------+
| SCENE A (0:00 - 1:35) — FULL-SCREEN BROWSER (1920x1080, 100% Zoom, No Bookmarks)  |
| URL: https://ap2-commerce.fieldsmith.pro/                                         |
|                                                                                   |
|  [AP2 Seller Operations Deck]   [3D Story | Setup | Dashboard | Workloads | MCP]  |
|                                 [Set My Limits (Trusted Surface)] [Simulate]      |
|  +--------------------------------------+--------------------------------------+  |
|  | Left Pane (on Setup tab):            | Right Pane (built-in split screen):  |  |
|  | Buyer Agent / 5-Step Setup /         | Live Protocol Inspector (JSON-RPC    |  |
|  | Anti-Tamper Verifier / API Onboard   | 2.0 MCP + AP2 ES256 SD-JWT frames)   |  |
|  +--------------------------------------+--------------------------------------+  |
+-----------------------------------------------------------------------------------+

                            |||  Alt + Tab at 1:35  |||

+-----------------------------------------------------------------------------------+
| SCENE B (1:35 - 2:00) — SPLIT TERMINAL + CODE / CONFIG (1920x1080, 16pt Font)     |
|                                                                                   |
|  +--------------------------------------+--------------------------------------+  |
|  | LEFT 60%: PowerShell / Terminal      | RIGHT 40%: VS Code / Terminal 2      |  |
|  |                                      |                                      |  |
|  | > python scripts/judge_audit_harness.py | > python -m backend.agents.llm_buyer_agent |
|  |   [CHECK 1..9] 9/9 CHECKS PASSED     |     --budget 60 --tier ap2-gateway   |  |
|  |                                      |     --mint-owner-limits              |  |
|  | > pytest backend/tests -q -n 4       |   STEP 1: REQUESTED -> STEP 2: OVER  |  |
|  |   792 passed, 9 skipped in ~65s      |   LIMIT -> STEP 3: COUNTER-OFFER ->  |  |
|  |                                      |   STEP 4..6: SIGNED & PURCHASED      |  |
|  +--------------------------------------+--------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

### Why This Layout Works Best
1. **No Squished Tables (0:00 – 1:35):** The **`Setup`** tab already has a built-in 50/50 split screen (Agent Controls on the left, **Live Protocol Inspector** on the right), while **`Dashboard`** (AG Studio v3) and **`Workloads`** (Bryntum Scheduler) get the full `1920x1080` width so every column, chart, and timeline bar looks crisp.
2. **Undeniable Technical Proof (1:35 – 2:00):** Switching to the dual terminal at 1:35 proves in seconds that the backend is running real Google AP2 v0.2 ES256 SD-JWT cryptography (`9/9 Judge Audit Checks` in ~1 second + `792 passed` tests + the standalone CLI buyer agent negotiating a counter-offer).

---

## 🎬 Master Timing & Click-by-Click Storyboard

| Time | Act / Theme | Exact Screen Action (`https://ap2-commerce.fieldsmith.pro/`) | Voiceover Narration (Spoken Word) | Prize Track Highlight |
| :--- | :--- | :--- | :--- | :--- |
| **0:00 - 0:22** | **Act 1: The Untrusted Courier Problem & 3D Pipeline** | Start on the **`3D Story`** tab (`5-Station 3D Pipeline`). Briefly hover over the 5 stations, then click **`Set My Limits (Trusted Surface)`** in the top-right header. Show the human owner signing `$60/mo` (`mandate.checkout.open.1` & `mandate.payment.open.1`) ES256 SD-JWT limits. | *"When an autonomous AI agent buys cloud compute, giving the LLM your private payment keys is a critical security risk — a single prompt injection can drain your account. AP2 Autonomous Commerce solves this on PayPal Subscriptions using Google's Agent Payments Protocol, AP2 v0.2, now under the FIDO Alliance. First, the human owner signs cryptographic spending limits on a Trusted Surface while keeping private keys inside an isolated Buyer Wallet MCP server."* | **Best Use of Agentic Commerce ($5,000)** |
| **0:22 - 0:52** | **Act 2: Autonomous MCP Negotiation, PayPal Settlement & Anti-Tamper** | Click the **`Setup`** tab. Click **"Execute Live Test Cycle"** (or **"Approve ($79.99/mo)"**). Watch the right-hand **Live Protocol Inspector** stream the JSON-RPC 2.0 MCP handshake, ES256 SD-JWT mandate verification, PayPal Subscription settlement, and node provisioning. Then click Step 3 (**Anti-Tamper**) and toggle **+1¢ Price Inflation** to show instantaneous cryptographic rejection. | *"Here on the Setup console, our buyer agent acts as an untrusted courier over Model Context Protocol. When a tier exceeds a $60 cap, the seller counter-offers a $49.99 Batch Worker; under a $100 cap, it settles the $79.99 AI Service Gateway via PayPal Subscriptions and the PayPal Agent Toolkit. Every renewal webhook is re-verified against the owner's mandate with advance cancellation, and even a one-cent price tamper is cryptographically rejected."* | **Best Use of PayPal + AI ($5,000)** |
| **0:52 - 1:18** | **Act 3: AG Studio v3 Fleet Ledger & Bryntum Workload Scheduler** | Click the **`Dashboard`** tab. Toggle **View / Edit** mode in **AG Studio v3**, filter a column, and highlight the `$1,219.87/mo` MRR (`$14,638.44 ARR`) across the seeded fleet. Next, click the **`Workloads`** tab (**Bryntum Sponsor** view) and click **"Provision Pending Node"** to watch the amber `AWAITING PAYPAL` bar turn vibrant green (`ACTIVE`) in place. | *"In our operations deck, AG Studio version 3 and AG Grid power the fleet ledger, letting operators switch between View and Edit modes, filter live telemetry, and audit mandate receipts across 14 nodes. Switching to Workloads, Bryntum Scheduler maps regional compute shifts — and as soon as PayPal confirms settlement, the pending compute allocation transitions in place from amber awaiting payment to active."* | **AG Grid / AG Studio ($5,000)** &<br/>**Bryntum ($1,000)** |
| **1:18 - 1:36** | **Act 4: Zapier MCP Back-Office Sync & APIMatic Onboarding** | Click the **`MCP`** tab. Click **"Run Autonomous AP2 Onboarding Chain"**. Show the green checkmarks and expand the **QuickBooks Online v3 GL Account 6300** JSON payload and HMAC-SHA256 signed CloudEvents envelope. Briefly flash Step 5 (**API & SDKs / APIMatic**) on **`Setup`**. | *"Once settled, our Zapier MCP export dispatches an HMAC-signed QuickBooks Online v3 expense payload mapped to General Ledger Account 6300 and schedules node health checks automatically — while our 48-path OpenAPI 3.1 contract and APIMatic configuration generate multi-language SDKs for self-service buyer key enrollment."* | **Zapier / Back-Office** &<br/>**APIMatic ($1,000)** |
| **1:36 - 2:00** | **Act 5: Live Terminal Proof (9/9 Judge Audit + 792 Tests)** | Press `Alt + Tab` to **Scene B (Split Terminal)**. On the left terminal, run `python scripts/judge_audit_harness.py` (finishes in 1 second showing `9/9 CHECKS PASSED`). Point to the right terminal showing `python -m backend.agents.llm_buyer_agent --budget 60 --tier ap2-gateway --mint-owner-limits` (`STEP 1 -> STEP 6: PURCHASED`) and `792 passed` in pytest. | *"Everything is empirically verifiable in one command. Running our Judge Audit Harness verifies all 9 cryptographic and operational invariants in under one second, backed by 792 passing automated tests — including all 188 upstream Google AP2 SDK conformance tests and a transparent 22-entry mock ledger. That's AP2 Autonomous Commerce."* | **Empirical Proof & Security Architecture** |

---

## 🎙️ Clean Voiceover Script (~325 Words @ 160 wpm = 2:00)

```text
[0:00 - Act 1: The Untrusted Courier Problem]
When an autonomous AI agent buys cloud compute, giving the LLM your private payment keys 
is a critical security risk — a single prompt injection can drain your account. 
AP2 Autonomous Commerce solves this on PayPal Subscriptions using Google's Agent Payments 
Protocol, AP2 v0.2, now under the FIDO Alliance. First, the human owner signs cryptographic 
spending limits on a Trusted Surface while keeping private keys inside an isolated Buyer 
Wallet MCP server.

[0:22 - Act 2: Autonomous Negotiation, PayPal Settlement & Anti-Tamper]
Here on the Setup console, our buyer agent acts as an untrusted courier over Model Context 
Protocol. When a tier exceeds a $60 cap, the seller counter-offers a $49.99 Batch Worker; 
under a $100 cap, it settles the $79.99 AI Service Gateway via PayPal Subscriptions and the 
PayPal Agent Toolkit. Every renewal webhook is re-verified against the owner's mandate with 
advance cancellation, and even a one-cent price tamper is cryptographically rejected.

[0:52 - Act 3: AG Studio v3 Fleet Ledger & Bryntum Scheduler]
In our operations deck, AG Studio version 3 and AG Grid power the fleet ledger, letting 
operators switch between View and Edit modes, filter live telemetry, and audit mandate 
receipts across 14 nodes. Switching to Workloads, Bryntum Scheduler maps regional compute 
shifts — and as soon as PayPal confirms settlement, the pending compute allocation 
transitions in place from amber awaiting payment to active.

[1:18 - Act 4: Zapier QuickBooks GL 6300 & APIMatic SDKs]
Once settled, our Zapier MCP export dispatches an HMAC-signed QuickBooks Online v3 expense 
payload mapped to General Ledger Account 6300 and schedules node health checks automatically — 
while our 48-path OpenAPI 3.1 contract and APIMatic configuration generate multi-language SDKs 
for self-service buyer key enrollment.

[1:36 - Act 5: One-Click Judge Audit & 792 Automated Tests]
Everything is empirically verifiable in one command. Running our Judge Audit Harness verifies 
all 9 cryptographic and operational invariants in under one second, backed by 792 passing 
automated tests — including all 188 upstream Google AP2 SDK conformance tests and a 
transparent 22-entry mock ledger. That's AP2 Autonomous Commerce.
```

---

## ✅ Pre-Recording Prep Checklist (Takes 60 Seconds)

1. **Browser Window (Scene A):**
   - Open `https://ap2-commerce.fieldsmith.pro/` in Chrome or Edge.
   - Press `Ctrl + Shift + B` to hide the bookmarks bar, set zoom to `100%`, and press `F11` (or maximize at `1920x1080`).
   - Start on the **`3D Story`** tab so the opening visual is immediately eye-catching.

2. **Split Terminal Window (Scene B — Ready Behind Browser via `Alt + Tab`):**
   - **Right Pane (Pre-run before recording so output is already visible on screen):**
     ```powershell
     python -m pytest backend/tests -q -n 4
     python -m backend.agents.llm_buyer_agent --budget 60 --tier ap2-gateway --mint-owner-limits
     ```
   - **Left Pane (Staged and ready to press `Enter` live at `1:36`):**
     ```powershell
     python scripts/judge_audit_harness.py
     ```
