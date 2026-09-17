from __future__ import annotations

import math
from dataclasses import dataclass

GIB = 2**30


@dataclass(frozen=True)
class ModelShape:
    """Иллюстративные размеры плотного трансформера, а не конкретная модель."""
    params_b: float            # миллиарды параметров
    layers: int
    kv_heads: int              # головы ключей и значений; при GQA их меньше голов запроса
    head_dim: int


@dataclass(frozen=True)
class Precision:
    weight_bytes: float        # байт на параметр: 2 для 16 бит, 1 для 8, около 0.55 для 4 бит
    kv_bytes: float            # байт на элемент KV-кэша


def weights_gib(m: ModelShape, p: Precision) -> float:
    return m.params_b * 1e9 * p.weight_bytes / GIB


def kv_gib(m: ModelShape, p: Precision, context: int) -> float:
    """Ключ и значение × слои × KV-головы × размер головы × байты × токены."""
    return 2 * m.layers * m.kv_heads * m.head_dim * p.kv_bytes * context / GIB


def max_sequences(m: ModelShape, p: Precision, gpu_gib: float, context: int,
                  reserve: float = 0.10, runtime_gib: float = 1.5) -> int:
    """Сколько последовательностей полной длины помещается в память одновременно."""
    free = gpu_gib * (1 - reserve) - runtime_gib - weights_gib(m, p)
    return max(0, math.floor(free / kv_gib(m, p, context)))


if __name__ == "__main__":
    mid = ModelShape(params_b=30, layers=60, kv_heads=8, head_dim=128)
    small = ModelShape(params_b=8, layers=32, kv_heads=8, head_dim=128)
    fp16, int8 = Precision(2.0, 2.0), Precision(1.0, 2.0)
    int4, int4_kv8 = Precision(0.55, 2.0), Precision(0.55, 1.0)

    assert round(weights_gib(mid, fp16), 1) == 55.9
    assert round(kv_gib(mid, fp16, 32_000), 2) == 7.32         # одна длинная последовательность
    assert max_sequences(mid, fp16, 80, 32_000) == 1
    assert max_sequences(mid, int8, 80, 32_000) == 5            # 8 бит: впятеро больше
    assert max_sequences(mid, int8, 80, 4_000) == 46            # короткий контекст: в девять раз больше
    assert max_sequences(mid, int4_kv8, 80, 32_000) == 15
    # На длинном контексте кэш вмещённых последовательностей больше самих весов.
    assert 5 * kv_gib(mid, int8, 32_000) > weights_gib(mid, int8)

    # Узел завода: карта на 24 ГиБ, контекст 8 тыс. токенов.
    assert max_sequences(small, int8, 24, 8_000) == 12
    assert max_sequences(small, fp16, 24, 8_000) == 5
    assert max_sequences(mid, int4, 24, 8_000) == 2
    assert max_sequences(mid, fp16, 24, 8_000) == 0             # веса не помещаются вовсе
    fits = {name: max_sequences(mid, p, 80, 32_000)
            for name, p in (("fp16", fp16), ("int8", int8), ("int4+kv8", int4_kv8))}
    print("последовательностей на 80 ГиБ при 32 тыс. токенов:", fits)
