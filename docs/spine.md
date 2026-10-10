# Constitutional Invariants (The Law)
<!-- SPEC-001 v1.9.0 Pillar 1 | Mutability: IMMUTABLE (Human-Only) -->

## Non-Negotiable Domain Axioms
1. Determinism First: No silent fallbacks, unverified mocks, or unhandled exceptions in production pathways.
2. Invariant Protection: Agents MUST NOT mutate `spine.md` or relax validation gates.
3. Secret Hygiene: Zero plaintext secrets, API keys, or credentials committed to git.

## Deterministic Verification Gates
- Static Analysis: Must pass configured linters (`ruff`, `flake8`, `eslint`, etc.) with zero warnings.
- Test Coverage Baseline: Line coverage must not drop below established thresholds.
- Corpus Verification: Fixture integrity must pass `python audit_evals_corpus.py`.

## Absolute Forbidden Operations
- Destructive git operations (`git push --force`, `git reset --hard` on tracked remote branches).
- Bypassing pre-commit hooks via `--no-verify` (enforced via agent harness permission boundary).
- Reading `sessions/*.md` flight recorder archives during Turn 1 boot hydration.
