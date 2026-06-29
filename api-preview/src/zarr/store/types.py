"""Supporting types for the Zarr v4 store layer.

Source: [proposals/stores-api.md](../proposals/stores-api.md)

This module defines the value objects, result records, streaming handles, and
transaction primitives that the capability protocols in :mod:`zarr.store.protocols`
exchange. These types are deliberately small and backend-agnostic so that every
concrete backend and composable wrapper speaks the same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from collections.abc import Sequence

__all__ = [
    "Generation",
    "WritableBuffer",
    "ReadResult",
    "PutResult",
    "ListResult",
    "ObjectMetadata",
    "StoreDeclaration",
    "KeyRange",
    "ReadStream",
    "AsyncReadStream",
    "Transaction",
    "TransactionFailed",
]


Generation = object
"""Opaque per-key version token.

Source: [proposals/stores-api.md](../proposals/stores-api.md)

A ``Generation`` identifies a particular version of the value stored at a key
(for example an HTTP ETag, an object-store version id, or a filesystem mtime
plus size). It is treated as a fully opaque token: the only operation defined on
it is equality. Stores compare generations to implement conditional reads and
writes (``if_match`` / ``if_none_match`` / ``if_not_match``) but never interpret
their internal structure.
"""

WritableBuffer = Any
"""A writable, buffer-protocol-supporting destination for streamed reads.

Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)

Aliased to :data:`typing.Any` because the buffer protocol is not expressible in
the standard typing vocabulary; in practice this is any object exposing a
writable C-contiguous buffer (``bytearray``, ``memoryview``, NumPy array, etc.).
"""


@dataclass(frozen=True)
class ReadResult:
    """Result of a successful read.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    value: memoryview
    generation: Generation


@dataclass(frozen=True)
class PutResult:
    """Result of a write.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    generation: Generation | None = None
    applied: bool = True


@dataclass
class ListResult:
    """Result of a delimited listing: leaf objects plus common prefixes.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    objects: Sequence[str]
    prefixes: Sequence[str]


@dataclass(frozen=True)
class ObjectMetadata:
    """Metadata about a stored object, as returned by ``head``.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    generation: Generation
    size_bytes: int
    last_modified: float | None


@dataclass(frozen=True)
class StoreDeclaration:
    """Serializable, backend-agnostic description of a store.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)

    A declaration captures the ``kind`` of store and the ``config`` needed to
    reconstruct it, enabling stores to be transmitted across process boundaries
    and rebuilt via :meth:`zarr.store.protocols.Serializable.from_declaration`.
    """

    kind: str
    config: dict[str, object]


@dataclass(frozen=True, slots=True)
class KeyRange:
    """A half-open range of keys ``[inclusive_min, exclusive_max)``.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)

    Key ranges bound the portion of a key space a store exposes and drive
    routing in composite stores. An ``exclusive_max`` of ``None`` denotes an
    unbounded upper end.
    """

    inclusive_min: str = ""
    exclusive_max: str | None = None

    @classmethod
    def from_prefix(cls, prefix: str) -> KeyRange:
        """Build the key range covering exactly the keys under ``prefix``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    def contains(self, key: str) -> bool:
        """Return whether ``key`` falls within this range.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    def overlaps(self, other: KeyRange) -> bool:
        """Return whether this range shares any key with ``other``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    def intersect(self, other: KeyRange) -> KeyRange | None:
        """Return the overlap of the two ranges, or ``None`` if disjoint.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


class ReadStream:
    """Synchronous streaming handle for incremental reads of one object.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)

    A read stream yields the bytes of a single value (or byte range) into
    caller-provided buffers, avoiding materializing the whole object at once. It
    is a context manager; exiting closes the underlying transport.
    """

    @property
    def generation(self) -> Generation | None:
        """The generation of the object being streamed, if known.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    @property
    def total_size(self) -> int | None:
        """Total number of bytes in the stream, if known in advance.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    @property
    def closed(self) -> bool:
        """Whether the stream has been closed.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    def read_into(self, buffer: WritableBuffer) -> int:
        """Read available bytes into ``buffer``, returning the count read.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    def read_full(self, buffer: WritableBuffer) -> int:
        """Fill ``buffer`` completely (or until EOF), returning the count read.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    def close(self) -> None:
        """Close the stream and release its resources.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    def __enter__(self) -> ReadStream:
        """Enter the stream context.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...

    def __exit__(self, *exc: object) -> None:
        """Exit the stream context, closing the stream.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...


class AsyncReadStream:
    """Asynchronous streaming handle for incremental reads of one object.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)

    The async counterpart to :class:`ReadStream`; methods are awaitable and the
    handle is an async context manager.
    """

    @property
    def generation(self) -> Generation | None:
        """The generation of the object being streamed, if known.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    @property
    def total_size(self) -> int | None:
        """Total number of bytes in the stream, if known in advance.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    @property
    def closed(self) -> bool:
        """Whether the stream has been closed.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    async def read_into_async(self, buffer: WritableBuffer) -> int:
        """Read available bytes into ``buffer``, returning the count read.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    async def read_full_async(self, buffer: WritableBuffer) -> int:
        """Fill ``buffer`` completely (or until EOF), returning the count read.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    async def aclose(self) -> None:
        """Close the stream and release its resources.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    async def __aenter__(self) -> AsyncReadStream:
        """Enter the async stream context.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...

    async def __aexit__(self, *exc: object) -> None:
        """Exit the async stream context, closing the stream.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...


class Transaction:
    """A unit of work that batches store mutations for atomic application.

    Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)

    A transaction collects writes and deletes and applies them together via
    :meth:`commit`. When ``atomic`` is set, the commit either fully succeeds or
    leaves the store unchanged; when ``repeatable_read`` is set, reads observed
    within the transaction are validated against their generations at commit
    time. It serves as both a sync and async context manager.
    """

    def __init__(self, *, atomic: bool = False, repeatable_read: bool = False) -> None:
        """Create a transaction.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
        """
        ...

    @property
    def aborted(self) -> bool:
        """Whether the transaction has been aborted.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
        """
        ...

    @property
    def committed(self) -> bool:
        """Whether the transaction has been committed.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
        """
        ...

    def commit(self) -> None:
        """Apply the transaction's buffered mutations.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
        """
        ...

    async def commit_async(self) -> None:
        """Apply the transaction's buffered mutations asynchronously.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
        """
        ...

    def abort(self) -> None:
        """Discard the transaction's buffered mutations.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
        """
        ...

    def __enter__(self) -> Transaction:
        """Enter the transaction context.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md) (inferred)
        """
        ...

    def __exit__(self, *exc: object) -> None:
        """Exit the transaction context, committing on success or aborting.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md) (inferred)
        """
        ...

    async def __aenter__(self) -> Transaction:
        """Enter the async transaction context.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md) (inferred)
        """
        ...

    async def __aexit__(self, *exc: object) -> None:
        """Exit the async transaction context, committing or aborting.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md) (inferred)
        """
        ...


class TransactionFailed(Exception):
    """Raised when a transaction cannot be committed.

    Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)

    Carries the set of conflicting ``keys`` and a human-readable ``reason``
    describing why the commit failed (for example a generation mismatch under
    ``repeatable_read``).
    """

    keys: frozenset[str]
    reason: str
