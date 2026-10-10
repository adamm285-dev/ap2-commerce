# Repository Cartography (The Compass)
<!-- SPEC-001 v1.4.0 Pillar 5 | Flat Cartography -->
<!-- Golden Rule: Consult this map FIRST. Read ONLY necessary target files. -->

### `.agents/skills/ag-dev/`
- `SKILL.md`
- `VERSION.md`

### `.agents/skills/ag-dev/references/charts/`
- `documentation-index.md`
- `recommendations.md`

### `.agents/skills/ag-dev/references/grid/`
- `documentation-index.md`
- `recommendations.md`

### `.agents/skills/ag-dev/references/studio/`
- `documentation-index.md`
- `recommendations.md`

### `.agents/skills/ag-update/`
- `SKILL.md`
- `VERSION.md`

### `.agents/skills/ag-update/references/`
- `changes-file-preamble.md`
- `determine-changes.md`
- `determine-scope.md`
- `packages.md`

### `.cursor/`
- `mcp.json`

### `.github/workflows/`
- `ci.yml`

### `backend/`
- `__init__.py`
- `config.py`
- `database.py`
- `mcp_server.py`
- `models.py`
- `requirements-dev.txt`
- `requirements.txt`
- `server.py`

### `backend/agents/`
- `__init__.py`
- `buyer_agent.py`
- `llm_buyer_agent.py`
- `seller_agent.py`
- `seller_copilot.py`

### `backend/api/`
- `__init__.py`
- `m2m_audit.py`

### `backend/harness/`
- `external_buyer_agent.py`

### `backend/services/`
- `__init__.py`
- `ap2_keys.py`
- `ap2_service.py`
- `crypto_mandate.py`
- `mandate_evaluator.py`
- `paypal_service.py`
- `plan_catalog.py`
- `recurring_mandate_service.py`
- `trusted_surface_service.py`
- `zapier_mcp_dispatcher.py`

### `backend/services/backoffice/`
- `__init__.py`
- `qbo_exporter.py`
- `webhook_dispatcher.py`

### `backend/tests/`
- `__init__.py`
- `ap2_test_utils.py`
- `conftest.py`
- `test_agent_negotiation.py`
- `test_anti_tamper.py`
- `test_ap2_adversarial_audit.py`
- `test_ap2_dual_mandates_and_chaining.py`
- `test_ap2_security_poc_audit.py`
- `test_ap2_stage2_merchant.py`
- `test_ap2_stage3_commit2.py`
- `test_backoffice_export.py`
- `test_bi_reconciliation.py`
- `test_buyer_key_registration.py`
- `test_buyer_wallet.py`
- `test_database_persistence.py`
- `test_dynamic_negotiation.py`
- `test_e2e_full_lifecycle.py`
- `test_external_buyer_harness.py`
- `test_fleet_endpoints.py`
- `test_live_paypal_sandbox.py`
- `test_llm_buyer_agent.py`
- `test_mandate_evaluator.py`
- `test_mcp_profiles.py`
- `test_mcp_remote_stream.py`
- `test_mcp_server.py`
- `test_mocks_ledger.py`
- `test_plan_catalog.py`
- `test_plan_resolution.py`
- `test_purchase_idempotency_regression.py`
- `test_recurring_mandate_renewals.py`
- `test_security_regressions.py`
- `test_seller_copilot.py`
- `test_server_endpoints.py`
- `test_trusted_surface_limits.py`

### `backend/tests/conformance/`
- `conftest.py`
- `test_agent_recurrence.py`
- `test_benchmark_max_flow.py`
- `test_chain.py`
- `test_checkout_mandate_chain.py`
- `test_constraints.py`
- `test_constraints_line_items.py`
- `test_disclosure_metadata.py`
- `test_issuer_jwt_hash.py`
- `test_kb_sd_jwt.py`
- `test_kb_sd_jwt_intermediate.py`
- `test_mandate_presentation.py`
- `test_mandate_wrapper.py`
- `test_payment_mandate_chain.py`
- `test_receipt_wrapper.py`
- `test_sd_jwt.py`

### `backend/vendor/`
- `__init__.py`

### `backend/vendor/ap2/`
- `LICENSE`
- `NOTICE`
- `__init__.py`

### `backend/vendor/ap2/models/`
- `__init__.py`
- `cart.py`
- `contact_picker.py`
- `mandate.py`
- `payment_request.py`

### `backend/vendor/ap2/sdk/`
- `README.md`
- `__init__.py`
- `checkout_mandate_chain.py`
- `constraints.py`
- `disclosure_metadata.py`
- `jwt_helper.py`
- `mandate.py`
- `max_flow_helper.py`
- `payment_mandate_chain.py`
- `receipt_wrapper.py`
- `utils.py`

### `backend/vendor/ap2/sdk/generated/`
- `__init__.py`
- `checkout_mandate.py`
- `checkout_receipt.py`
- `open_checkout_mandate.py`
- `open_payment_mandate.py`
- `payment_mandate.py`
- `payment_receipt.py`

### `backend/vendor/ap2/sdk/generated/types/`
- `__init__.py`
- `amount.py`
- `buyer.py`
- `checkout.py`
- `item.py`
- `jwk.py`
- `line_item.py`
- `link.py`
- `merchant.py`
- `message.py`
- `message_error.py`
- `message_info.py`
- `message_warning.py`
- `payment_instrument.py`
- `pisp.py`
- `receipt_status.py`
- `total.py`

### `backend/vendor/ap2/sdk/sdjwt/`
- `__init__.py`
- `chain.py`
- `common.py`
- `kb_sd_jwt.py`
- `sd_jwt.py`

### `backend/vendor/ap2/tests/`
- `README.md`
- `agent_recurrence_tests.py`
- `benchmark_max_flow_tests.py`
- `chain_tests.py`
- `checkout_mandate_chain_tests.py`
- `conftest.py`
- `constraints_line_items_tests.py`
- `constraints_tests.py`
- `disclosure_metadata_tests.py`
- `issuer_jwt_hash_tests.py`
- `kb_sd_jwt_intermediate_tests.py`
- `kb_sd_jwt_tests.py`
- `mandate_presentation_tests.py`
- `mandate_wrapper_tests.py`
- `payment_mandate_chain_tests.py`
- `receipt_wrapper_tests.py`
- `sd_jwt_tests.py`

### `backend/wallet/`
- `__init__.py`
- `mcp_server.py`
- `wallet.py`

### `docs/`
- `MOCKS.md`
- `NOTEBOOKLM_SLIDES_PROMPT.md`
- `NOTEBOOKLM_SOURCE_DOCUMENT.md`
- `app_map.md`
- `decisions.md`
- `evals.md`
- `roadmap.md`
- `spine.md`
- `state.md`
- `wiring.yaml`

### `docs/audits/`
- `live_mcp_verification.log`

### `docs/prompts/`
- `grillme.md`

### `public/`
- `favicon.svg`
- `icons.svg`
- `llms.txt`

### `public/.well-known/`
- `mcp.json`

### `root/`
- `.dockerignore`
- `.env.example`
- `.geminiignore`
- `.gitignore`
- `.oxlintrc.json`
- `AGENTS.md`
- `DEMO_VIDEO_SCRIPT.md`
- `DEVPOST_SUBMISSION.md`
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `LICENSE`
- `README.md`
- `apimatic.json`
- `claude_desktop_config.json`
- `docker-compose.yml`
- `index.html`
- `mcp_config.json`
- `openapi.json`
- `openapi.yaml`
- `package-lock.json`
- `package.json`
- `pytest.ini`
- `skills-lock.json`
- `tsconfig.app.json`
- `tsconfig.json`
- `tsconfig.node.json`
- `vite.config.ts`

### `scripts/`
- `audit_live_mcp.py`
- `check_mocks.py`
- `generate_hackathon_narration.py`
- `judge_audit_harness.py`
- `live_cloud_stress_test.py`
- `setup_claude_desktop_demo.py`
- `setup_paypal_sandbox_plans.py`

### `sdk_examples/`
- `python_sdk_example.py`
- `typescript_sdk_example.ts`

### `src/`
- `App.css`
- `App.tsx`
- `index.css`
- `main.tsx`

### `src/assets/`
- `ap2_logo.jpg`
- `hero.png`
- `react.svg`
- `vite.svg`

### `src/components/`
- `AdversarialTamperModal.tsx`
- `AgStudioReportStudio.tsx`
- `BryntumDispatchScheduler.tsx`
- `EnterpriseFleetLedger.tsx`
- `NodeSettingsView.tsx`
- `SellerCopilotView.tsx`
- `TrustedSurfaceLimitsModal.tsx`
- `ZapierMcpView.tsx`

### `src/data/`
- `telemetryData.ts`

### `src/services/`
- `paypalAgentService.ts`
- `zapierMcpService.ts`

### `tests/fixtures/`
- `init.txt`
