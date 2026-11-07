# Empirical Standing & Ground Truth (Evals)
<!-- SPEC-001 v1.9.0 Pillar 7 | Mutability: CRYPTOGRAPHIC -->
<!-- Corpus Diversity Invariant: Unique SHA-256 digests required across all golden fixtures -->

## 1. Golden Reference Corpus & Diversity
| Asset ID | Path / Scenario | SHA-256 (Normalized) | Unique Characteristics | Target Subsystem |
| :--- | :--- | :--- | :--- | :--- |
| `TC-INIT` | `tests/fixtures/init.txt` | `8ca3b82b88a0f82559ebc4f0804792fe0cbb98e701d2f6f4fb334a1f0b3405c4` | Baseline golden reference | Core Engine |
| `EVAL-SEC-REG` | `backend/tests/test_security_regressions.py` | `7e5eb6c82e869a5272e7852ac867fd47c0904b0cce46d2516225006e43b91a40` | Reviewer security regression suite (Sections 1-7) | Security & Mandate Verification |
| `EVAL-CONC-LEASE` | `backend/tests/test_purchase_concurrency.py` | `c6dd23b0f708c8b82a9528245c205c2cbc2cb0954e0bc8a48a980be0f036547f` | Cross-process SQLite purchase leases & `PayPal-Request-Id` idempotency | Purchase & PayPal Service |
| `EVAL-MOCK-LEDGER` | `backend/tests/test_mocks_ledger.py` | `81ac14294d432e4ea07fdca86fa74a45308ccc01e047a4c3f934c9a5b99da4e7` | Bi-directional `docs/MOCKS.md` vs `# MOCK(M-NNN)` code marker verifier | Governance & Mock Gate (Gate L) |
| `EVAL-RENEWAL` | `backend/tests/test_recurring_mandate_renewals.py` | `dd2675378755bea61cfd52145d48147391043b1c5af3a94b68c9e2de3ae2ef57` | Month-2+ recurring sale verification & advance cancellation | Recurring Mandate Service |
| `EVAL-REVOCATION` | `backend/tests/test_mandate_revocation.py` | `32c101c474d1210061a770064ef0d342c18be3baf475dd723f764e619b885ca0` | Cryptographic mandate revocation status list & auto-cancellation | Mandate Revocation Service |
| `EVAL-PAYOUTS` | `backend/tests/test_marketplace_payouts.py` | `a4a1ace0d1386901b24ffd883eb43e5c752ca85296eee3181f738e0089f8b12e` | Two-sided node operator batch payouts & integer-cent margins | Marketplace Payout Service |
| `EVAL-NATIVE-OIDC` | `backend/tests/test_ap2_native_rail_and_oidc.py` | `b4f3d5b37b022a3e9749f5bab9993d4e74568713b3d4b285bf1198561cc6faec` | PayPal OIDC identity attestation & native AP2 gateway direct charge rail | OIDC & Native AP2 Gateway |
| `EVAL-WALLET` | `backend/tests/test_buyer_wallet.py` | `79965c82cac7a1d61293b580ea2a6236ecd314c2b2f54c808f1123009fccb4fd` | Air-gapped buyer wallet MCP, dry-run preview, step-up & multi-merchant keyring | Buyer Wallet & Enclave Keystore |
| `EVAL-AUDIT-RUN1` | `backend/tests/test_security_audit_run1_fixes.py` | `0d9167876a056113568489f977ba7cd3d17abfd02dc89a0244adc585eddce9b1` | Remediation suite for 16 security-audit run-1 findings | Full-Stack Security Hardening |
| `EVAL-JUDGE-HARNESS` | `scripts/judge_audit_harness.py` | `8c7c12018d39b814b1f9b5977d0152b5bcdf93c4019601fdc41e7b02583a993c` | End-to-end 9-check AP2 v0.2 & MCP 2024-11-05 judge verification harness | E2E Verification Harness |

## 2. Baseline Empirical Scorecard
- Baseline Commit: `5885d26` (`HEAD`)
- Test Suite Status: `792 passed, 9 skipped` (`python -m pytest backend/tests -q -n 4`, 188 vendored AP2 SDK conformance + 604 project tests)
- Judge Audit Harness: `9/9 checks passed (100% GREEN)` (`python scripts/judge_audit_harness.py`)
- Mock Inventory Gate: `PASSED` (22 active mocks, 4 retired in `docs/MOCKS.md`; `python scripts/check_mocks.py`)
- Frontend Production Build: `PASSED` (`npm run build` — `tsc -b && vite build`, 1,925 modules)
