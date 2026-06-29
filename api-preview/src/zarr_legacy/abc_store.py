"""Legacy 3.x store abstract base class and byte-request types.

Mirrors the monolithic async ``Store`` ABC and its byte-range request types from
``zarr.abc.store``. In 4.0.0 the single all-or-nothing ABC is replaced by a set
of narrow capability protocols in ``zarr.store`` that a backend implements only
for the operations it actually supports.

Real 3.x location: ``zarr.abc.store``
Source: [proposals/stores.md](../proposals/stores.md)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from ._util import _legacy

__all__ = [
    "RangeByteRequest",
    "OffsetByteRequest",
    "SuffixByteRequest",
    "ByteRequest",
    "Store",
    "ByteGetter",
    "ByteSetter",
]

Buffer = Any
BufferPrototype = Any
ByteRequest = Any


@_legacy(
    replaced_by="zarr.store.RangeByteRequest",
    migration="Use the byte-range request types re-exported from zarr.store.",
)
@dataclass(frozen=True)
class RangeByteRequest:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store.RangeByteRequest`
        **Migration:** Use the byte-range request types re-exported from zarr.store.

    A request for a half-open byte range ``[start, end)``.

    Real 3.x location: `zarr.abc.store.RangeByteRequest`
    Source: [proposals/stores.md](../proposals/stores.md)
    """

    start: int
    end: int


@_legacy(
    replaced_by="zarr.store.OffsetByteRequest",
    migration="Use the byte-range request types re-exported from zarr.store.",
)
@dataclass(frozen=True)
class OffsetByteRequest:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store.OffsetByteRequest`
        **Migration:** Use the byte-range request types re-exported from zarr.store.

    A request for all bytes from ``offset`` to the end of the value.

    Real 3.x location: `zarr.abc.store.OffsetByteRequest`
    Source: [proposals/stores.md](../proposals/stores.md)
    """

    offset: int


@_legacy(
    replaced_by="zarr.store.SuffixByteRequest",
    migration="Use the byte-range request types re-exported from zarr.store.",
)
@dataclass(frozen=True)
class SuffixByteRequest:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store.SuffixByteRequest`
        **Migration:** Use the byte-range request types re-exported from zarr.store.

    A request for the final ``suffix`` bytes of the value.

    Real 3.x location: `zarr.abc.store.SuffixByteRequest`
    Source: [proposals/stores.md](../proposals/stores.md)
    """

    suffix: int


@_legacy(
    replaced_by="zarr.store (Get/GetRange/Put/Delete/List capability protocols + ReadResult/Generation)",
    migration="Implement only the capability protocols your backend supports and compose wrappers.",
)
class Store(ABC):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store` capability protocols (Get/GetRange/Put/Delete/List/...) + ReadResult/Generation
        **Migration:** Implement only the capability protocols your backend supports and compose wrappers.

    The monolithic async store abstract base class.

    Real 3.x location: `zarr.abc.store.Store`
    Source: [proposals/stores.md](../proposals/stores.md)
    """

    @property
    @abstractmethod
    def read_only(self) -> bool:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store` capability protocols
            **Migration:** Capability is implied by which protocols the backend implements.

        Whether the store is read-only.

        Real 3.x location: `zarr.abc.store.Store.read_only`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @property
    @abstractmethod
    def supports_writes(self) -> bool:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Put`
            **Migration:** Implement the Put protocol instead of advertising a flag.

        Whether the store supports writes.

        Real 3.x location: `zarr.abc.store.Store.supports_writes`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @property
    @abstractmethod
    def supports_deletes(self) -> bool:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Delete`
            **Migration:** Implement the Delete protocol instead of advertising a flag.

        Whether the store supports deletes.

        Real 3.x location: `zarr.abc.store.Store.supports_deletes`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @property
    @abstractmethod
    def supports_listing(self) -> bool:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.List`
            **Migration:** Implement the List protocol instead of advertising a flag.

        Whether the store supports listing.

        Real 3.x location: `zarr.abc.store.Store.supports_listing`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def get(
        self,
        key: str,
        prototype: BufferPrototype,
        byte_range: ByteRequest | None = None,
    ) -> Buffer | None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Get`
            **Migration:** Implement the Get protocol returning a ReadResult.

        Retrieve the value (or a byte range of it) associated with ``key``.

        Real 3.x location: `zarr.abc.store.Store.get`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def get_partial_values(
        self,
        prototype: BufferPrototype,
        key_ranges: Iterable[tuple[str, ByteRequest]],
    ) -> list[Buffer | None]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.GetRange`
            **Migration:** Implement the GetRange protocol for batched ranged reads.

        Retrieve byte ranges from possibly multiple keys.

        Real 3.x location: `zarr.abc.store.Store.get_partial_values`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def get_ranges(
        self,
        prototype: BufferPrototype,
        key_ranges: Iterable[tuple[str, ByteRequest]],
    ) -> list[Buffer | None]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.GetRange`
            **Migration:** Implement the GetRange protocol for batched ranged reads.

        Retrieve byte ranges from possibly multiple keys.

        Real 3.x location: `zarr.abc.store.Store.get_ranges`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def set(self, key: str, value: Buffer) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Put`
            **Migration:** Implement the Put protocol.

        Store the value associated with ``key``.

        Real 3.x location: `zarr.abc.store.Store.set`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def set_if_not_exists(self, key: str, value: Buffer) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Put`
            **Migration:** Use the conditional-put capability of the Put protocol.

        Store the value associated with ``key`` only if it does not already exist.

        Real 3.x location: `zarr.abc.store.Store.set_if_not_exists`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Delete`
            **Migration:** Implement the Delete protocol.

        Remove the value associated with ``key``.

        Real 3.x location: `zarr.abc.store.Store.delete`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def delete_dir(self, prefix: str) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Delete`
            **Migration:** Compose Delete and List protocols to remove a prefix.

        Remove all keys under ``prefix``.

        Real 3.x location: `zarr.abc.store.Store.delete_dir`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    def list(self) -> AsyncIterator[str]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.List`
            **Migration:** Implement the List protocol.

        Asynchronously iterate over all keys in the store.

        Real 3.x location: `zarr.abc.store.Store.list`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    def list_prefix(self, prefix: str) -> AsyncIterator[str]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.List`
            **Migration:** Implement the List protocol.

        Asynchronously iterate over all keys under ``prefix``.

        Real 3.x location: `zarr.abc.store.Store.list_prefix`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    def list_dir(self, prefix: str) -> AsyncIterator[str]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.List`
            **Migration:** Implement the List protocol.

        Asynchronously iterate over the immediate children of ``prefix``.

        Real 3.x location: `zarr.abc.store.Store.list_dir`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def getsize(self, key: str) -> int:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store` capability protocols
            **Migration:** Derive size from a ReadResult or the GetRange protocol.

        Return the size in bytes of the value associated with ``key``.

        Real 3.x location: `zarr.abc.store.Store.getsize`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    @abstractmethod
    async def getsize_prefix(self, prefix: str) -> int:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store` capability protocols
            **Migration:** Compose List with per-key size queries.

        Return the total size in bytes of all values under ``prefix``.

        Real 3.x location: `zarr.abc.store.Store.getsize_prefix`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...


@_legacy(
    replaced_by="zarr.store (Get/GetRange protocols)",
    migration="Use the read capability protocols from zarr.store.",
)
class ByteGetter(Protocol):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store` read protocols (Get/GetRange)
        **Migration:** Use the read capability protocols from zarr.store.

    Protocol for an object that can read bytes for a single key.

    Real 3.x location: `zarr.abc.store.ByteGetter`
    Source: [proposals/stores.md](../proposals/stores.md)
    """

    async def get(
        self,
        prototype: BufferPrototype,
        byte_range: ByteRequest | None = None,
    ) -> Buffer | None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Get`
            **Migration:** Use the Get protocol.

        Read bytes (or a byte range) for the bound key.

        Real 3.x location: `zarr.abc.store.ByteGetter.get`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...


@_legacy(
    replaced_by="zarr.store (Put/Delete protocols)",
    migration="Use the write capability protocols from zarr.store.",
)
class ByteSetter(Protocol):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store` write protocols (Put/Delete)
        **Migration:** Use the write capability protocols from zarr.store.

    Protocol for an object that can read and write bytes for a single key.

    Real 3.x location: `zarr.abc.store.ByteSetter`
    Source: [proposals/stores.md](../proposals/stores.md)
    """

    async def get(
        self,
        prototype: BufferPrototype,
        byte_range: ByteRequest | None = None,
    ) -> Buffer | None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Get`
            **Migration:** Use the Get protocol.

        Read bytes (or a byte range) for the bound key.

        Real 3.x location: `zarr.abc.store.ByteSetter.get`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    async def set(self, value: Buffer, byte_range: ByteRequest | None = None) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Put`
            **Migration:** Use the Put protocol.

        Write bytes for the bound key.

        Real 3.x location: `zarr.abc.store.ByteSetter.set`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    async def set_if_not_exists(self, value: Buffer) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Put`
            **Migration:** Use the conditional-put capability of the Put protocol.

        Write bytes for the bound key only if it does not already exist.

        Real 3.x location: `zarr.abc.store.ByteSetter.set_if_not_exists`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...

    async def delete(self) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.Delete`
            **Migration:** Use the Delete protocol.

        Delete the bound key.

        Real 3.x location: `zarr.abc.store.ByteSetter.delete`
        Source: [proposals/stores.md](../proposals/stores.md)
        """
        ...
