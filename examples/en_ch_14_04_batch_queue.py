from __future__ import annotations

import heapq
from dataclasses import dataclass, field

ONLINE, BATCH = 0, 1                       # the smaller number is popped first


@dataclass
class TokenBucket:
    """A token limiter: a refill rate and a capacity for bursts."""
    rate: float                            # tokens per second: the per-minute quota / 60
    burst: float                           # how much can be spent at once
    level: float = 0.0
    updated: float = 0.0

    def take(self, n: int, now: float, keep: float = 0.0) -> bool:
        self.level = min(self.burst, self.level + (now - self.updated) * self.rate)
        self.updated = now
        if self.level - n < keep:
            return False
        self.level -= n
        return True


@dataclass(order=True)
class Job:
    priority: int
    seq: int
    tokens: int = field(compare=False)
    name: str = field(compare=False)


@dataclass
class Scheduler:
    bucket: TokenBucket
    batch_limit: int                       # batch queue length beyond which submissions are refused
    online_reserve: float                  # bucket tokens the batch may not take
    heap: list[Job] = field(default_factory=list)
    seq: int = 0
    batch_waiting: int = 0

    def submit(self, name: str, tokens: int, priority: int) -> bool:
        if tokens > self.bucket.burst:
            raise ValueError(f"{name}: {tokens} tokens will never pass the limiter")
        if priority == BATCH and self.batch_waiting >= self.batch_limit:
            return False                   # backpressure: the producer waits
        self.seq += 1
        heapq.heappush(self.heap, Job(priority, self.seq, tokens, name))
        if priority == BATCH:
            self.batch_waiting += 1
        return True

    def dispatch(self, now: float) -> list[str]:
        sent: list[str] = []
        while self.heap:
            job = self.heap[0]
            keep = 0.0 if job.priority == ONLINE else self.online_reserve
            if not self.bucket.take(job.tokens, now, keep):
                break                      # the head of the queue waits for a refill
            heapq.heappop(self.heap)
            if job.priority == BATCH:
                self.batch_waiting -= 1
            sent.append(job.name)
        return sent


if __name__ == "__main__":
    bucket = TokenBucket(rate=1_000, burst=12_000, level=12_000)
    sched = Scheduler(bucket, batch_limit=20, online_reserve=5_000)
    accepted = [sched.submit(f"b{i}", 1_200, BATCH) for i in range(30)]
    assert accepted.count(False) == 10                  # ten documents were not accepted
    assert sched.dispatch(now=0.0) == [f"b{i}" for i in range(5)]
    assert bucket.level >= 5_000                        # the online reserve is untouched

    sched.submit("inspect-17", 3_500, ONLINE)           # an engineer's request at the line
    assert sched.dispatch(now=0.5)[0] == "inspect-17"   # ahead of fifteen batch documents

    sent, t = 5, 0.5
    while sched.heap:
        t += 1.0
        sent += len(sched.dispatch(now=t))
    assert (sent, t) == (20, 20.5)
    assert sched.submit("b30", 1_200, BATCH)            # the queue has room again
    print(f"a batch of 20 documents took {t:.1f} s, online did not wait")
