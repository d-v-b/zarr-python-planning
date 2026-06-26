"""Metrics and tracing surface for Zarr-Python v4.

Source: [proposals/observability.md](../proposals/observability.md)
"""

from __future__ import annotations

from dataclasses import dataclass

# ``Tracer`` is the OpenTelemetry tracer type; it is referenced by bare name in
# annotations and is never imported at runtime so this module stays dependency
# free.

__all__ = [
    "Metrics",
    "metrics_process_wide",
    "enable_opentelemetry",
    "SPAN_NAMES",
]


@dataclass
class Metrics:
    """Mutable bag of counters describing store, cache, and compute activity.

    Source: [proposals/observability.md](../proposals/observability.md)
    """

    store_get_count: int = 0
    store_get_bytes: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_dedup_hits: int = 0
    coalesce_groups: int = 0
    coalesce_wasted_bytes: int = 0
    decode_seconds_total: float = 0.0
    compute_concurrency_inflight: int = 0
    compute_concurrency_waited: float = 0.0

    def reset(self) -> None:
        """Reset all counters to their initial values.

        Source: [proposals/observability.md](../proposals/observability.md)
        """
        ...


metrics_process_wide: Metrics = Metrics()
"""Opt-in process-wide aggregator of :class:`Metrics`.

Source: [proposals/observability.md](../proposals/observability.md)
"""


def enable_opentelemetry(tracer: Tracer | None = None) -> None:
    """Enable OpenTelemetry auto-instrumentation; zero-cost when no tracer set.

    Source: [proposals/observability.md](../proposals/observability.md)
    """
    ...


SPAN_NAMES: tuple[str, ...] = (
    "zarr.store.get",
    "zarr.codec.decode",
    "zarr.array.read_selection",
    "zarr.engine.read_chunk",
    "zarr.cache.hit",
)
"""Conventional span names emitted by the instrumented code paths.

Source: [proposals/observability.md](../proposals/observability.md)
"""
