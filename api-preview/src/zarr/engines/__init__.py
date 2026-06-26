"""Pluggable engine protocol and registry for Zarr-Python v4.

An engine implements the hierarchy verb set. Alternative engines preserve the
zarr-python surface while swapping the implementation underneath; the engine is
selected via the ``engine=`` kwarg on ``zarr.open(...)``. Built-in engines are
``"default"`` (pure Python), ``"zarrs"`` (Rust), and ``"tensorstore"`` (Google
TensorStore).

Source: [proposals/performance.md](../proposals/performance.md)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from zarr.engines.python import PythonEngine
from zarr.engines.tensorstore import TensorStoreEngine
from zarr.engines.zarrs import ZarrsEngine

if TYPE_CHECKING:
    from zarr.metadata import ArrayMetadata, Selection
    from zarr.store import Store

# Scalar aliases with no canonical owner; declared locally for a standalone import.
CodecPipeline = Any  # owned elsewhere (ordered codec bundle)
NDArrayLike = Any  # owned elsewhere (array-like buffer)

__all__ = [
    "Engine",
    "register_engine",
    "get_engine",
    "list_engines",
    "PythonEngine",
    "ZarrsEngine",
    "TensorStoreEngine",
]


@runtime_checkable
class Engine(Protocol):
    """An engine implements the hierarchy verb set.

    Alternative engines preserve the zarr-python surface while swapping the
    implementation underneath the four core verbs.

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
        """Read and decode a single chunk.

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
        """Read and decode an arbitrary selection across chunks.

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
        """Encode and write a single chunk.

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
        """Encode and write an arbitrary selection across chunks.

        Source: [proposals/performance.md](../proposals/performance.md)
        """
        ...


def register_engine(name: str, engine: Engine) -> None:
    """Register ``engine`` under ``name`` in the global engine registry.

    Source: [proposals/performance.md](../proposals/performance.md)
    """
    ...


def get_engine(name: str) -> Engine:
    """Return the engine registered under ``name``.

    Source: [proposals/performance.md](../proposals/performance.md)
    """
    ...


def list_engines() -> list[str]:
    """List the names of all registered engines.

    Source: [proposals/performance.md](../proposals/performance.md)
    """
    ...
