from __future__ import annotations

import math
from dataclasses import dataclass

GIB = 2**30


@dataclass(frozen=True)
class ModelShape:
    """Illustrative dimensions of a dense transformer, not a specific model."""
    params_b: float            # billions of parameters
    layers: int
    kv_heads: int              # key-value heads; with GQA fewer than the query heads
    head_dim: int


@dataclass(frozen=True)
class Precision:
    weight_bytes: float        # bytes per parameter: 2 at 16 bits, 1 at 8, about 0.55 at 4 bits
    kv_bytes: float            # bytes per KV cache element


def weights_gib(m: ModelShape, p: Precision) -> float:
    return m.params_b * 1e9 * p.weight_bytes / GIB


def kv_gib(m: ModelShape, p: Precision, context: int) -> float:
    """Key and value × layers × KV heads × head size × bytes × tokens."""
    return 2 * m.layers * m.kv_heads * m.head_dim * p.kv_bytes * context / GIB


def max_sequences(m: ModelShape, p: Precision, gpu_gib: float, context: int,
                  reserve: float = 0.10, runtime_gib: float = 1.5) -> int:
    """How many full-length sequences fit into memory at once."""
    free = gpu_gib * (1 - reserve) - runtime_gib - weights_gib(m, p)
    return max(0, math.floor(free / kv_gib(m, p, context)))


if __name__ == "__main__":
    mid = ModelShape(params_b=30, layers=60, kv_heads=8, head_dim=128)
    small = ModelShape(params_b=8, layers=32, kv_heads=8, head_dim=128)
    fp16, int8 = Precision(2.0, 2.0), Precision(1.0, 2.0)
    int4, int4_kv8 = Precision(0.55, 2.0), Precision(0.55, 1.0)

    assert round(weights_gib(mid, fp16), 1) == 55.9
    assert round(kv_gib(mid, fp16, 32_000), 2) == 7.32         # one long sequence
    assert max_sequences(mid, fp16, 80, 32_000) == 1
    assert max_sequences(mid, int8, 80, 32_000) == 5            # 8 bits: five times as many
    assert max_sequences(mid, int8, 80, 4_000) == 46            # short context: nine times as many
    assert max_sequences(mid, int4_kv8, 80, 32_000) == 15
    # At long context the cache of the fitted sequences outweighs the weights.
    assert 5 * kv_gib(mid, int8, 32_000) > weights_gib(mid, int8)

    # The plant node: a 24 GiB card, an 8k-token context.
    assert max_sequences(small, int8, 24, 8_000) == 12
    assert max_sequences(small, fp16, 24, 8_000) == 5
    assert max_sequences(mid, int4, 24, 8_000) == 2
    assert max_sequences(mid, fp16, 24, 8_000) == 0             # the weights do not fit at all
    fits = {name: max_sequences(mid, p, 80, 32_000)
            for name, p in (("fp16", fp16), ("int8", int8), ("int4+kv8", int4_kv8))}
    print("sequences on 80 GiB at 32k tokens:", fits)
