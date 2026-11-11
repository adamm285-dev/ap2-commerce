# AP2 Autonomous Commerce - Official Hackathon Demo Video Script & Screen Layout Guide

> **Duration:** 2 minutes 52.4 seconds (`172.42s`, ~3-Minute Detailed Walkthrough)  
> **Target Event:** PayPal AI Hackathon 2026  
> **Live Demo URL:** `https://ap2-commerce.fieldsmith.pro/`  
> **Final Video File:** `media/hackathon_demo/AP2_Autonomous_Commerce_Demo_2Min.mp4` (`1920x1080` @ 30fps, H.264 + 48kHz AAC)  
> **Narration Model:** Single-pass `gemini-3.8-flash-tts` studio voice (`Achird`, pure `1.0x` natural cadence + `48 kHz` stereo `-1.9 dBFS` true-peak mastering via `scripts/generate_hackathon_narration.py`)  
> **Structure:** 5 Detailed Acts covering all 6 prize tracks + live terminal proof so judges see the architectural trust boundaries, the complete 4-station 3D animations, the interactive operations deck, the populated 4-step AP2 Execution Trace, and the real cryptographic/test execution underneath.

---

## Screen Layout & Two-Scene Flow (`1920x1080`)

```text
+-----------------------------------------------------------------------------------+
| SCENE A (0:00 - 2:22.1) - ARCHITECTURE INTRO + FULL-SCREEN BROWSER (1920x1080)    |
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

                            |||  Switch at 2:22.1  |||

+-----------------------------------------------------------------------------------+
| SCENE B (2:22.1 - 2:52.4) - JUDGE VERIFICATION SUITE TERMINAL OVERLAY (1920x1080) |
|                                                                                   |
|  > python -m pytest backend/tests -q -n 4                                         |
|    792 passed, 9 skipped in 58.81s (188 upstream AP2 conformance + regressions)   |
|  > python scripts/check_mocks.py                                                  |
|    docs/MOCKS.md matches the MOCK markers in the code.                            |
+-----------------------------------------------------------------------------------+
```

---

## Master Timing & Click-by-Click Storyboard (2:52.4 / 172.42s)

| Time | Act / Theme | Exact Screen Action | Voiceover Narration (`1.0x` Native Speed) | Prize Track Highlight |
| :--- | :--- | :--- | :--- | :--- |
| **0:00 - 0:45.8** | **Act 1: Architecture Intro, Trusted Surface Minting & Full 4-Station 3D Story** | Show **The Security Threat: Why LLMs Must Never Hold Private Keys** (`0:00-0:10.6`) architecture slide. Cut directly to **`Set My Limits (Trusted Surface)`** (`0:10.6`), check **Human Intent Confirmation**, and click **`Sign & Mint Open Mandates`** (`$100/mo` cap, green `"Open Mandates Authenticated & Issued!"` banner held through `0:18.6`). On the **`3D Story`** stage (`0:18.6-0:27.0`), animate **Step 1/4** -> **Step 3/4 (`$49.99/mo Deal <= $60.00 Rule`)** -> **Step 4/4 (Compute Rack emerald green ON)**. At `0:27.0-0:45.8`, run **`2. Simulate Rogue AI Attack ($200 Lie)`** through Steps 1/4 -> 2/4 -> 3/4 -> 4/4 so Station 3 blocks the attack (`BLOCKED BEFORE SIGNING - Exceeds Your $60/mo Rule (HTTP 401)`). | *"When an autonomous AI agent buys cloud compute, handing the model your private payment keys is a serious security risk. A single prompt injection can drain your account. AP2 Autonomous Commerce solves this on PayPal Subscriptions using the Agent Payments Protocol, now under the FIDO Alliance. First, on our Trusted Surface, the human owner signs a sixty-dollar cryptographic spending limit and forwards the open mandates to the agent. Now watch the 3D pipeline as our buyer agent bargains down from a seventy-nine ninety-nine gateway to a forty-nine ninety-nine Batch Worker that fits the owner's rule. And if a prompt-injected agent lies and claims a two-hundred-dollar budget, the isolated Buyer Wallet MCP server blocks the signature before any money can move."* | **Best Use of Agentic Commerce ($5,000)** |
| **0:45.8 - 1:22.5** | **Act 2: Setup Console, Populated 4-Step AP2 Execution Trace & Anti-Tamper** | Switch directly to **`Setup`** (`0:45.8`). Inspect **Node Settings & Gateway** (`0:45.8-0:55.2`), then display the populated **`AP2 Execution Trace`** (`0:55.2-1:08.2`) showing `Step 4/4 Complete` and `"Settlement Ledger Mutated Successfully"` across all four verified stages. At `1:08.2-1:22.5`, open **`Anti-Tamper Verifier`** and click **`Tamper Price (+1 cent) & Re-Verify`** to trigger `401 Signature Mismatch: Budget Policy Violated`. | *"Switching to the Setup console, let's run an autonomous AP2 negotiation under a one-hundred-dollar cap. The seller verifies the mandate policy at seventy-nine ninety-nine a month and settles the recurring subscription through PayPal Subscriptions and the PayPal Agent Toolkit. In the right-hand inspector, we can audit the full ES256 SD-JWT execution trace and merchant receipts. Next, in the Anti-Tamper Verifier, if an attacker inflates the signed payload by even one cent, live signature re-verification immediately rejects the transaction with a 401 signature mismatch."* | **Best Use of PayPal + AI ($5,000)** |
| **1:22.5 - 2:01.05** | **Act 3: AG Grid Fleet Ledger, AG Studio BI Suite & Bryntum Workload Scheduler** | Switch to **`Dashboard`** (`1:22.5`). Inspect the **Live Operational Grid** and **Settlement Ledger** (`1:22.5-1:34.7`), then toggle to the **`AG Studio BI Suite`** **Executive View** and **Drag & Drop Editor** (`1:34.7-1:40.2`). At `1:40.2`, cut directly to **`Workloads`** (**Bryntum Scheduler**), click **`Sim Sub ($79.99)`** to transition `Node-01` from amber `Pending` to emerald `Dedicated Gateway`, and click **`Sim Workload Task`** to lock a slot on `Node-02` (`1:40.2-2:01.05`). | *"In the operations deck, AG Studio version three and AG Grid power the enterprise fleet ledger across fourteen seeded nodes, reconciling twelve hundred nineteen dollars in monthly recurring revenue. Operators can filter active subscriptions and switch seamlessly between Mission Control, Executive View, and the Drag and Drop Editor. Switching to Workloads, Bryntum Scheduler maps regional compute shifts across five worker clusters. As soon as PayPal confirms settlement, the pending compute node transitions in place from amber awaiting payment to active, and dispatches live workload tasks across the timeline."* | **AG Grid / AG Studio ($5,000)** &<br/>**Bryntum ($1,000)** |
| **2:01.05 - 2:22.1** | **Act 4: Zapier MCP QuickBooks GL 6300 Sync & CloudEvents v1.0** | Cut directly to **`MCP`** (`2:01.05`). Inspect the **Zapier MCP Action Execution Trace**, scroll through the **QuickBooks Online v3 (GL Account 6300)** JSON payload and **CloudEvents v1.0 (JSON-RPC)** schema, and highlight the HMAC-SHA256 **Signed Webhook Envelope** (`2:01.05-2:22.1`). | *"On the MCP tab, running the subscription chain triggers our Zapier back-office bridge. In the Wire and Schema Inspector, you can inspect the QuickBooks Online version three expense payload mapped to General Ledger Account sixty-three hundred, the CloudEvents JSON-RPC frame, and the HMAC-SHA256 signed webhook envelope, alongside our OpenAPI three point one contract and APIMatic SDKs."* | **Zapier / Back-Office** &<br/>**APIMatic ($1,000)** |
| **2:22.1 - 2:52.4** | **Act 5: Judge Verification Suite (792 Automated Tests & 9/9 Audit Harness)** | Transition to the **Judge Verification Suite Terminal** (`2:22.1-2:52.4`) displaying `python scripts/judge_audit_harness.py` (`9/9 CHECKS PASSED`) and `python -m pytest backend/tests -q -n 4` (`792 passed, 9 skipped`, including all 188 unmodified upstream AP2 conformance tests and the security regression suite). | *"Finally, everything is empirically verifiable in a single command. Running our Judge Audit Harness executes all nine cryptographic and operational invariant checks in under one second, while our standalone buyer agent CLI negotiates and settles end to end. The system is backed by seven hundred ninety-two passing automated tests, including all one hundred eighty-eight upstream AP2 SDK conformance tests and a transparent twenty-two-entry mock ledger. This is AP2 Autonomous Commerce, built for the PayPal AI Hackathon."* | **Empirical Proof & Security Architecture** |

---

## Complete Single-Pass Narration Transcript (`scripts/generate_hackathon_narration.py`)

```text
When an autonomous AI agent buys cloud compute, handing the model your private payment keys is a serious security risk. A single prompt injection can drain your account. AP2 Autonomous Commerce solves this on PayPal Subscriptions using the Agent Payments Protocol, now under the FIDO Alliance. First, on our Trusted Surface, the human owner signs a sixty-dollar cryptographic spending limit and forwards the open mandates to the agent. Now watch the 3D pipeline as our buyer agent bargains down from a seventy-nine ninety-nine gateway to a forty-nine ninety-nine Batch Worker that fits the owner's rule. And if a prompt-injected agent lies and claims a two-hundred-dollar budget, the isolated Buyer Wallet MCP server blocks the signature before any money can move.

Switching to the Setup console, let's run an autonomous AP2 negotiation under a one-hundred-dollar cap. The seller verifies the mandate policy at seventy-nine ninety-nine a month and settles the recurring subscription through PayPal Subscriptions and the PayPal Agent Toolkit. In the right-hand inspector, we can audit the full ES256 SD-JWT execution trace and merchant receipts. Next, in the Anti-Tamper Verifier, if an attacker inflates the signed payload by even one cent, live signature re-verification immediately rejects the transaction with a 401 signature mismatch.

In the operations deck, AG Studio version three and AG Grid power the enterprise fleet ledger across fourteen seeded nodes, reconciling twelve hundred nineteen dollars in monthly recurring revenue. Operators can filter active subscriptions and switch seamlessly between Mission Control, Executive View, and the Drag and Drop Editor. Switching to Workloads, Bryntum Scheduler maps regional compute shifts across five worker clusters. As soon as PayPal confirms settlement, the pending compute node transitions in place from amber awaiting payment to active, and dispatches live workload tasks across the timeline.

On the MCP tab, running the subscription chain triggers our Zapier back-office bridge. In the Wire and Schema Inspector, you can inspect the QuickBooks Online version three expense payload mapped to General Ledger Account sixty-three hundred, the CloudEvents JSON-RPC frame, and the HMAC-SHA256 signed webhook envelope, alongside our OpenAPI three point one contract and APIMatic SDKs.

Finally, everything is empirically verifiable in a single command. Running our Judge Audit Harness executes all nine cryptographic and operational invariant checks in under one second, while our standalone buyer agent CLI negotiates and settles end to end. The system is backed by seven hundred ninety-two passing automated tests, including all one hundred eighty-eight upstream AP2 SDK conformance tests and a transparent twenty-two-entry mock ledger. This is AP2 Autonomous Commerce, built for the PayPal AI Hackathon.
```
