# MOCKS.md: Mock Inventory

Every place where the code stands in for real behavior: simulated API responses, seeded or hardcoded data, demo-only keys or endpoints, offline stubs, and fallbacks that fake success.

**How this file is kept honest.** Each entry has an ID. The code it describes carries a marker with the same ID: `# MOCK(M-NNN): ...` in Python, `// MOCK(M-NNN): ...` in TypeScript. `backend/tests/test_mocks_ledger.py` fails if a marker has no entry, an entry has no marker, an entry lists a file with no marker for it, or a listed `path::symbol` doesn't exist. Run it directly with `python scripts/check_mocks.py`.

**Format.** One `### M-NNN: title` heading per entry, then four fields: `Where` (one or more backticked `path::symbol`), `What it fakes`, `Why`, and `To make it real`.

**Retired IDs (never reuse):** M-013 (failing-open Vault capture, code deleted 2026-10-10), M-017 (frontend faked success when the backend was unreachable, fixed 2026-10-10; it now reports the failure).

---

### M-001: Mock mode turns itself on when PayPal keys are missing
- **Where:** `backend/config.py::settings`
- **What it fakes:** If `PAYPAL_CLIENT_ID` or `PAYPAL_CLIENT_SECRET` is empty, `MOCK_EXTERNAL_APIS` is forced to true, so every mock below activates even if you asked for live mode.
- **Why:** Lets the app start with no credentials.
- **To make it real:** In live deployments, refuse to start when live mode is requested and credentials are missing, instead of switching silently.

### M-002: PayPal REST calls are simulated in mock mode
- **Where:** `backend/services/paypal_service.py::PayPalService.get_access_token`, `backend/services/paypal_service.py::PayPalService.get_sync_access_token`, `backend/services/paypal_service.py::PayPalService.stop_subscription`, `backend/services/paypal_service.py::PayPalService.create_order`, `backend/services/paypal_service.py::PayPalService.verify_subscription`, `backend/services/paypal_service.py::PayPalService.create_subscription`
- **What it fakes:** OAuth tokens, orders, subscription creation (returned as ACTIVE with no buyer approval), subscription lookups, and cancel/suspend calls. No request reaches PayPal.
- **Why:** Project rule 9 (no live network calls) and credential-free judging.
- **To make it real:** Set `MOCK_EXTERNAL_APIS=false` with sandbox credentials. The live branches exist but the live tests (`backend/tests/test_live_paypal_sandbox.py`) have not been run, and they don't cover cancel/suspend.

### M-003: Webhook signatures are checked with a local HMAC in mock mode
- **Where:** `backend/services/paypal_service.py::PayPalService.verify_webhook_signature`, `backend/services/paypal_service.py::PayPalService.generate_mock_webhook_signature`
- **What it fakes:** PayPal's webhook signature verification. In mock mode a webhook is accepted if it carries an HMAC this server computes itself.
- **Why:** Lets tests and demos send signed webhooks without PayPal.
- **To make it real:** Live mode calls PayPal's `verify-webhook-signature` API with `PAYPAL_WEBHOOK_ID`; run it once against sandbox.

### M-004: PayPal buyer approval is simulated
- **Where:** `backend/server.py::simulate_paypal_approval`, `backend/harness/external_buyer_agent.py::ExternalBuyerAgent.execute_autonomous_procurement`
- **What it fakes:** The human approving a subscription on PayPal. An admin-only endpoint flips APPROVAL_PENDING to ACTIVE; the external buyer harness calls it.
- **Why:** Completes the flow in sandbox and mock runs without a browser.
- **To make it real:** The buyer approves at PayPal's `approval_url`; activation then arrives via the `BILLING.SUBSCRIPTION.ACTIVATED` webhook.

### M-005: Demo owner and agent keys live inside the server process
- **Where:** `backend/services/ap2_keys.py::get_demo_user_key`, `backend/services/ap2_keys.py::get_demo_agent_key`, `backend/services/ap2_service.py::resolve_root_public_key`, `backend/services/ap2_service.py::create_trusted_surface_open_mandates`, `backend/services/ap2_service.py::create_closed_mandate_chains`, `backend/services/trusted_surface_service.py::create_trusted_surface_open_mandates`, `backend/agents/buyer_agent.py::BuyerAgent.run_autonomous_onboarding_cycle`, `backend/agents/llm_buyer_agent.py::mint_demo_owner_limits_to_file`
- **What it fakes:** The owner's device and the buyer agent's wallet. The server generates both keys in memory, signs owner limits with the "owner" key, and in mock mode accepts that key as a trust root. In this setup the seller can produce owner authorizations, so non-repudiation is not demonstrated.
- **Why:** One-process demos and tests.
- **To make it real:** Owner keys come only from the registry (enrolled via the challenge flow) and are held on the owner's device, ideally a passkey. Agents sign with their own key in their own process, as `backend/wallet/` does.

### M-006: The server signs owner limits for any caller (mock mode only)
- **Where:** `backend/server.py::trusted_surface_sign_limits_endpoint`, `src/services/paypalAgentService.ts::evaluateAgentNegotiation`
- **What it fakes:** The owner's signing surface. Any caller that sends `human_confirmed: true` gets owner-signed limits with any cap. The flag is not proof that a human confirmed, and the portal's negotiation step sends it hardcoded to true without asking anyone.
- **Why:** Lets the portal UI demo "owner sets limits" without a passkey.
- **To make it real:** The owner signs in the browser or on a phone (WebCrypto or passkey); the server only verifies. Live mode already returns 404 here.

### M-007: Deck purchase runs the whole purchase server-side (mock mode only)
- **Where:** `backend/server.py::deck_purchase_endpoint`
- **What it fakes:** All three parties at once. The server signs owner limits, negotiates, and closes the mandates as the agent, using the M-005 demo keys.
- **Why:** One-click purchase in the portal demo.
- **To make it real:** The owner, agent and seller sign in separate places, as in the Claude Desktop flow (`backend/wallet/`).

### M-008: A throwaway merchant key is generated when none is configured
- **Where:** `backend/services/ap2_keys.py::get_merchant_key`
- **What it fakes:** A stable merchant signing key. Without `AP2_MERCHANT_PRIVATE_KEY_JWK` or `AP2_MERCHANT_PRIVATE_KEY_FILE`, each process makes its own key, so checkouts signed by one process can't be verified by another.
- **Why:** Tests and single-process demos.
- **To make it real:** Load the merchant key from a KMS or HSM and publish its public key (JWKS).

### M-009: The fleet ledger and schedule are seeded demo data
- **Where:** `backend/database.py::AP2_FLEET_SEEDED_SUBSCRIPTIONS`, `backend/database.py::seed_fleet_subscriptions_if_empty`, `backend/database.py::get_fleet_ledger`, `backend/database.py::get_fleet_schedule`
- **What it fakes:** A fleet of 14 compute-node subscriptions (13 active) and a hardcoded scheduler event list. The fleet MRR and ARR on the dashboard come from this seed.
- **Why:** The AG Studio and Bryntum views have something to show without 14 real purchases.
- **To make it real:** Seed only behind an explicit demo flag; build the ledger and schedule from real subscriptions.

### M-010: Compute node provisioning returns a placeholder endpoint
- **Where:** `backend/agents/seller_agent.py::SellerAgent.provision_compute_node`
- **What it fakes:** Allocating compute. The subscription checks are real, but the "node" is a generated ID and an `mcp+https://…example.com` endpoint; nothing is provisioned.
- **Why:** There is no compute infrastructure behind the demo.
- **To make it real:** Call a real provisioning backend and return its actual endpoint.

### M-011: Back-office exports are generated, not delivered
- **Where:** `backend/services/backoffice/webhook_dispatcher.py::is_url_permitted`, `backend/services/backoffice/webhook_dispatcher.py::BackofficeWebhookDispatcher.dispatch`, `backend/services/zapier_mcp_dispatcher.py::ZapierMcpDispatcher.execute_downline_sync`
- **What it fakes:** Delivery to QuickBooks, ERP and calendar systems. Without a webhook URL the export is a dry run with no network call. Mock mode also allows localhost and mock-only domains. Non-onboarding workflows return made-up ERP, QuickBooks and calendar IDs.
- **Why:** Shows the payloads without QuickBooks or Zapier accounts.
- **To make it real:** Configure a webhook target (for example a Zapier catch hook connected to QuickBooks) and return the IDs the downstream systems actually assign.

### M-012: MCP tools fill missing IDs with demo values
- **Where:** `backend/mcp_server.py::_handle_mcp_request_internal`
- **What it fakes:** Caller input. `provision_compute_node` defaults to subscription `I-MOCK-SUB-01`; `dispatch_zapier_mcp` defaults to subscription `I-AUTONOMOUS-8902`, a $79.99 fee and placeholder names and endpoints.
- **Why:** Lets an MCP client call the tools with almost no arguments during demos.
- **To make it real:** Make these arguments required and reject calls that omit them.

### M-014: The anti-tamper playground uses demo keys and a demo secret
- **Where:** `backend/services/crypto_mandate.py::DEMO_TAMPER_SECRET`, `backend/services/crypto_mandate.py::_DEMO_TAMPER_KEY`, `backend/server.py::verify_tamper_endpoint`, `backend/server.py::generate_proof_endpoint`, `backend/server.py::get_sample_proof`
- **What it fakes:** A tamper-detection demo on the older Ed25519/HMAC "mandate proof" format, with a hardcoded secret and a throwaway key. It's not the AP2 v0.2 purchase path, which uses ES256 SD-JWT.
- **Why:** An interactive "change one byte and watch it fail" demo for the UI.
- **To make it real:** Demonstrate tampering against real AP2 v0.2 chains (as `scripts/judge_audit_harness.py` check 4 does) and retire the legacy format.

### M-015: The buyer agent's "LLM" is an offline script unless a provider is set
- **Where:** `backend/agents/llm_buyer_agent.py::StubbedModelRunner`, `backend/agents/llm_buyer_agent.py::LLMBuyerAgent.__init__`
- **What it fakes:** Model reasoning. With no `--provider`, a deterministic script picks the tool calls.
- **Why:** Runs offline with no API key (project rule 9).
- **To make it real:** Pass `--provider` (openai, xai or gemini) with an approved key, or use Claude Desktop with the wallet.

### M-016: The seller "AI Copilot" is keyword-matched canned replies
- **Where:** `backend/agents/seller_copilot.py::SellerCopilot.handle_message`
- **What it fakes:** An AI assistant. Replies are chosen by matching words in the message, and the fleet statistics in them are hardcoded text, not read from the ledger.
- **Why:** Copilot demo without a model.
- **To make it real:** Back it with a model, and compute any numbers from the ledger at request time.

### M-018: Dashboard data is hardcoded in the frontend
- **Where:** `src/data/telemetryData.ts::initialA2aTransactions`, `src/data/telemetryData.ts::kycAuditData`, `src/data/telemetryData.ts::nodeClusterData`, `src/components/ZapierMcpView.tsx::ZapierMcpView`
- **What it fakes:** Transactions, KYC audit records and node-cluster data shown before (or instead of) backend data, and example QuickBooks, CloudEvents and webhook payloads shown in the back-office view when no run has produced real ones.
- **Why:** Dashboards render immediately.
- **To make it real:** Load from the backend and show empty states when there's no data.

### M-019: UI controls that simulate events
- **Where:** `src/components/BryntumDispatchScheduler.tsx::handleSimulateActivation`, `src/components/BryntumDispatchScheduler.tsx::handleSimulateInboundLeadAndLock`, `src/components/SellerCopilotView.tsx::triggerBuyerSimulatorIntro`
- **What it fakes:** Line activation, inbound work and a buyer walkthrough, triggered by buttons rather than real events.
- **Why:** Lets a presenter show state changes on demand.
- **To make it real:** Drive these views from real webhook and subscription events; keep the buttons only behind a demo flag.

### M-020: Workload dispatch automation is simulated entirely in the browser
- **Where:** `src/services/zapierMcpService.ts::executeZapierMcpWorkflow`
- **What it fakes:** The whole "workload dispatch" back-office run: CloudEvents, QuickBooks invoice and EventBus routing are generated client-side after a 600 ms delay. No backend call is made.
- **Why:** Gives the workload scenario in the back-office view something to show.
- **To make it real:** Call a backend endpoint that performs (or dry-runs and says so) each step, as the onboarding scenario does.

### M-021: The back-office run log reports deliveries that didn't happen
- **Where:** `src/services/zapierMcpService.ts::executeZapierA2aWorkflow`
- **What it fakes:** Delivery results. Even when the backend only did a dry run, the browser labels the QuickBooks, CloudEvents and webhook steps VERIFIED, and shows a hardcoded `X-AP2-Signature`, a placeholder `HMAC-MANDATE-VERIFIED-01` proof, `protocol_version: AP2-v1.4.1` and a fixed Zapier hook URL.
- **Why:** Leftover presentation code from before the backend reported dry runs.
- **To make it real:** Build the log from what the backend returns (for example `webhookDispatched` and the delivery ID) and label dry runs as dry runs.
