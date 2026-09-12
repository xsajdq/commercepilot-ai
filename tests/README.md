# Cross-cutting tests

Tests specific to one app/package live next to it (e.g. `apps/api/tests`).
This tree is for tests that span multiple services:

- `unit/` — pure logic tests spanning `packages/*` without any app.
- `integration/` — tests exercising apps together (e.g. API + worker via a
  real queue), added once there's more than one service to integrate.
- `e2e/` — full-stack tests against the Docker Compose stack, added once
  there's a user-facing flow worth covering end-to-end.

Empty for now — Phase 0 has no cross-service behavior yet to test.
