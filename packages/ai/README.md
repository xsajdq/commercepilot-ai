# packages/ai (`cp_ai`)

Phase 7's tool system - the only way an AI agent (starting Phase 9) is
ever allowed to touch anything. Agents, prompts, and the `AIProvider`
abstraction land later, alongside the first agent that actually needs
them; this package only has to exist first because CLAUDE.md requires
every AI action to go through an explicitly defined, permissioned tool -
never `execute_sql`, never an arbitrary HTTP request.

## `cp_ai.tools`

The control flow from CLAUDE.md, minus the Policy Engine and the real
Approval workflow (both Phase 8):

```
AI -> Tool -> Validation -> [Policy] -> Risk -> Approval
    -> Execution -> Audit Log
```

- **`ToolContext`** - a tool call's `tenant_id` and actor identity.
  Always constructed by the caller from the authenticated session/AI
  job, never from a tool argument - a tool's `args_model` is refused at
  registration time if it declares a `tenant_id` field at all
  (`UnsafeToolSchemaError`), so there's no argument for even a
  prompt-injected model to smuggle one through (CLAUDE.md #7, #18).
- **`ToolResult`** - `success`/`data`/`error`, plus `entity_type`/
  `entity_id`/`before`/`after` for mutations, which feed straight into
  the `AuditEvent` the executor writes. `ToolResult.pending_approval(...)`
  is what a gated tool call returns instead of running.
- **`ToolSchema`** - one AI-callable tool: name, description, a Pydantic
  `args_model` (also its JSON schema, via `.input_schema()`, for
  handing to an `AIProvider`'s tool-use API), a `ToolPermission`, and the
  `handler` that does the work.
- **`ToolPermission`** - `risk_level` (`LOW`/`MEDIUM`/`HIGH`) and
  `mutates`. `requires_approval` is `True` for anything above `LOW`
  (CLAUDE.md #4). Tracked separately from `mutates` because they answer
  different questions: risk decides whether a human has to sign off
  first; `mutates` decides whether a successful run gets an audit log
  (CLAUDE.md #5) - a high-risk read needs approval but audits nothing,
  a low-risk write is auditable but never blocks.
- **`ToolRegistry`** - registers/looks up tools by name, and produces
  `tool_definitions()` in the name/description/input_schema shape most
  tool-use APIs expect.
- **`ToolExecutor`** - runs the chain above for one `ToolCall`: resolve
  the tool, validate arguments, short-circuit to
  `ToolResult.pending_approval(...)` for anything above `LOW` risk
  (Phase 8 is what turns this into a real `Recommendation`/`Approval`
  row and resumes execution once a human approves it - until then this
  is a hard stop, no handler call, no mutation), otherwise call the
  handler and write an `AuditEvent` if the tool mutates, whether the
  handler succeeded or not. A handler's own exception is caught and
  turned into a failed `ToolResult` - a single bad tool call must never
  crash the caller.

## `cp_ai.tools.builtin`

Two concrete tools proving the framework works end to end against real
`cp_domain` data (`register_builtin_tools(registry)` registers both):

- **`get_product`** (`LOW` risk, read-only) - looks up one of the
  caller's products by SKU. Runs immediately, never audited (it's not a
  mutation).
- **`update_price`** (`HIGH` risk, mutates) - changes an offer's price
  in *our own* domain model only. It deliberately does not push the
  change to the marketplace: per CLAUDE.md #2 ("every external mutation
  must go through a typed connector") and #10 ("deterministic business
  calculations... must not be delegated to an LLM"), pushing a real
  price change is the pricing agent's job (Phase 9), built on the
  deterministic pricing engine - not something a generic tool does on an
  AI's say-so. Its only purpose here is to prove the approval gate:
  `ToolExecutor` never lets `update_price_handler` run without Phase 8's
  approval workflow, so calling it through the executor always comes
  back as `requires_approval` with the price untouched.

Run this package's own tests (registry + executor mechanics, using a
mocked `AsyncSession` - no DB needed):

```bash
cd packages/ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

DB-integration coverage (tenant isolation, the approval gate leaving the
price untouched, and a real `AuditEvent` row for a low-risk mutation)
lives in `apps/api/tests/test_ai_tools.py`, reusing that app's Postgres
test fixtures - same reasoning as `packages/sync`.
