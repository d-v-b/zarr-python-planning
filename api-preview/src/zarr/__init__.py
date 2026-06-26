"""Zarr-Python — projected v4 final-state public API (PREVIEW, non-functional).

This package is a stub-only snapshot of the public API as it would look after the
entire Zarr-Python v4 plan has landed (the post-``4.0.0`` end state). Nothing here
performs real IO; every body is ``...``. Names and signatures are synthesized from
the planning proposals and will change. Signatures the proposals leave to
implementation are flagged ``(inferred)`` in their docstrings.

The library is reshaped around the seven-level "Zarr stack". Each level is a
submodule here, but in the real plan corresponds to a separately published
distribution re-exported through this facade:

- :mod:`zarr.metadata`  -> ``zarr-metadata``
- :mod:`zarr.dtype`     -> ``zarr-dtype``
- :mod:`zarr.codec`     -> ``zarr-codec``
- :mod:`zarr.store`     -> ``zarr-store``

Source: [proposals/functional-core.md](../proposals/functional-core.md), [proposals/missing-apis.md](../proposals/missing-apis.md)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
from collections.abc import Awaitable, Callable, Iterable, Sequence

if TYPE_CHECKING:
    from .dtype import DType
    from .metadata import ChunkKeyEncoding

# Stack submodules (importable as zarr.metadata, zarr.store, ...).
from . import (
    codec,
    concurrency,
    dtype,
    engines,
    exceptions,
    hierarchy,
    metadata,
    observability,
    store,
)
from .array import Array
from .group import Group
from .concurrency import ComputeConcurrency, IoConcurrency
from .observability import Metrics, enable_opentelemetry, metrics_process_wide
from .config import Config, config, to_sync
from .exceptions import (
    ChunkAlignmentError,
    InvalidMetadataError,
    PathExistsError,
    PathNotFoundError,
    ZarrError,
)
from .store import (
    Caching,
    FsspecStore,
    KvStack,
    LocalStore,
    MemoryStore,
    ObstoreStore,
    Prefixed,
    RangeCoalescing,
    ReadOnly,
    Retry,
    Transaction,
    TransactionFailed,
    ZipStore,
)

# Module-local aliases for the array-like / store inputs used only in annotations.
StoreLike = Any
NDArrayLike = Any

__all__ = [
    # Core objects
    "Array",
    "Group",
    # Opening
    "open",
    "open_array",
    "open_group",
    "open_for_read",
    "open_or_create",
    "open_nodes",
    # Creating
    "create",
    "create_array",
    "create_group",
    "create_or_overwrite",
    # IO conveniences
    "copy",
    "copy_all",
    "rechunk",
    "register_attr_serializer",
    "batch",
    "materialize",
    # Concurrency / observability / config
    "ComputeConcurrency",
    "IoConcurrency",
    "Metrics",
    "metrics_process_wide",
    "enable_opentelemetry",
    "Config",
    "config",
    "to_sync",
    # Exceptions
    "ZarrError",
    "PathExistsError",
    "PathNotFoundError",
    "InvalidMetadataError",
    "ChunkAlignmentError",
    "TransactionFailed",
    # Common store backends / wrappers (full surface in zarr.store)
    "LocalStore",
    "MemoryStore",
    "ZipStore",
    "FsspecStore",
    "ObstoreStore",
    "Caching",
    "RangeCoalescing",
    "Retry",
    "ReadOnly",
    "Prefixed",
    "KvStack",
    "Transaction",
    # Submodules
    "metadata",
    "dtype",
    "codec",
    "store",
    "engines",
    "hierarchy",
    "observability",
    "concurrency",
    "exceptions",
]


# --------------------------------------------------------------------------- #
# Opening existing hierarchies
# --------------------------------------------------------------------------- #
def open(
    store: StoreLike = None,
    *,
    path: str | None = None,
    zarr_format: Literal[2, 3] | None = None,
    storage_options: dict[str, Any] | None = None,
    engine: str = "default",
) -> Array | Group:
    """Open an existing array or group, dispatching on what is found.

    Accepts a store, a path, or a ZEP-8 URL (e.g. ``"zarr://s3://bucket/key"``).
    The ``engine`` keyword selects the IO engine (``"default"``, ``"zarrs"``,
    ``"tensorstore"``).

    Source: [proposals/functional-core.md](../proposals/functional-core.md), [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
    """
    ...


def open_array(
    store: StoreLike = None,
    *,
    path: str | None = None,
    zarr_format: Literal[2, 3] | None = None,
    storage_options: dict[str, Any] | None = None,
    engine: str = "default",
) -> Array:
    """Open an existing array.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
    """
    ...


def open_group(
    store: StoreLike = None,
    *,
    path: str | None = None,
    zarr_format: Literal[2, 3] | None = None,
    storage_options: dict[str, Any] | None = None,
    attributes: dict[str, Any] | None = None,
    use_consolidated: bool | str | None = None,
    engine: str = "default",
) -> Group:
    """Open an existing group.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
    """
    ...


def open_for_read(
    store: StoreLike = None,
    *,
    path: str | None = None,
    zarr_format: Literal[2, 3] | None = None,
    storage_options: dict[str, Any] | None = None,
    engine: str = "default",
) -> Array | Group:
    """Open a node read-only. Replaces ``open(..., mode="r")``.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §3
    """
    ...


def open_or_create(
    store: StoreLike = None,
    *,
    path: str | None = None,
    zarr_format: Literal[2, 3] | None = None,
    storage_options: dict[str, Any] | None = None,
    engine: str = "default",
) -> Array | Group:
    """Open a node if it exists, otherwise create it. Replaces ``mode="a"``.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §3
    """
    ...


def open_nodes(store: StoreLike, paths: Iterable[str]) -> dict[str, Array | Group]:
    """Open several nodes in one pass, returning a path -> node mapping.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...


# --------------------------------------------------------------------------- #
# Creating new hierarchies
# --------------------------------------------------------------------------- #
def create_array(
    store: StoreLike,
    *,
    name: str | None = None,
    shape: tuple[int, ...] | None = None,
    dtype: DType | str | None = None,
    data: NDArrayLike | None = None,
    chunks: tuple[int, ...] | Literal["auto"] = "auto",
    shards: tuple[int, ...] | None = None,
    filters: Any = "auto",
    compressors: Any = "auto",
    serializer: Any = "auto",
    fill_value: Any | None = None,
    order: Literal["C", "F"] | None = None,
    zarr_format: Literal[2, 3] | None = 3,
    attributes: dict[str, Any] | None = None,
    chunk_key_encoding: ChunkKeyEncoding | None = None,
    dimension_names: Sequence[str | None] | None = None,
    storage_options: dict[str, Any] | None = None,
    overwrite: bool = False,
    config: Any | None = None,
    engine: str = "default",
    write_data: bool = True,
) -> Array:
    """Create a new array.

    The full array-creation surface, mirroring the explicit keyword arguments of
    the current ``zarr.create_array``. ``filters`` / ``compressors`` / ``serializer``
    are the v3 three-part codec knobs; ``engine`` selects the IO engine.

    Note: the *naming* of the mode-replacement constructors is itself an open
    question in the plan — ``create`` / ``create_or_overwrite`` here versus a single
    ``create_array(..., overwrite=...)`` are alternatives still to be decided.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (constructor names inferred / open question)
    """
    ...


def create(
    store: StoreLike,
    *,
    path: str | None = None,
    shape: tuple[int, ...] | None = None,
    dtype: DType | str | None = None,
    data: NDArrayLike | None = None,
    chunks: tuple[int, ...] | Literal["auto"] = "auto",
    shards: tuple[int, ...] | None = None,
    filters: Any = "auto",
    compressors: Any = "auto",
    serializer: Any = "auto",
    fill_value: Any | None = None,
    order: Literal["C", "F"] | None = None,
    zarr_format: Literal[2, 3] | None = 3,
    attributes: dict[str, Any] | None = None,
    chunk_key_encoding: ChunkKeyEncoding | None = None,
    dimension_names: Sequence[str | None] | None = None,
    storage_options: dict[str, Any] | None = None,
    config: Any | None = None,
    engine: str = "default",
    write_data: bool = True,
) -> Array:
    """Create a new array, raising if a node already exists. Replaces ``mode="w-"``.

    Same surface as :func:`create_array` but with no ``overwrite`` — existence is an
    error. See the naming open-question noted on :func:`create_array`.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §3 (open question)
    """
    ...


def create_or_overwrite(
    store: StoreLike,
    *,
    path: str | None = None,
    shape: tuple[int, ...] | None = None,
    dtype: DType | str | None = None,
    data: NDArrayLike | None = None,
    chunks: tuple[int, ...] | Literal["auto"] = "auto",
    shards: tuple[int, ...] | None = None,
    filters: Any = "auto",
    compressors: Any = "auto",
    serializer: Any = "auto",
    fill_value: Any | None = None,
    order: Literal["C", "F"] | None = None,
    zarr_format: Literal[2, 3] | None = 3,
    attributes: dict[str, Any] | None = None,
    chunk_key_encoding: ChunkKeyEncoding | None = None,
    dimension_names: Sequence[str | None] | None = None,
    storage_options: dict[str, Any] | None = None,
    config: Any | None = None,
    engine: str = "default",
    write_data: bool = True,
) -> Array:
    """Create a new array, replacing any existing node. Replaces ``mode="w"``.

    Same surface as :func:`create_array` with ``overwrite`` implied by the name.
    See the naming open-question noted on :func:`create_array`.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) §3 (open question)
    """
    ...


def create_group(
    store: StoreLike,
    *,
    name: str | None = None,
    zarr_format: Literal[2, 3] | None = 3,
    overwrite: bool = False,
    attributes: dict[str, Any] | None = None,
    storage_options: dict[str, Any] | None = None,
    engine: str = "default",
) -> Group:
    """Create a new group.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (inferred)
    """
    ...


# --------------------------------------------------------------------------- #
# IO conveniences
# --------------------------------------------------------------------------- #
def copy(
    src: Array | Group,
    dst: StoreLike,
    *,
    name: str | None = None,
    overwrite: bool = False,
) -> None:
    """Copy a single array or group to another store.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (signature inferred)
    """
    ...


def copy_all(src: Group, dst: StoreLike, *, overwrite: bool = False) -> None:
    """Recursively copy an entire hierarchy to another store.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (signature inferred)
    """
    ...


def rechunk(
    source: Array,
    chunks: tuple[int, ...] | Literal["auto"],
    *,
    target_store: StoreLike | None = None,
    max_memory: int | str | None = None,
) -> Array:
    """Rewrite an array with a new chunk layout (in-library rechunking primitive).

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md) (signature inferred)
    """
    ...


def register_attr_serializer(
    type_class: type,
    encoder: Callable[[Any], Any],
    decoder: Callable[[Any], Any],
) -> None:
    """Register an encoder/decoder for a non-JSON-native attribute type.

    Source: [proposals/missing-apis.md](../proposals/missing-apis.md)
    """
    ...


def batch() -> Any:
    """Context manager that collects view materializations into one IO plan.

    Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
    """
    ...


def materialize(views: Iterable[Array]) -> list[NDArrayLike]:
    """Materialize several lazy views in a single batched IO plan.

    Source: [proposals/lazy-indexing.md](../proposals/lazy-indexing.md)
    """
    ...
