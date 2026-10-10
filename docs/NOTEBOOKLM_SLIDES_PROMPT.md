# NotebookLM & Gemini Slides Prompt: Fact-Checked Engineering Walkthrough

> **Prompt Design:**  
> This prompt instructs Google NotebookLM (or Gemini) to generate an authentic architecture walkthrough based on **Section 11 of `NOTEBOOKLM_SOURCE_DOCUMENT.md`**.  
> It incorporates all code-verified facts, removes AI-generated visual artifacts, and reflects our 554-test suite and real 9-check judge audit harness.

---

## The All-in-One Short Prompt (Recommended)
*Paste this prompt directly into NotebookLM with `NOTEBOOKLM_SOURCE_DOCUMENT.md` attached as the source:*

```markdown
Using Section 11 of the source document ("Complete 8-Slide Executive Architecture Walkthrough (Fact-Checked Ground Truth)"), generate the complete 8-slide presentation deck.

Requirements:
- Label the slides as an "Architecture Walkthrough" with "Narration" scripts (not "Audits").
- Do NOT include any synthetic timestamps (e.g. 2024-05-27) or garbled text.
- Accurately state: 554 tests passing (188 Google SDK + 366 project), 13 active nodes of 14 provisioned ($14,638.44 annualized ARR), and cite the real 9 Judge Audit checks.

To ensure all 8 slides generate completely without hitting token cutoff limits, format each slide concisely using this structure:

- **Slide [N]: [Title]** — *[Subtitle]*
- **Visual:** [1-sentence schematic description without synthetic timestamps]
- **Core Invariants:** [3 punchy, technical bullet points grounded in code]
- **Code Anchor:** [Exact file path & test reference]
- **Narration (15-20s):** "[Spoken voiceover sentence]"

Generate all 8 slides now from Slide 1 through Slide 8.
```

---

## Two-Turn Staged Prompt (For Maximum Depth)
*If you want full paragraph speaker scripts without hitting the output token limit:*

**Turn 1:**
```markdown
Using Section 11 of the source document, generate an in-depth slide specification for Slides 1 through 4 only (AP2 v0.2 Baseline, Untrusted Courier Threat, Two-Process MCP Architecture, and Recurring Billing & Renewal Enforcement). Include the full slide title, detailed visual layout, 3 technical takeaways with exact code anchors, and the complete 20-second narration script.
```

**Turn 2:**
```markdown
Now generate Slides 5 through 8 (Dynamic Bargaining, Simulated Fleet Operations, The Production Gap Report, and Empirical Verification), and conclude with the Executive Slide Deck Summary Table.
```

---

## Pre-Rendered Executive Summary Table (For README & Devpost)

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
