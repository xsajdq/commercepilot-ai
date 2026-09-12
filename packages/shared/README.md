# packages/shared

Cross-cutting utilities used by more than one app/package (e.g. tenant
context helpers, common Pydantic types). Kept intentionally empty until
real duplication between `apps/api`, `apps/worker`, and the other
`packages/*` shows up — no speculative utilities.
