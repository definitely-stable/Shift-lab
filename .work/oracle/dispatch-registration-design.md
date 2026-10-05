# Slice C0 durable dispatch registration

Status: **IMPLEMENTATION FOUNDATION; PRODUCTION CAPTURE BLOCKED**. Natural oracle and G1 remain NOT_RUN. This design does not remove `DISPATCH_HISTORY_UNVERIFIED` or change the frozen scientific contract.

## Requirement and trust boundary

Preserve every dispatched pilot attempt, including pre-checkout failure, cancellation, refusal, manual UI/API dispatch and each full/failed-job/single-job rerun. Registering only attempts that execute a job, or only admitted attempts, would weaken the user's invariant. No natural dispatch, measurement, account provisioning or permission change is authorized by this implementation step. All pilot/PR workflows remain read-only and secret-free apart from their standard read token. No paid or external compute is introduced.

The local operator request is distinct from a GitHub attempt: an intent has no assigned run ID until independently bound. An unacknowledged intent cannot be discarded or considered proof that no run was created. A local journal alone is not independently durable; registration requires exact read-back acknowledgment from its external backing store before any submission. The backing store, its immutable anchor and capture of bypass attempts must be reviewed and provisioned before production activation.

## Current capability evidence (2026-10-05 local)

Read-only queries against `definitely-stable/Shift-lab` found a public organization repository with admin access, zero repository Actions policies, organization plan `free`, and HTTP404 from the organization audit-log API. The pilot workflow is not yet present on default main (HTTP404); PR26 is Draft at `8c144ca8338f858a6c26135bcaa0275bf9899c47`. These are observations at the time of design, not permanent capability claims. HTTP404 does not distinguish all possible entitlement/scope causes; no audit source was verified. Existing general-purpose app installations are not an exclusive broker identity and will not be repurposed as one.

## Alternatives evaluated

| Route | What it preserves | Why it does not yet prove the full invariant |
|---|---|---|
| Actions artifact/API inventory | Observed run IDs and reruns | Trailing run deleted before observation is invisible; runner loss before bootstrap can leave no artifact |
| Pre-registration CLI alone | Every request made through that CLI | UI/API bypass is possible; a human token can be used outside the broker |
| Dedicated App broker + workflow actor policy | Broker requests before POST, constrains execution | [Policies](https://docs.github.com/en/actions/concepts/about-actions-policies) describe disallowed runs failing with an error, not a guarantee that no run is created. Rejected bypass dispatches still fall within the user's invariant. Rerun actor behavior is not specified by this policy documentation |
| Async workflow/webhook observer | Delivered creation/status events | Observer failure, delivery retention and missing rerun request events require independent completeness proof. [Failed webhooks](https://docs.github.com/en/webhooks/using-webhooks/handling-failed-webhook-deliveries) are not automatically redelivered |
| Provider audit creation/rerun events + durable capture | Can include bypass and deleted run events independently of run inventory | The source must be accessible and its coverage, lag, retention and gaps verified. No such source is available through the current tested credentials |

[Execution controls](https://docs.github.com/en/actions/how-tos/administer/control-workflow-execution) are available for public repos and may target an App and exact workflow path. [REST policies](https://docs.github.com/en/rest/actions/policies) are separate control-plane configuration. [Rerun APIs](https://docs.github.com/en/rest/actions/workflow-runs) expose full, failed-job and single-job routes; [context](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts) distinguishes original actor and triggering actor. None of these sources establishes the missing all-event capture by itself. GitHub documents audit events `workflows.created_workflow_run` and `workflows.rerun_workflow_run` in its [audit-event reference](https://docs.github.com/en/organizations/keeping-your-organization-secure/managing-security-settings-for-your-organization/audit-log-events-for-your-organization).

## Implemented broker foundation

[oracle_dispatch.py](../tools/oracle_dispatch.py) implements a closed append-only intent journal and submission state machine with injected storage/submission adapters. It provides no live-dispatch CLI or production-unlock option. Tests use fake adapters and synthetic identities only; no GitHub POST or natural workflow is invoked.

Each immutable event contains sequence, previous event digest, intent ID, action, canonical closed data and event digest. Journal validation checks exact fields, canonical digest chain, monotonically increasing sequence, unique intent creation, valid state transitions and append-only comparison to an independently retained base. Payload is only repository/ref/source/measurement identity, operation and run/attempt/job binding; exception strings, tokens and evaluation costs are never stored.

Operations: `dispatch`, `rerun_all`, `rerun_failed`, `rerun_job`. All rerun operations require the same run ID and exact expected next attempt, with job ID only for the job route. Reusing a run/attempt reservation or submitting another request while one is unresolved is refused. The caller serializes registration across the backing store; optimistic exact-base comparison prevents stale writers from replacing another registration.

State sequence:

1. `REGISTERED`: write and independently read back exact journal bytes before submission can become possible.
2. `SUBMITTING`: write and read back this transition **before** invoking the submit adapter. Only this call site submits. A crash now remains uncertain, even if it preceded the HTTP call.
3. `ACKNOWLEDGED`: append only a closed exact run/attempt binding after an unambiguous adapter response. The current [dispatch REST API](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event) documents a 200 response with the workflow run ID. A 204/201 with no exact binding, lost response, timeout or exception produces `UNRESOLVED`; it cannot become NOT_DISPATCHED or be automatically retried. A provider run ID alone still requires exact source/ref/attempt verification by the future adapter.
4. `UNRESOLVED`: permanent blocker in this implementation, which supplies no resolution API. A future verified backend must define separate authoritative reconciliation to a matching run/attempt binding. Retrying the same intent is refused. The failed record remains in history; a subsequent success cannot erase it.

An acknowledged dispatch still needs a retained verified bundle. A journal with two acknowledged good requests proves those two requests, not absence of a third bypass. `history_blockers()` therefore always includes `DISPATCH_HISTORY_UNVERIFIED`; unresolved/registering requests add their own blocker. The existing production worker and G1 guards stay unchanged. The module is an offline foundation for a future provisioned controller, not a functioning production controller.

## Activation acceptance criteria

- Verify independent capture of every created/rejected/cancelled dispatch and every rerun route, including no-job/pre-bootstrap events, with source/run/attempt bindings.
- Establish and retain genesis before the first pilot dispatch; demonstrate complete, bounded-lag event coverage through each G1 evaluation. Capture gaps and ambiguous coverage permanently block PASS until resolved from an authoritative source.
- Provision exclusive broker identity, exact workflow actor/event controls, immutable journal backing and read-only pilot/G1 receipt verification. Verify the actual server behavior for direct UI/API dispatch, full rerun, failed-job rerun and single-job rerun on a synthetic-only workflow.
- Prove journal durability before POST, compare remote acknowledgment against an independently retained head, block stale/concurrent writers and preserve lost responses; never blindly retry POST.
- Reconcile journal, independent event history, GitHub inventory, attempt sidecars and verified bundles as sets. Missing/extra/mismatched events block PASS; scientific G1 receives all attempts of its identity unchanged.
- Change the production history guard only in a reviewed implementation after these criteria are supported by actual backend evidence. App allowlist, operator declaration, local hash chain, fake source or healthy API listing cannot waive the guard.

Activation requires a verified capture source and associated control-plane access. The current read-only workflow configuration and observed Free organization do not supply that source. This is the concrete remaining infrastructure dependency; no scientific semantics or thresholds are weakened to avoid it.
