"""Capability protocols for the Zarr v4 store layer.

Source: [proposals/stores.md](../proposals/stores.md)

Rather than a single monolithic ``Store`` base class, the v4 store layer is
defined as a family of small structural protocols, each describing one
capability (get, put, delete, list, ...). A concrete backend or wrapper
advertises exactly the capabilities it supports, and consumers depend only on
the narrow protocols they need. Each capability has a synchronous form and an
``_async``-suffixed asynchronous counterpart with an identical signature.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

from collections.abc import Iterator, Sequence

if TYPE_CHECKING:
    from zarr.store.types import (
        AsyncReadStream,
        Generation,
        KeyRange,
        ListResult,
        ObjectMetadata,
        PutResult,
        ReadResult,
        ReadStream,
        StoreDeclaration,
        Transaction,
    )

__all__ = [
    # sync read
    "Get",
    "GetRange",
    "GetRanges",
    # sync write
    "Put",
    "Delete",
    # sync list / metadata
    "List",
    "ListWithDelimiter",
    "Head",
    "Copy",
    # sync streaming
    "GetStreaming",
    "GetRangeStreaming",
    "GetRangesStreaming",
    # cross-cutting
    "Transactional",
    "Serializable",
    # async read
    "GetAsync",
    "GetRangeAsync",
    "GetRangesAsync",
    # async write
    "PutAsync",
    "DeleteAsync",
    # async list / metadata
    "ListAsync",
    "ListWithDelimiterAsync",
    "HeadAsync",
    "CopyAsync",
    # async streaming
    "GetStreamingAsync",
    "GetRangeStreamingAsync",
    "GetRangesStreamingAsync",
    # markers
    "ThreadSafe",
    "AsyncSafe",
]


# --------------------------------------------------------------------------- #
# Synchronous read capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class Get(Protocol):
    """Capability: read the full value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def get(self, key: str, *, if_not_match: Generation | None = None) -> ReadResult:
        """Return the value at ``key``, optionally only if its generation differs.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class GetRange(Protocol):
    """Capability: read a single byte range of the value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def get_range(
        self,
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
        if_not_match: Generation | None = None,
    ) -> ReadResult:
        """Return a byte range of the value at ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class GetRanges(Protocol):
    """Capability: read multiple byte ranges of the value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def get_ranges(
        self,
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
        if_not_match: Generation | None = None,
    ) -> Sequence[ReadResult]:
        """Return several byte ranges of the value at ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


# --------------------------------------------------------------------------- #
# Synchronous write capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class Put(Protocol):
    """Capability: write the value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def put(
        self,
        key: str,
        value: bytes | memoryview,
        *,
        if_match: Generation | None = None,
        if_none_match: bool = False,
    ) -> PutResult:
        """Write ``value`` to ``key``, optionally conditional on a generation.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class Delete(Protocol):
    """Capability: delete the value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def delete(self, key: str, *, if_match: Generation | None = None) -> None:
        """Delete ``key``, optionally only if its generation matches.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


# --------------------------------------------------------------------------- #
# Synchronous list / metadata capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class List(Protocol):
    """Capability: enumerate keys.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def list(
        self,
        prefix: str | None = None,
        *,
        offset: str | None = None,
        range: KeyRange | None = None,
    ) -> Iterator[str]:
        """Iterate over keys, optionally restricted by prefix, offset, or range.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class ListWithDelimiter(Protocol):
    """Capability: enumerate keys one hierarchy level deep.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def list_with_delimiter(
        self, prefix: str | None = None, *, range: KeyRange | None = None
    ) -> ListResult:
        """Return leaf objects and common prefixes directly under ``prefix``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class Head(Protocol):
    """Capability: fetch object metadata without the value.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def head(self, key: str) -> ObjectMetadata:
        """Return metadata for ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class Copy(Protocol):
    """Capability: copy a value from one key to another.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def copy(self, src: str, dst: str) -> None:
        """Copy the value at ``src`` to ``dst``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


# --------------------------------------------------------------------------- #
# Synchronous streaming capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class GetStreaming(Protocol):
    """Capability: open a streaming read of the full value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def get_streaming(self, key: str) -> ReadStream:
        """Open a :class:`~zarr.store.types.ReadStream` for ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class GetRangeStreaming(Protocol):
    """Capability: open a streaming read of a byte range at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def get_range_streaming(
        self,
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> ReadStream:
        """Open a :class:`~zarr.store.types.ReadStream` over a byte range of ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...


@runtime_checkable
class GetRangesStreaming(Protocol):
    """Capability: open streaming reads of multiple byte ranges at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def get_ranges_streaming(
        self,
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
    ) -> Sequence[ReadStream]:
        """Open one :class:`~zarr.store.types.ReadStream` per requested range.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...


# --------------------------------------------------------------------------- #
# Cross-cutting capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class Transactional(Protocol):
    """Capability: bind a store to a transaction.

    Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
    """

    def with_transaction(self, txn: Transaction) -> Self:
        """Return a view of this store whose mutations join ``txn``.

        Source: [proposals/stores-transactional.md](../proposals/stores-transactional.md)
        """
        ...


@runtime_checkable
class Serializable(Protocol):
    """Capability: convert a store to and from a portable declaration.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def to_declaration(self) -> StoreDeclaration:
        """Return a :class:`~zarr.store.types.StoreDeclaration` for this store.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...

    @classmethod
    def from_declaration(cls, decl: StoreDeclaration) -> Self:
        """Reconstruct a store from a declaration.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


# --------------------------------------------------------------------------- #
# Asynchronous read capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class GetAsync(Protocol):
    """Capability: asynchronously read the full value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def get_async(
        self, key: str, *, if_not_match: Generation | None = None
    ) -> ReadResult:
        """Return the value at ``key``, optionally only if its generation differs.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class GetRangeAsync(Protocol):
    """Capability: asynchronously read a single byte range at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def get_range_async(
        self,
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
        if_not_match: Generation | None = None,
    ) -> ReadResult:
        """Return a byte range of the value at ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class GetRangesAsync(Protocol):
    """Capability: asynchronously read multiple byte ranges at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def get_ranges_async(
        self,
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
        if_not_match: Generation | None = None,
    ) -> Sequence[ReadResult]:
        """Return several byte ranges of the value at ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


# --------------------------------------------------------------------------- #
# Asynchronous write capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class PutAsync(Protocol):
    """Capability: asynchronously write the value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def put_async(
        self,
        key: str,
        value: bytes | memoryview,
        *,
        if_match: Generation | None = None,
        if_none_match: bool = False,
    ) -> PutResult:
        """Write ``value`` to ``key``, optionally conditional on a generation.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class DeleteAsync(Protocol):
    """Capability: asynchronously delete the value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def delete_async(self, key: str, *, if_match: Generation | None = None) -> None:
        """Delete ``key``, optionally only if its generation matches.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


# --------------------------------------------------------------------------- #
# Asynchronous list / metadata capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class ListAsync(Protocol):
    """Capability: asynchronously enumerate keys.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    def list_async(
        self,
        prefix: str | None = None,
        *,
        offset: str | None = None,
        range: KeyRange | None = None,
    ) -> AsyncIterator[str]:
        """Asynchronously iterate over keys.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...


@runtime_checkable
class ListWithDelimiterAsync(Protocol):
    """Capability: asynchronously enumerate keys one hierarchy level deep.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def list_with_delimiter_async(
        self, prefix: str | None = None, *, range: KeyRange | None = None
    ) -> ListResult:
        """Return leaf objects and common prefixes directly under ``prefix``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class HeadAsync(Protocol):
    """Capability: asynchronously fetch object metadata.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def head_async(self, key: str) -> ObjectMetadata:
        """Return metadata for ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class CopyAsync(Protocol):
    """Capability: asynchronously copy a value from one key to another.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def copy_async(self, src: str, dst: str) -> None:
        """Copy the value at ``src`` to ``dst``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


# --------------------------------------------------------------------------- #
# Asynchronous streaming capabilities
# --------------------------------------------------------------------------- #
@runtime_checkable
class GetStreamingAsync(Protocol):
    """Capability: open an async streaming read of the full value at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def get_streaming_async(self, key: str) -> AsyncReadStream:
        """Open an :class:`~zarr.store.types.AsyncReadStream` for ``key``.

        Source: [proposals/stores-api.md](../proposals/stores-api.md)
        """
        ...


@runtime_checkable
class GetRangeStreamingAsync(Protocol):
    """Capability: open an async streaming read of a byte range at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def get_range_streaming_async(
        self,
        key: str,
        *,
        start: int,
        end: int | None = None,
        length: int | None = None,
    ) -> AsyncReadStream:
        """Open an :class:`~zarr.store.types.AsyncReadStream` over a byte range.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...


@runtime_checkable
class GetRangesStreamingAsync(Protocol):
    """Capability: open async streaming reads of multiple byte ranges at a key.

    Source: [proposals/stores-api.md](../proposals/stores-api.md)
    """

    async def get_ranges_streaming_async(
        self,
        key: str,
        *,
        starts: Sequence[int],
        ends: Sequence[int] | None = None,
        lengths: Sequence[int] | None = None,
    ) -> Sequence[AsyncReadStream]:
        """Open one :class:`~zarr.store.types.AsyncReadStream` per requested range.

        Source: [proposals/stores-api.md](../proposals/stores-api.md) (inferred)
        """
        ...


# --------------------------------------------------------------------------- #
# Marker protocols
# --------------------------------------------------------------------------- #
@runtime_checkable
class ThreadSafe(Protocol):
    """Marker: this store may be shared across threads.

    Source: [proposals/stores-conformance.md](../proposals/stores-conformance.md)
    """


@runtime_checkable
class AsyncSafe(Protocol):
    """Marker: this store may be shared across concurrent async tasks.

    Source: [proposals/stores-conformance.md](../proposals/stores-conformance.md)
    """
