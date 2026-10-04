# Durable dispatch registration implementation plan

Goal: implement the safe, testable pre-submission foundation and record exact production activation blockers.

Spec: [dispatch-registration-design.md](dispatch-registration-design.md). Continue on the existing Draft PR branch; no natural runs, POSTs, policy mutations, secrets or changed frozen bindings. Production guard remains closed.

1. `oracle_dispatch.py` / `test_oracle_dispatch.py`: write failing tests for closed/hash-chained append-only journal, state transitions, duplicate/run-attempt reservations, independent store acknowledgment, crash/lost response, all rerun shapes and inability of a local journal to establish all-dispatch completeness. Implement pure journal validation and injected adapter broker; no live-dispatch CLI. Run tests and record results.
2. `test_oracle_attempts.py`: add metadata-only counterexamples for pre-registration-only history, policy-rejected deleted tail and a manual rerun missing from the broker's requests. Existing production G1 must refuse these histories; do not change scientific evaluator.
3. Link the design/status from Slice C0; run relevant tests, frozen-chain/base audit and documentation validation. Independent scoped review of journal and bypass boundary. Commit/push to Draft PR26 and inspect CI; do not merge or dispatch pilot.

Ruling: the App-policy route cannot be declared authoritative from current docs, since disallowed workflow runs may still exist as failures. Pre-registration is implemented as a foundation and cannot unlock the production gate; cost of a wrong ruling would be a false G1 PASS. Backend activation remains pending a verified all-event capture source.
