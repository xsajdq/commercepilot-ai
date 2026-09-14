# E2E: load test (Phase 21)

`load_test.py` - a full-stack load test against a real running
`apps/api` process (real Postgres + Redis, not a mock or the pytest
suite's in-process ASGI client). Plain `httpx` + `asyncio`, no
load-testing framework - see the script's own module docstring for
the reasoning and for exactly what it measures and doesn't claim.

## Running it

```bash
# From apps/api's own venv (needs httpx, already a dependency there).
cd apps/api && source .venv/bin/activate

# Start the API with a relaxed rate limit for this run - see the
# script's docstring for why (Phase 21c's per-IP limiter would
# otherwise dominate the results, since every virtual user here shares
# one source IP).
DATABASE_URL=... REDIS_URL=... SECRET_KEY=... \
  RATE_LIMIT_DEFAULT_PER_MINUTE=100000 RATE_LIMIT_AUTH_PER_MINUTE=1000 \
  uvicorn app.main:app --port 8000 &

cd ../..
python3 tests/e2e/load_test.py --base-url http://127.0.0.1:8000 \
  --users 10 --duration 20
```

## Real run recorded while building this phase

10 concurrent virtual users, each registered as their own tenant, each
looping GET requests for 20s against a realistic mix of authenticated
read routes (`/analytics/dashboard`, `/connections`, `/products`,
`/recommendations`, `/billing`, `/catalog/audits`) - against a real
local Postgres + Redis, with `apps/worker` idle:

```
Total requests:  2781
Duration:        20.5s
Throughput:      135.4 req/s
Status codes:    {'2xx': 2781}
Latency p50:     57.4ms
Latency p90:     104.8ms
Latency p99:     234.1ms
Latency max:     877.1ms
```

Zero errors across every endpoint tested, and Prometheus's own
`http_requests_total` (`/metrics`) independently counted the same
traffic (2792, including the 10 setup registrations and a few health
checks) - cross-confirming the app's own metrics pipeline reports real
numbers under real concurrent load, not just single-request smoke
tests.

As the script's own docstring says: this is a "does this regress"
baseline from one sandboxed machine, not a production capacity claim.
Re-run it after a change that touches a hot path (a new N+1 query, a
heavier serializer, a new piece of middleware) and compare against
these numbers.
