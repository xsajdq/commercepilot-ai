"""Phase 21 load test - a full-stack check against a real running
`apps/api` process (see `tests/README.md`'s own definition of `e2e/`:
"full-stack tests against ... a user-facing flow worth covering end to
end"). Deliberately plain `httpx` + `asyncio`, no load-testing
framework: this codebase prefers owning small, direct tooling over a
new dependency for something this size (same reasoning as `cp_sync`'s
own retry helper).

What this measures: request latency (p50/p90/p99) and throughput for a
realistic mix of authenticated read endpoints, under concurrent
synthetic load, against a real Postgres + Redis-backed API process -
not a mock, not the in-process ASGI test client the pytest suite uses.

What this does NOT claim: this is a single sandboxed machine running
every virtual user against `localhost`, not a production-representative
environment (no real network latency, no realistic Postgres connection
pool sizing tuned for load, one CPU's worth of headroom). Treat the
numbers here as "does this regress" baseline, not "this is what
production can handle" - the same honesty this repo already applies to
docs/architecture/deployment.md's alert thresholds ("a starting point,
not calibrated against real traffic yet").

Usage:
    # Start the API with a relaxed rate limit for this run - the
    # default (120 req/min per IP across ALL non-auth routes, see
    # apps/api/app/core/rate_limit.py) exists to protect against abuse
    # from one source, which is exactly what many virtual users on one
    # test machine looks like. Raising it here measures the API's own
    # performance instead of re-proving the rate limiter works (Phase
    # 21c's own tests already cover that).
    RATE_LIMIT_DEFAULT_PER_MINUTE=100000 uvicorn app.main:app --port 8000

    python3 tests/e2e/load_test.py --base-url http://127.0.0.1:8000 \
        --users 10 --duration 20
"""

from __future__ import annotations

import argparse
import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field

import httpx


@dataclass
class Sample:
    endpoint: str
    status: int
    duration_s: float


@dataclass
class Results:
    samples: list[Sample] = field(default_factory=list)

    def add(self, sample: Sample) -> None:
        self.samples.append(sample)


async def _register_user(client: httpx.AsyncClient, index: int) -> str | None:
    email = f"loadtest-{uuid.uuid4().hex[:10]}-{index}@example.com"
    payload = {
        "email": email,
        "password": "supersecret123",
        "full_name": f"Load Test User {index}",
        "tenant_name": f"Load Test Shop {index}",
    }
    response = await client.post("/auth/register", json=payload)
    if response.status_code != 201:
        print(f"  ! setup: user {index} registration failed ({response.status_code})")
        return None
    return response.json()["access_token"]


async def _setup_users(base_url: str, count: int) -> list[str]:
    """Sequential, not concurrent: registration lives under the auth
    endpoints' own tighter rate limit (10/min by default), and setup
    isn't what this test is measuring anyway."""
    tokens: list[str] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        for i in range(count):
            token = await _register_user(client, i)
            if token:
                tokens.append(token)
    print(f"Set up {len(tokens)}/{count} virtual users.")
    return tokens


_ENDPOINTS = [
    "/analytics/dashboard",
    "/connections",
    "/products",
    "/recommendations",
    "/billing",
    "/catalog/audits",
]


async def _virtual_user(
    base_url: str, token: str, duration_s: float, results: Results
) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.monotonic() + duration_s
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0, headers=headers) as client:
        while time.monotonic() < deadline:
            endpoint = random.choice(_ENDPOINTS)
            start = time.perf_counter()
            try:
                response = await client.get(endpoint)
                status = response.status_code
            except httpx.HTTPError:
                status = 0
            results.add(Sample(endpoint=endpoint, status=status, duration_s=time.perf_counter() - start))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[index]


def _report(results: Results, duration_s: float) -> None:
    total = len(results.samples)
    if total == 0:
        print("No requests completed.")
        return

    durations_ms = [s.duration_s * 1000 for s in results.samples]
    by_status_family: dict[str, int] = {}
    for sample in results.samples:
        family = f"{sample.status // 100}xx" if sample.status else "error"
        by_status_family[family] = by_status_family.get(family, 0) + 1

    print()
    print("=== Load test report ===")
    print(f"Total requests:  {total}")
    print(f"Duration:        {duration_s:.1f}s")
    print(f"Throughput:      {total / duration_s:.1f} req/s")
    print(f"Status codes:    {by_status_family}")
    print(f"Latency p50:     {_percentile(durations_ms, 0.50):.1f}ms")
    print(f"Latency p90:     {_percentile(durations_ms, 0.90):.1f}ms")
    print(f"Latency p99:     {_percentile(durations_ms, 0.99):.1f}ms")
    print(f"Latency max:     {max(durations_ms):.1f}ms")

    print()
    print("By endpoint:")
    for endpoint in _ENDPOINTS:
        endpoint_durations = [
            s.duration_s * 1000 for s in results.samples if s.endpoint == endpoint
        ]
        if not endpoint_durations:
            continue
        print(
            f"  {endpoint:30s} n={len(endpoint_durations):5d}  "
            f"p50={_percentile(endpoint_durations, 0.50):6.1f}ms  "
            f"p99={_percentile(endpoint_durations, 0.99):6.1f}ms"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=10, help="concurrent virtual users")
    parser.add_argument("--duration", type=float, default=20.0, help="seconds per virtual user")
    args = parser.parse_args()

    tokens = await _setup_users(args.base_url, args.users)
    if not tokens:
        print("No users could be set up - aborting.")
        return

    results = Results()
    print(f"Running {len(tokens)} virtual users for {args.duration}s each...")
    start = time.monotonic()
    await asyncio.gather(
        *(_virtual_user(args.base_url, token, args.duration, results) for token in tokens)
    )
    elapsed = time.monotonic() - start

    _report(results, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
