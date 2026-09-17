# packages/policies (`cp_policies`)

Phase 8's approval engine: the `Recommendation -> PendingApproval ->
Approved/Rejected -> Executing -> Success/Failed` workflow CONTRIBUTING.md's
control flow ends in, for anything `cp_ai.ToolExecutor` gates above `LOW`
risk (Phase 7). No HTTP routes yet - this is the engine only, tested via
`apps/api`'s DB-integration suite; an approval queue UI/API is later
work once there's a caller (an agent, Phase 9+) actually proposing
things.

## `cp_policies.approval_engine`

- **`propose_recommendation(db, ...)`** - records an AI-proposed action,
  `PROPOSED`. `tool_name`/`tool_arguments` are stored in `payload`
  exactly as a blocked `ToolExecutor.execute()` call was made - the AI
  gets one shot at what it's asking for, not a second one after a human
  has already read and approved the first.
- **`submit_for_approval(db, recommendation)`** - moves a `PROPOSED`
  recommendation into the human queue (`PENDING_APPROVAL` + a `PENDING`
  `Approval` row). This is where a real Policy Engine would run further
  checks before a human ever sees it - Phase 8 keeps it a pass-through;
  raises `RecommendationNotPendingError` if the recommendation isn't
  `PROPOSED`.
- **`approve(db, registry, ...)`** - approves and immediately resumes
  execution: resolves the stored `tool_name` in the given
  `ToolRegistry`, re-validates `tool_arguments` against the tool's own
  `args_model`, and calls its handler *directly* (never through
  `ToolExecutor.execute()` again - that would just re-hit the same risk
  gate and come back `requires_approval` forever). Always ends at a
  terminal status, `SUCCESS` or `FAILED` - never left `EXECUTING` -
  whether the tool ran cleanly, returned its own failure, raised, or the
  stored tool name/arguments turned out to be bad. Writes a real
  `AuditEvent` (`approval_id` set) for a `mutates` tool either way,
  exactly like `ToolExecutor` does for an auto-executed low-risk one.
- **`reject(db, ...)`** - marks the recommendation `REJECTED`. Never
  calls anything, never writes an audit log - nothing was mutated.

Both `approve` and `reject` scope every lookup by `tenant_id` and raise
`RecommendationNotFoundError`/`RecommendationNotPendingError` rather than
silently doing nothing - a decision is made exactly once, and never
across a tenant boundary.

## Known simplification

Approving is not protected against a concurrent double-approval race
(no row locking) - acceptable for Phase 8 (single approver flows,
no UI yet), worth revisiting once there's an approval queue multiple
people can act on at once.

Run this package's own tests (state-machine guards, using a mocked
`AsyncSession` - no DB needed):

```bash
cd packages/policies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

DB-integration coverage (the full propose -> submit -> approve loop
actually running `cp_ai`'s `update_price` tool and persisting a real
`AuditEvent`, plus the reject path and tenant isolation) lives in
`apps/api/tests/test_approval_engine.py`, reusing that app's Postgres
test fixtures - same reasoning as `packages/sync` and `packages/ai`.
