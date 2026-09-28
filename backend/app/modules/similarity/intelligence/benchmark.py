"""Reproducible local benchmarks for the retrieval pipeline."""

from dataclasses import dataclass, asdict
import time
import tracemalloc
from typing import Callable, Sequence


@dataclass(frozen=True)
class SimilarityBenchmark:
    corpus_chunks: int
    queries: int
    elapsed_ms: float
    peak_memory_bytes: int
    throughput_queries_per_second: float
    candidate_bound: int

    def as_dict(self) -> dict[str, int | float]:
        return asdict(self)


def benchmark_retrieval(
    query_fn: Callable[[str, int], Sequence[object]],
    queries: Sequence[str],
    *,
    corpus_chunks: int,
    candidate_bound: int,
) -> SimilarityBenchmark:
    """Benchmark a real provider with explicit corpus and candidate bounds."""

    tracemalloc.start()
    started = time.perf_counter()
    for query in queries:
        result = query_fn(query, candidate_bound)
        if len(result) > candidate_bound:
            raise AssertionError("retriever exceeded its candidate bound")
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return SimilarityBenchmark(
        corpus_chunks=corpus_chunks,
        queries=len(queries),
        elapsed_ms=elapsed * 1000,
        peak_memory_bytes=peak,
        throughput_queries_per_second=(len(queries) / elapsed) if elapsed else 0.0,
        candidate_bound=candidate_bound,
    )
