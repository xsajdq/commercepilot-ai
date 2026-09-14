# Cross-cutting tests

Tests specific to one app/package live next to it (e.g. `apps/api/tests`).
This tree is for tests that span multiple services:

- `unit/` — pure logic tests spanning `packages/*` without any app.
- `integration/` — tests exercising apps together (e.g. API + worker via a
  real queue), added once there's more than one service to integrate.
- `e2e/` — full-stack tests against the Docker Compose stack, added once
  there's a user-facing flow worth covering end-to-end. `e2e/load_test.py`
  (Phase 21) is the first thing here - see `e2e/README.md`.

`unit/` and `integration/` are still empty - nothing cross-service to
test in those two yet.
