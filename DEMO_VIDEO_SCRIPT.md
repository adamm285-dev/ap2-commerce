# AP2 Autonomous Commerce — Official Hackathon Demo Video Script & Screen Layout Guide

> **Duration:** 2 minutes 58.5 seconds (`178.5s`, ~3-Minute Detailed Walkthrough)  
> **Target Event:** PayPal AI Hackathon 2026  
> **Live Demo URL:** `https://ap2-commerce.fieldsmith.pro/`  
> **Final Video File:** `media/hackathon_demo/AP2_Autonomous_Commerce_Demo_2Min.mp4` (`1920x1080` @ 30fps, H.264 + 24kHz AAC)  
> **Narration Model:** Single-pass `gemini-3.8-flash-tts` studio voice (`Achird`, pure `1.0x` natural cadence + `48 kHz` stereo `-1.9 dBFS` true-peak mastering via `scripts/generate_hackathon_narration.py`)  
> **Structure:** 5 Detailed Acts covering all 6 prize tracks + live terminal proof so judges see the complete 4-station 3D animations, the interactive operations deck, the populated 4-step AP2 Execution Trace, and the real cryptographic/test execution underneath.

---

## 🖥️ Screen Layout & Two-Scene Flow (`1920x1080`)

```text
+-----------------------------------------------------------------------------------+
| SCENE A (0:00 - 2:24) — FULL-SCREEN BROWSER (1920x1080, 100% Zoom)                |
| URL: https://ap2-commerce.fieldsmith.pro/                                         |
|                                                                                   |
|  [AP2 Seller Operations Deck]   [3D Story | Setup | Dashboard | Workloads | MCP]  |
|                                 [Set My Limits (Trusted Surface)] [Simulate]      |
|  +--------------------------------------+--------------------------------------+  |
|  | Left Pane (on Setup tab):            | Right Pane (built-in split screen):  |  |
|  | Buyer Agent / 4-Step Setup /         | Live Protocol Inspector (4-step      |  |
|  | Anti-Tamper Verifier / API Onboard   | AP2 Execution Trace + SD-JWT frames) |  |
|  +--------------------------------------+--------------------------------------+  |
+-----------------------------------------------------------------------------------+

                            |||  Switch at 2:24  |||

+-----------------------------------------------------------------------------------+
| SCENE B (2:24 - 2:58.5) — SPLIT TERMINAL PROOF (1920x1080)                        |
|                                                                                   |
|  +--------------------------------------+--------------------------------------+  |
|  | LEFT 52%: Judge Audit Harness        | RIGHT 48%: CLI Buyer + 792 Pytest    |  |
|  |                                      |                                      |  |
|  | > python scripts/judge_audit_harness.py | > python -m backend.agents.llm_buyer_agent |
|  |   [CHECK 1..9] 9/9 CHECKS PASSED     |     --budget 60 --tier ap2-gateway   |  |
|  |   (100% GREEN) in 0.42s              |     --mint-owner-limits              |  |
|  |                                      |   STEP 1..6: COUNTER-OFFER PURCHASED |  |
|  |                                      | > pytest backend/tests -q -n 4       |  |
|  |                                      |   792 passed, 9 skipped in 66.25s    |  |
|  +--------------------------------------+--------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 🎬 Master Timing & Click-by-Click Storyboard (2:58.5 / 178.5s)

| Time | Act / Theme | Exact Screen Action | Voiceover Narration (`gemini-3.8-flash-tts`, `1.0x` Native Speed) | Prize Track Highlight |
| :--- | :--- | :--- | :--- | :--- |
| **0:00 - 0:46** | **Act 1: Trusted Surface Minting & Full 4-Station 3D Story** | Open **`Set My Limits (Trusted Surface)`** first (`0:02`), check **Human Intent Confirmation**, click **`Sign & Mint Open Mandates`** (`$60/mo` cap, `mandate.checkout.open.1` & `mandate.payment.open.1`), and click **`Forward Signed Open Mandates to AI Buyer Agent →`** (`0:13`). On the **`3D Story`** stage, click **`▶️ 1. Watch AI Bargain & Buy ($60 → $49.99)`** (`0:14–0:31`) so all 4 stations animate to completion (`Smart Counter-Offer Approved`), then click **`🛑 2. Simulate Rogue AI Attack ($200 Lie)`** (`0:31–0:46`) so Station 3 blocks the attack (`BLOCKED BEFORE SIGNING — HTTP 401`). | *"When an autonomous AI agent buys cloud compute on your behalf, handing your private payment keys to a large language model is a critical security failure. A single prompt injection or hallucinated price can drain your treasury before a human ever notices. AP2 Autonomous Commerce solves this on PayPal Subscriptions using Google's Agent Payments Protocol, AP2 version zero point two, now stewarded by the FIDO Alliance. We start on the Trusted Surface, where the human owner sets a strict sixty-dollar monthly ceiling, confirms human intent, and signs open checkout and payment mandates in an isolated hardware vault. Back on the three-D pipeline stage, watch what happens when our AI buyer requests a seventy-nine ninety-nine AI Gateway that exceeds our sixty-dollar rule: the seller automatically negotiates a forty-nine ninety-nine Batch Worker counter-offer, the isolated wallet verifies the math, and the server rack lights up green. And when a compromised agent tries to sneak through a two-hundred-dollar rogue charge, the hardware vault blocks the request before signing and locks down the rack."* | **Best Use of Agentic Commerce ($5,000)** |
| **0:46 - 1:24** | **Act 2: Setup Copilot, Populated 4-Step AP2 Execution Trace & Anti-Tamper** | Switch directly to **`Setup`** (`0:46`). Click **`Approve & Execute ($79.99/mo via PayPal)`** (`0:49`) to execute the live autonomous A2A cycle. Switch the right pane to **`AP2 Execution Trace`** (`0:54–1:11`) showing `● Step 4/4 Complete` and all 4 green trace cards (`1. Programmatic Spending Mandate Verification`, `2. PayPal Delegated Subscription Token`, `3. Dedicated Worker Node Allocation`, `4. Zapier MCP & Enterprise ERP Sync`). At `1:11`, switch to **`Anti-Tamper Verifier`** (`401 Signature Mismatch: Budget Policy Violated`). | *"Switching to our interactive Setup console, the buyer agent acts purely as an untrusted courier over the Model Context Protocol. When we approve a seventy-nine ninety-nine PayPal subscription under a one-hundred-dollar mandate, the right-hand inspector records the complete four-step AP2 execution trace: verifying the programmatic spending mandate, minting the delegated PayPal subscription token, allocating the dedicated worker node, and syncing the enterprise ledger. Every recurring renewal webhook is re-verified against the owner's original mandate with advance PayPal cancellation if a limit expires. And inside the Anti-Tamper Verifier, inflating the signed price by even a single cent triggers an immediate HTTP 401 cryptographic signature mismatch."* | **Best Use of PayPal + AI ($5,000)** |
| **1:24 - 1:58** | **Act 3: AG Studio v3 Fleet Ledger & Bryntum Workload Scheduler** | Switch to **`Dashboard`** (`1:24`). Toggle **View / Edit** mode in **AG Studio v3**, open a column filter, and inspect the live telemetry (`1:24–1:42`). At `1:42`, switch to **`Workloads`** (**Bryntum Sponsor** view) and click **`Provision Pending Node`** (`1:49`) to watch `Node-01` transition in place from amber `AWAITING PAYPAL` to emerald `● Node-01 Active ($79.99)` across the `$1,219.87/mo` fleet. | *"In our operations deck, AG Studio version three and AG Grid power the live enterprise fleet ledger, giving finance and infrastructure operators instant View and Edit modes, multi-column filtering, and cryptographic receipt auditing across all fourteen active mandates totaling twelve hundred nineteen dollars and eighty-seven cents in monthly recurring revenue. Moving to the Workloads tab, Bryntum Scheduler maps regional compute capacity across five enclave clusters. The moment PayPal confirms subscription settlement, provisioning the pending node transitions the workload allocation bar in place from amber awaiting payment to active emerald green."* | **AG Grid / AG Studio ($5,000)** &<br/>**Bryntum ($1,000)** |
| **1:58 - 2:24** | **Act 4: Zapier MCP QuickBooks GL 6300 Sync & APIMatic SDKs** | Switch to **`MCP`** (`1:58`). Click **`Run Autonomous AP2 Onboarding Chain`** (`2:01`) and scroll down (`2:08`) to show the **QuickBooks Online v3 (GL Account 6300)** JSON payload and HMAC-SHA256 signed CloudEvents envelope (`2:08–2:18`). At `2:18`, switch back to **`Setup`** -> **`API & SDKs`** to display the 48-path OpenAPI 3.1 contract and APIMatic multi-language SDK portal. | *"Next, on the MCP back-office tab, running our autonomous onboarding chain dispatches an HMAC-SHA256 signed CloudEvents envelope through Zapier MCP directly into QuickBooks Online version three, mapping every compute charge to General Ledger Account 6300 while scheduling automated node health checks. And in our API and SDK portal, a forty-eight-path OpenAPI three point one specification and APIMatic configuration generate type-safe SDKs for self-service buyer key enrollment."* | **Zapier / Back-Office** &<br/>**APIMatic ($1,000)** |
| **2:24 - 2:58.5** | **Act 5: Split-Screen Terminal Proof (9/9 Judge Audit + 792 Automated Tests)** | Switch to **Scene B (Full-Screen Split Terminal)** (`2:24–2:58.5`). Left pane displays `python scripts/judge_audit_harness.py` (`9/9 CHECKS PASSED (100% GREEN) in 0.42s`). Right pane displays `python -m backend.agents.llm_buyer_agent --budget 60 --tier ap2-gateway --mint-owner-limits` (`STEP 1 -> STEP 6: PURCHASED!`) and `pytest backend/tests -q -n 4` (`792 passed, 9 skipped`). | *"Finally, every claim in this platform is empirically verifiable from the command line. Running our one-click Judge Audit Harness validates all nine cryptographic and operational invariants in under one second, while our standalone CLI buyer agent negotiates and signs a live counter-offer end to end, backed by seven hundred ninety-two passing automated tests including all one hundred eighty-eight upstream Google AP2 conformance tests. That is AP2 Autonomous Commerce."* | **Empirical Proof & Security Architecture** |

---

## 🎙️ Complete Single-Pass Narration Transcript (`scripts/generate_hackathon_narration.py`)

```text
When an autonomous AI agent buys cloud compute on your behalf, handing your private payment keys to a large language model is a critical security failure. A single prompt injection or hallucinated price can drain your treasury before a human ever notices. AP2 Autonomous Commerce solves this on PayPal Subscriptions using Google's Agent Payments Protocol, AP2 version zero point two, now stewarded by the FIDO Alliance. We start on the Trusted Surface, where the human owner sets a strict sixty-dollar monthly ceiling, confirms human intent, and signs open checkout and payment mandates in an isolated hardware vault. Back on the three-D pipeline stage, watch what happens when our AI buyer requests a seventy-nine ninety-nine AI Gateway that exceeds our sixty-dollar rule: the seller automatically negotiates a forty-nine ninety-nine Batch Worker counter-offer, the isolated wallet verifies the math, and the server rack lights up green. And when a compromised agent tries to sneak through a two-hundred-dollar rogue charge, the hardware vault blocks the request before signing and locks down the rack.

Switching to our interactive Setup console, the buyer agent acts purely as an untrusted courier over the Model Context Protocol. When we approve a seventy-nine ninety-nine PayPal subscription under a one-hundred-dollar mandate, the right-hand inspector records the complete four-step AP2 execution trace: verifying the programmatic spending mandate, minting the delegated PayPal subscription token, allocating the dedicated worker node, and syncing the enterprise ledger. Every recurring renewal webhook is re-verified against the owner's original mandate with advance PayPal cancellation if a limit expires. And inside the Anti-Tamper Verifier, inflating the signed price by even a single cent triggers an immediate HTTP 401 cryptographic signature mismatch.

In our operations deck, AG Studio version three and AG Grid power the live enterprise fleet ledger, giving finance and infrastructure operators instant View and Edit modes, multi-column filtering, and cryptographic receipt auditing across all fourteen active mandates totaling twelve hundred nineteen dollars and eighty-seven cents in monthly recurring revenue. Moving to the Workloads tab, Bryntum Scheduler maps regional compute capacity across five enclave clusters. The moment PayPal confirms subscription settlement, provisioning the pending node transitions the workload allocation bar in place from amber awaiting payment to active emerald green.

Next, on the MCP back-office tab, running our autonomous onboarding chain dispatches an HMAC-SHA256 signed CloudEvents envelope through Zapier MCP directly into QuickBooks Online version three, mapping every compute charge to General Ledger Account 6300 while scheduling automated node health checks. And in our API and SDK portal, a forty-eight-path OpenAPI three point one specification and APIMatic configuration generate type-safe SDKs for self-service buyer key enrollment.

Finally, every claim in this platform is empirically verifiable from the command line. Running our one-click Judge Audit Harness validates all nine cryptographic and operational invariants in under one second, while our standalone CLI buyer agent negotiates and signs a live counter-offer end to end, backed by seven hundred ninety-two passing automated tests including all one hundred eighty-eight upstream Google AP2 conformance tests. That is AP2 Autonomous Commerce.
```
