from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from uuid import uuid4

import httpx


@dataclass
class Sample:
    endpoint: str
    status: int
    latency_ms: float
    expected: bool


class LoadRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.base_url = args.base_url.rstrip("/")
        self.email = os.environ["LOADTEST_EMAIL"]
        self.password = os.environ["LOADTEST_PASSWORD"]
        self.doctor_id = os.getenv("LOADTEST_DOCTOR_ID")
        self.slot_ids = [value for value in os.getenv("LOADTEST_SLOT_IDS", "").split(",") if value]
        self.duration = args.duration
        self.concurrency = args.concurrency
        self.samples: list[Sample] = []
        self.samples_lock = asyncio.Lock()
        self.slot_index = 0
        self.slot_lock = asyncio.Lock()
        self.elapsed_seconds = 0.0
        self.blocked_reasons: set[str] = set()

    async def record(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        expected_statuses: set[int],
        endpoint: str,
    ) -> httpx.Response:
        started = time.perf_counter()
        try:
            response = await client.request(method, path, json=json, headers=headers)
            status = response.status_code
        except httpx.HTTPError:
            response = httpx.Response(599, request=httpx.Request(method, path))
            status = 599
        sample = Sample(
            endpoint=endpoint,
            status=status,
            latency_ms=(time.perf_counter() - started) * 1000,
            expected=status in expected_statuses,
        )
        async with self.samples_lock:
            self.samples.append(sample)
        return response

    async def choose_slot(self, client: httpx.AsyncClient, doctor_id: str) -> str | None:
        if self.slot_ids:
            async with self.slot_lock:
                slot_id = self.slot_ids[self.slot_index % len(self.slot_ids)]
                self.slot_index += 1
            return slot_id
        response = await self.record(
            client,
            "GET",
            f"/api/v1/doctors/{doctor_id}/availability",
            expected_statuses={200},
            endpoint="availability",
        )
        if response.status_code != 200:
            self.blocked_reasons.add("availability_request_failed")
            return None
        available = [slot for slot in response.json() if slot.get("status") == "AVAILABLE"]
        if not available:
            self.blocked_reasons.add("no_available_slot")
        return available[0]["id"] if available else None

    async def worker(self, worker_id: int) -> None:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            login = await self.record(
                client,
                "POST",
                "/api/v1/auth/login",
                json={"email": self.email, "password": self.password},
                expected_statuses={200},
                endpoint="login",
            )
            if login.status_code != 200:
                return
            access_token = login.json().get("access_token")
            headers = {"Authorization": f"Bearer {access_token}"}
            doctor_id = self.doctor_id
            deadline = time.monotonic() + self.duration
            iteration = 0
            while time.monotonic() < deadline:
                await self.record(
                    client,
                    "GET",
                    "/health",
                    expected_statuses={200},
                    endpoint="health",
                )
                doctors = await self.record(
                    client,
                    "GET",
                    "/api/v1/doctors",
                    headers=headers,
                    expected_statuses={200},
                    endpoint="doctor_discovery",
                )
                if doctor_id is None and doctors.status_code == 200:
                    items = doctors.json().get("items", [])
                    if items:
                        doctor_id = items[0]["id"]
                if doctor_id is None:
                    self.blocked_reasons.add("no_doctor_found")
                    continue
                slot_id = await self.choose_slot(client, doctor_id)
                if slot_id is None:
                    continue
                await self.record(
                    client,
                    "POST",
                    "/api/v1/bookings",
                    headers=headers,
                    json={
                        "slot_id": slot_id,
                        "idempotency_key": f"loadtest-{worker_id}-{iteration}-{uuid4().hex}",
                    },
                    expected_statuses={201, 409},
                    endpoint="booking",
                )
                iteration += 1

    async def run(self) -> None:
        started = time.perf_counter()
        await asyncio.gather(*(self.worker(worker_id) for worker_id in range(self.concurrency)))
        self.elapsed_seconds = max(time.perf_counter() - started, 0.001)

    def report(self) -> int:
        by_endpoint: dict[str, list[Sample]] = defaultdict(list)
        for sample in self.samples:
            by_endpoint[sample.endpoint].append(sample)
        failures = 0
        print(
            "endpoint | requests | throughput_req_s | p50_ms | p95_ms | "
            "errors | expected_conflicts"
        )
        for endpoint, samples in sorted(by_endpoint.items()):
            latencies = sorted(sample.latency_ms for sample in samples)
            errors = [sample for sample in samples if not sample.expected]
            conflicts = [sample for sample in samples if sample.status == 409]
            failures += len(errors)
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
            print(
                f"{endpoint} | {len(samples)} | {len(samples) / self.elapsed_seconds:.2f} | "
                f"{p50:.2f} | {p95:.2f} | {len(errors)} | {len(conflicts)}"
            )
        if self.blocked_reasons:
            print(f"setup_bottlenecks | {','.join(sorted(self.blocked_reasons))}")
        return 0 if self.samples and failures == 0 and not self.blocked_reasons else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lightweight Amrutam API load test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--duration", type=int, default=30)
    return parser.parse_args()


async def async_main() -> int:
    runner = LoadRunner(parse_args())
    await runner.run()
    return runner.report()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(async_main()))
    except KeyError as exc:
        print(f"Missing required environment variable: {exc.args[0]}")
        raise SystemExit(2) from None
