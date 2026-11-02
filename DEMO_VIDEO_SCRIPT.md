# AP2 Autonomous Commerce - Official Hackathon Demo Video Script & Screen Layout Guide

> **Duration:** 2 minutes 58.0 seconds (`178.02s`, ~3-Minute Detailed Walkthrough)  
> **Target Event:** PayPal AI Hackathon 2026  
> **Live Demo URL:** `https://ap2-commerce.fieldsmith.pro/`  
> **Final Video File:** `media/hackathon_demo/AP2_Autonomous_Commerce_Demo_2Min.mp4` (`1920x1080` @ 30fps, H.264 + 48kHz AAC)  
> **Narration Model:** Single-pass `gemini-3.8-flash-tts` studio voice (`Achird`, pure `1.0x` natural cadence + `48 kHz` stereo `-1.9 dBFS` true-peak mastering via `scripts/generate_hackathon_narration.py`)  
> **Structure:** 5 Detailed Acts covering all 6 prize tracks + live terminal proof so judges see the architectural trust boundaries, the complete 4-station 3D animations, the interactive operations deck, the populated 4-step AP2 Execution Trace, and the real cryptographic/test execution underneath.

---

## Screen Layout & Two-Scene Flow (`1920x1080`)

```text
+-----------------------------------------------------------------------------------+
| SCENE A (0:00 - 2:26.5) - ARCHITECTURE INTRO + FULL-SCREEN BROWSER (1920x1080)    |
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

                            |||  Switch at 2:26.5  |||

+-----------------------------------------------------------------------------------+
| SCENE B (2:26.5 - 2:58.0) - JUDGE VERIFICATION SUITE TERMINAL OVERLAY (1920x1080) |
|                                                                                   |
|  > python -m pytest backend/tests -q -n 4                                         |
|    792 passed, 9 skipped in 58.81s (188 upstream AP2 conformance + regressions)   |
|  > python scripts/check_mocks.py                                                  |
|    docs/MOCKS.md matches the MOCK markers in the code.                            |
+-----------------------------------------------------------------------------------+
```

---

## Master Timing & Click-by-Click Storyboard (2:58.0 / 178.02s)

| Time | Act / Theme | Exact Screen Action | Voiceover Narration (`gemini-3.8-flash-tts`, `1.0x` Native Speed) | Prize Track Highlight |
| :--- | :--- | :--- | :--- | :--- |
| **0:00 - 0:48.6** | **Act 1: Architecture Intro, Trusted Surface Minting & Full 4-Station 3D Story** | Show **AP2 v0.2 Cryptographic Foundations** (`0:00-0:05`) and **Dual-MCP Process Boundary Airgap** (`0:05-0:09.8`) architecture slides. Cut to **`3D Story`** (`0:09.8`) and open **`Set My Limits (Trusted Surface)`** (`0:10.6`), check **Human Intent Confirmation**, and click **`Sign & Mint Open Mandates`** (`$60/mo` cap, green `"Open Mandates Authenticated & Issued!"` banner held through `0:18.6`). On the **`3D Story`** stage (`0:18.6-0:29.8`), animate **Step 1/4** -> **Step 3/4 (`$49.99/mo Deal <= $60.00 Rule`)** -> **Step 4/4 (Compute Rack emerald green ON)**. At `0:29.8-0:48.6`, run **`2. Simulate Rogue AI Attack ($200 Lie)`** so Station 3 blocks the attack (`BLOCKED BEFORE SIGNING - Exceeds Your $60/mo Rule (HTTP 401)`). | *"When an autonomous AI agent buys cloud compute, handing it raw payment credentials is a critical security risk. AP2 Autonomous Commerce eliminates that risk using Google's Agent Payments Protocol, version zero point two, now stewarded by the FIDO Alliance. First, on our Trusted Surface, the human owner signs open checkout and payment mandates in an isolated hardware vault, enforcing a strict sixty-dollar monthly spending cap. On our three-D pipeline stage, when the buyer agent requests a seventy-nine ninety-nine AI Gateway that exceeds that cap, the seller negotiates a forty-nine ninety-nine Batch Worker counter-offer, PayPal verifies the cryptographic chain, and the server rack lights up green. Conversely, when a prompt-injected rogue agent attempts an unauthorized two-hundred-dollar charge, the isolated signing boundary refuses to sign and blocks the attack at the gate with an HTTP four-oh-one refusal before any funds move."* | **Best Use of Agentic Commerce ($5,000)** |
| **0:48.6 - 1:25.3** | **Act 2: Setup Console, Populated 4-Step AP2 Execution Trace & Anti-Tamper** | Switch directly to **`Setup`** (`0:48.6`). Inspect **Node Settings & Gateway** (`0:48.6-0:58.0`), then display the populated **`AP2 Execution Trace`** (`0:58.0-1:11.0`) showing `Step 4/4 Complete` and `"Settlement Ledger Mutated Successfully"` across all four verified stages. At `1:11.0-1:25.3`, open **`Anti-Tamper Verifier`** and click **`Tamper Price (+1 cent) & Re-Verify`** to trigger `401 Signature Mismatch: Budget Policy Violated`. | *"Moving to the Setup console, the untrusted buyer agent communicates strictly over the Model Context Protocol without ever touching private keys. Approving a seventy-nine ninety-nine PayPal subscription under a one-hundred-dollar owner limit records the complete four-stage AP2 execution trace: verifying the programmatic mandate, minting the delegated PayPal subscription token, allocating the dedicated compute node, and mutating the settlement ledger. And inside our live Anti-Tamper Verifier, mutating the signed price by even a single cent invalidates the selective-disclosure digest and triggers an immediate HTTP four-oh-one signature mismatch."* | **Best Use of PayPal + AI ($5,000)** |
| **1:25.3 - 2:05.0** | **Act 3: AG Grid Fleet Ledger, AG Studio BI Suite & Bryntum Workload Scheduler** | Switch to **`Dashboard`** (`1:25.3`). Inspect the **Live Operational Grid** (`1:25.3-1:35.5`), scroll to the **Settlement Ledger** and open the **Cryptographic Audit Drawer** (`1:35.5-1:42.8`), then toggle to the **`AG Studio BI Suite`** executive chart view (`1:42.8-1:48.5`). At `1:48.5`, cut directly to **`Workloads`** (**Bryntum Scheduler**), click **`Sim Sub ($79.99)`** to transition `Node-01` from amber `AWAITING PAYPAL` to emerald `Node-01 Active ($79.99)`, and click **`Sim Workload Task`** to lock a slot on `Node-02` (`1:48.5-2:05.0`). | *"On the Dashboard, AG Grid Enterprise powers our live operational telemetry and settlement ledger across fourteen active mandates totaling twelve hundred nineteen dollars and eighty-seven cents in monthly recurring revenue. Clicking any settled row opens the cryptographic audit drawer with its full selective-disclosure receipt, while toggling to the AG Studio BI Suite renders real-time executive revenue analytics. Switching to Workloads, the Bryntum Scheduler maps regional compute capacity across five enclave clusters. Simulating a settled seventy-nine ninety-nine subscription immediately transitions Node-01 in place from amber awaiting payment to active emerald green, and dispatching a workload task locks a dedicated execution slot on Node-02."* | **AG Grid / AG Studio ($5,000)** &<br/>**Bryntum ($1,000)** |
| **2:05.0 - 2:26.5** | **Act 4: Zapier MCP QuickBooks GL 6300 Sync & CloudEvents v1.0** | Cut directly to **`MCP`** (`2:05.0`). Inspect the **Zapier MCP Action Execution Trace**, scroll through the **QuickBooks Online v3 (GL Account 6300)** JSON payload and **CloudEvents v1.0 (JSON-RPC)** schema, and highlight the HMAC-SHA256 **Signed Webhook Envelope** (`2:05.0-2:26.5`). | *"On the MCP tab, our autonomous enterprise fulfillment pipeline dispatches an HMAC-SHA256 signed CloudEvents one-point-zero envelope through Zapier MCP directly into QuickBooks Online version three, automatically reconciling every compute subscription under General Ledger Account sixty-three hundred."* | **Zapier / Back-Office** &<br/>**APIMatic ($1,000)** |
| **2:26.5 - 2:58.0** | **Act 5: Judge Verification Suite (888 Automated Tests & Mock Ledger Check)** | Transition to the **Judge Verification Suite Terminal** (`2:26.5-2:58.0`) displaying `python -m pytest backend/tests -q -n 4` (`888 passed, 2 skipped`, including all 188 unmodified Google AP2 conformance tests and the security regression suite) and `python scripts/check_mocks.py` (`docs/MOCKS.md matches the MOCK markers in the code.`). | *"Finally, every security invariant is continuously verified from the command line: our full test suite passes eight hundred eighty-eight automated tests, including all one hundred eighty-eight unmodified Google AP2 conformance tests and our strict security regression and mock-ledger audits. Thank you for watching AP2 Autonomous Commerce."* | **Empirical Proof & Security Architecture** |

---

## Complete Single-Pass Narration Transcript (`scripts/generate_hackathon_narration.py`)

```text
When an autonomous AI agent buys cloud compute, handing it raw payment credentials is a critical security risk. AP2 Autonomous Commerce eliminates that risk using Google's Agent Payments Protocol, version zero point two, now stewarded by the FIDO Alliance. First, on our Trusted Surface, the human owner signs open checkout and payment mandates in an isolated hardware vault, enforcing a strict sixty-dollar monthly spending cap. On our three-D pipeline stage, when the buyer agent requests a seventy-nine ninety-nine AI Gateway that exceeds that cap, the seller negotiates a forty-nine ninety-nine Batch Worker counter-offer, PayPal verifies the cryptographic chain, and the server rack lights up green. Conversely, when a prompt-injected rogue agent attempts an unauthorized two-hundred-dollar charge, the isolated signing boundary refuses to sign and blocks the attack at the gate with an HTTP four-oh-one refusal before any funds move.

Moving to the Setup console, the untrusted buyer agent communicates strictly over the Model Context Protocol without ever touching private keys. Approving a seventy-nine ninety-nine PayPal subscription under a one-hundred-dollar owner limit records the complete four-stage AP2 execution trace: verifying the programmatic mandate, minting the delegated PayPal subscription token, allocating the dedicated compute node, and mutating the settlement ledger. And inside our live Anti-Tamper Verifier, mutating the signed price by even a single cent invalidates the selective-disclosure digest and triggers an immediate HTTP four-oh-one signature mismatch.

On the Dashboard, AG Grid Enterprise powers our live operational telemetry and settlement ledger across fourteen active mandates totaling twelve hundred nineteen dollars and eighty-seven cents in monthly recurring revenue. Clicking any settled row opens the cryptographic audit drawer with its full selective-disclosure receipt, while toggling to the AG Studio BI Suite renders real-time executive revenue analytics. Switching to Workloads, the Bryntum Scheduler maps regional compute capacity across five enclave clusters. Simulating a settled seventy-nine ninety-nine subscription immediately transitions Node-01 in place from amber awaiting payment to active emerald green, and dispatching a workload task locks a dedicated execution slot on Node-02.

On the MCP tab, our autonomous enterprise fulfillment pipeline dispatches an HMAC-SHA256 signed CloudEvents one-point-zero envelope through Zapier MCP directly into QuickBooks Online version three, automatically reconciling every compute subscription under General Ledger Account sixty-three hundred.

Finally, every security invariant is continuously verified from the command line: our full test suite passes eight hundred eighty-eight automated tests, including all one hundred eighty-eight unmodified Google AP2 conformance tests and our strict security regression and mock-ledger audits. Thank you for watching AP2 Autonomous Commerce.
```
