"""Engine wrapping the ``zarrs`` Rust implementation for Zarr-Python v4.

Source: [proposals/performance.md](../proposals/performance.md)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zarr.metadata import ArrayMetadata, Selection
    from zarr.store import Store

# Scalar aliases with no canonical owner; declared locally for a standalone import.
CodecPipeline = Any  # owned elsewhere (ordered codec bundle)
NDArrayLike = Any  # owned elsewhere (array-like buffer)

__all__ = ["ZarrsEngine"]


class ZarrsEngine:
    """Engine wrapping the ``zarrs`` Rust implementation (opt-in dependency).

    Source: [proposals/performance.md](../proposals/performance.md)
    """

    def read_chunk(
        self,
        store: Store,
        metadata: ArrayMetadata,
        coords: tuple[int, ...],
        codecs: CodecPipeline,
        selection: Selection | None = None,
    ) -> NDArrayLike:
        """Read and decode a single chunk via ``zarrs``.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...

    def read_selection(
        self,
        store: Store,
        metadata: ArrayMetadata,
        selection: Selection,
        codecs: CodecPipeline,
    ) -> NDArrayLike:
        """Read and decode an arbitrary selection via ``zarrs``.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...

    def write_chunk(
        self,
        store: Store,
        metadata: ArrayMetadata,
        coords: tuple[int, ...],
        data: NDArrayLike,
        codecs: CodecPipeline,
    ) -> None:
        """Encode and write a single chunk via ``zarrs``.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...

    def write_selection(
        self,
        store: Store,
        metadata: ArrayMetadata,
        selection: Selection,
        data: NDArrayLike,
        codecs: CodecPipeline,
    ) -> None:
        """Encode and write an arbitrary selection via ``zarrs``.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...
