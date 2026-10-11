# NotebookLM & Gemini Slides Prompt: Clean Architecture Walkthrough

> **Prompt Design:**
> This prompt tells Google NotebookLM (or Gemini) to regenerate the 8-slide architecture walkthrough from **Section 11 of `NOTEBOOKLM_SOURCE_DOCUMENT.md`**, using **Section 12 (Accuracy Guardrails)** as a list of things never to draw.
> It fixes the errors found in the October 10, 2026 deck: invented technology labels, a wrong architecture diagram, fabricated terminal output, demo data presented as revenue, and garbled generated text.

---

## The Master Revision & Steering Prompt (Copy & Paste)
*Paste this prompt directly into NotebookLM's prompt box:*

```markdown
Regenerate the 8-slide architecture deck from Section 11 of the source document. Use only facts from the source document. Treat Section 12 (Accuracy Guardrails) as a list of things you must never show.

LAYOUT RULES:
1. No file paths or code anchors on any slide.
2. No watermarks, logos or sparkle badges.
3. No narration boxes on the canvas.
4. Every word on a slide must be spelled correctly and legible at presentation size. Prefer a few large labels over dense grids of small bracketed tags.
5. Do not generate fake tables, timestamps, hashes or JSON. If a slide needs output, use the exact text given below.

SLIDE CORRECTIONS:
- Slide 1: Title "AP2 Autonomous Commerce: Built on AP2 v0.2, Extending Its Roadmap". Subtitle "Google's Agent Payments Protocol, now under the FIDO Alliance".
  * Left box: AP2 v0.2 baseline only: open and closed Checkout and Payment Mandates, SD-JWT, ES256, Human Present and Human Not Present flows, "188 SDK tests passing". No version numbers other than v0.2, and no "stable" badge.
  * Right: four items with their real status: Recurring payments & subscriptions [V1.x roadmap]; Human Not Present purchases [shipped in v0.2, implemented here]; MCP-based implementation [V1.x roadmap]; Buyer–seller negotiation [long-term vision].
  * Remove every invented label: TLS 1.3/Noise, FIDO2/WebAuthn, TEE/Secure Enclave, zero-knowledge, mDNS/DHT, JSON-LD, auction, multi-sig, ECC/RSA, daily/weekly billing, usage pricing, "0.2.1a".
  * Bottom bullets: "Implements AP2 v0.2 with Google's SDK" and the three signers (owner signs limits, merchant signs checkout, buyer's wallet signs the closed mandates). Do not say "full conformance".
- Slide 2: Show the attack text once each (a web page and the seller's reply). Replace "Treasury Vault" with "Buyer Wallet (separate process)". Bullets as in the source document.
- Slide 3: Title "Two-Server MCP Architecture: The Isolated Buyer Wallet". Do NOT say FastMCP. Draw Claude Desktop at the top connected separately to the Buyer Wallet and the Seller; the wallet and the seller are NOT connected to each other. Number the steps 1–4 exactly as in the source document. Write "WalletRefusal" as one word in code style.
- Slide 4: Remove "Vault" and "MIT" everywhere. Subtitle "Webhook checks, advance cancellation, and separate purchase and billing windows". Show a "next charge allowed?" check after EVERY PAYMENT.SALE.COMPLETED, not one check mid-year, and a "cancel in advance" marker before a 13th charge. Third bullet: "A price change is caught after the charge: it cancels; unverifiable charges suspend; refunds are manual."
- Slide 5: Replace the fake terminal entirely. No "0x" values, no decimal dollar amounts, no "BUDGET_CAP_EXCEEDED". Show only these two outputs:
  `Tamper Test (+1¢ Inflation $79.99 -> $80.00): REJECTED (invalid_mandate)`
  `{"status": "REFUSED", "error": "PAYMENT_CONSTRAINT_VIOLATION"}`
  Say "two merchant-signed error receipts", not "dual-signed". Replace "self-heal workflows" with "counter-offers the best tier within budget".
- Slide 6: Title "Demo Fleet Operations: Dashboard, Dispatch and Accounting Payloads". Put a visible "Seeded demo data" label on the fleet panel. Do not write "ARR" as revenue; write "Demo fleet: 14 subscriptions, 13 active, $1,219.87 MRR". Mark the QuickBooks payload "generated (dry run)". Leave the panels as simple outlined boxes with titles if you cannot show clean content; no generated tables or times.
- Slide 7: Keep the 2x2 matrix but label it: Keys (disk → hardware-backed), Replay protection (in-memory → shared store), Rails (seller verifies AP2 → networks verify AP2), Revocation (expiry only → status list). Do not pair nonces with KMS; do not say CRL. Add a short list: renew limits after payment 12, check charge spacing, verify renewals on the PayPal sandbox, 18 declared mocks.
- Slide 8: Title "Verification: Tests, Judge Audit and Declared Mocks". Panels: "559 passed, 9 skipped (188 Google AP2 SDK tests + 371 project tests)"; "9/9 judge checks, about 1 second, no API keys"; "18 declared mocks, checked by a test". Remove "Standards Contribution", "battle-tested" and "AP2 V1.x working group".

Generate the full 8-slide deck now, following these rules exactly.
```

---

## Executive Slide Deck Summary Table (Reference Ground Truth)

| Slide | Title | Core Technical Point | Architectural Component |
| :---: | :--- | :--- | :--- |
| **01** | **AP2 v0.2 Baseline & Roadmap** | AP2 v0.2 (now under the FIDO Alliance) implemented with Google's SDK; Human Not Present implemented; recurring payments, MCP and negotiation extended | `AP2 v0.2 SDK`, `FIDO Alliance` |
| **02** | **The Untrusted Courier Threat** | Why LLMs must never hold private signing keys | `Buyer Wallet`, `Key Isolation` |
| **03** | **Two-Server MCP Architecture** | The wallet holds the agent key and owner-signed limits; overspending is refused with `WalletRefusal` before signing | `Seller MCP Server`, `Buyer Wallet MCP Server` |
| **04** | **Recurring Billing & Renewal Enforcement** | Webhook re-verification, plus advance cancellation before the payment count, budget or term runs out | `Recurring Mandate Service` |
| **05** | **Counter-Offers & Anti-Tamper** | Counter-offer to the $49.99 Batch Worker; 1¢ inflation rejected with `invalid_mandate` | `Seller Agent`, `AP2 ES256 SD-JWT Verifier` |
| **06** | **Demo Fleet Operations (Seeded Data)** | AG Studio v3.0.0 fleet ledger, Bryntum Scheduler and QuickBooks GL 6300 payloads over seeded demo data | `Enterprise Fleet Ledger`, `Back-Office Export` |
| **07** | **The Production Gap Report** | Disk keys, in-memory replay caches, no revocation, no native AP2 rail, renewal edge cases, 18 declared mocks | `Hardware Keys`, `Shared State`, `Native AP2 Rails` |
| **08** | **Empirical Verification** | 559 passing tests (188 SDK + 371 project); 9/9 judge checks in about a second; 18 declared mocks | `Automated Test Suite`, `Judge Audit Harness`, `Mock Ledger` |
