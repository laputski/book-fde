from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    tool: str
    content: str
    is_error: bool = False
    code: str = ""


@dataclass(frozen=True)
class Request:
    tool: str
    timeout_s: float
    latency_s: float          # how long the system takes to answer: for the stub only


Handler = Callable[[Request], Awaitable[str]]


async def call_one(request: Request, handler: Handler) -> Observation:
    """One call with its own timeout: a failure is returned as an observation."""
    try:
        async with asyncio.timeout(request.timeout_s):
            return Observation(request.tool, await handler(request))
    except TimeoutError:
        return Observation(request.tool, f"no answer within {request.timeout_s} s",
                           True, "upstream_timeout")
    except ConnectionError as err:
        return Observation(request.tool, str(err), True, "upstream_error")


async def fan_out(requests: Sequence[Request], handler: Handler) -> list[Observation]:
    """All calls go out at once; the complete set of observations is returned."""
    return list(await asyncio.gather(*(call_one(r, handler) for r in requests)))


async def demo() -> tuple[list[Observation], float]:
    async def upstream(request: Request) -> str:
        await asyncio.sleep(request.latency_s)
        if request.tool == "get_carrier_status":
            raise ConnectionError("the carrier rejected the request: limit of 5 per second")
        return f"{request.tool}: done"

    requests = [
        Request("get_telematics", timeout_s=1.0, latency_s=0.05),
        Request("get_carrier_status", timeout_s=1.0, latency_s=0.05),
        Request("get_customs_status", timeout_s=0.02, latency_s=0.06),
    ]
    started = time.perf_counter()
    observations = await fan_out(requests, upstream)
    return observations, time.perf_counter() - started


if __name__ == "__main__":
    results, elapsed = asyncio.run(demo())
    by_tool = {o.tool: o for o in results}
    assert len(results) == 3                                   # one observation per call
    assert not by_tool["get_telematics"].is_error
    assert by_tool["get_carrier_status"].code == "upstream_error"
    assert by_tool["get_customs_status"].code == "upstream_timeout"
    assert elapsed < 0.12                                      # 0.12 s one after another
    ok = [o.tool for o in results if not o.is_error]
    assert ok == ["get_telematics"]
    print("three calls at once, two failures as observations, one useful result")
