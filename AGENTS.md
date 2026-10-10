# Rules for coding agents in this repository

These rules apply to every task in this repo. The owner has an independent reviewer re-run attacks and checks after every report, so shortcuts get caught. When a rule blocks you, stop and say so in your report.

## Security rules

1. **Verify first.** Mandate and signature verification runs before anything else. No cache, lookup or replay path may return data or take an action until the caller has presented a valid mandate.
2. **Fail closed.** If a check can't read or evaluate its input (a constraint is missing, a parse fails, a type is unknown), refuse. Never write checks like `if value and value != expected`, which pass when the value is missing. Never swallow parse errors with `except: pass`.
3. **Use the vendored Google AP2 SDK** in `backend/vendor/ap2` to parse, verify and evaluate constraints. Don't hand-write SD-JWT parsing. Don't edit vendored files. If one truly must change, record it in `backend/vendor/ap2/NOTICE` and call it out in your report.
4. **Trust roots come only from the key registry,** enrolled through the challenge flow. Never trust a key from a token header, a request body or an environment variable. Never overwrite a registered key.
5. **Keys stay separated.** The buyer agent never imports, holds or uses the owner's key; it signs only closed mandates, with its own key. The server signs owner limits only in mock mode.
6. **Money is integer cents.** Compute in cents first; never multiply dollar floats and truncate. The SDK's `Budget.max` is dollars, so derive it from a cents total.
7. **Never weaken a check or a test to make something pass.** That covers deleting, skipping, loosening asserts and adding default values that bypass a check.
8. **Don't reorder or move security checks silently.** If you change the order checks run in, say so in your report and add a test showing the old protection still holds.
9. **No live network calls.** Run with `MOCK_EXTERNAL_APIS=true`. No PayPal sandbox or AI-provider calls unless the owner approves that specific run. Never send an API key to any host except the one that issued it.

## Before you change shared code

`seller_agent.purchase_subscription` and `verify_ap2_chains` sit on every purchase path. Before you change either one:
- list their callers;
- list what your change could break;
- check that `backend/tests/test_security_regressions.py` still passes.

## Tests

- `backend/tests/test_security_regressions.py` belongs to the owner's reviewer. **Don't edit, skip or delete it.** Tests marked `KNOWN_ISSUE` are open findings. When your fix makes one pass, pytest reports `XPASS(strict)`: remove only that marker, in the same commit as the fix.
- Run tests from the repo root with `python -m pytest backend/tests -q -n 4`, so the temp-database isolation in `conftest.py` applies. Tests must never touch `backend/data/a2a_commerce.db`.
- Before reporting, run the full test suite and `npm run build`. `npx tsc --noEmit -p .` checks nothing here.

## Reports

- Paste raw command output, copied rather than retyped. Never present a summary as if it were output.
- List every behavior change, including ones nobody asked for.
- Report dev database row counts by status after your runs.

## Scope

- Work only inside this repository. Commit locally; never push.
- **Never discard changes you didn't make.** If the working tree has edits you don't recognize, don't run `git checkout`, `git restore`, `git stash` or `git reset` on them. Leave them in place, stage only your own files by path, and mention the unrecognized changes in your report. The owner's reviewer may have added them.
- Never `pip install ap2` from PyPI. That name belongs to an unrelated package; the real SDK is vendored here.
