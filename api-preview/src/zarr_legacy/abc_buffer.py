"""Legacy 3.x buffer abstractions.

Mirrors the CPU/GPU byte and n-d array buffer abstractions and the
``BufferPrototype`` indirection from ``zarr.abc.buffer`` / ``zarr.core.buffer``.
In 4.0.0 this prototype machinery is replaced by the ``ReadResult``/``memoryview``
read contract, ``read_into``/``decode_into``, and Array-API namespace selection
at materialization time.

Real 3.x location: ``zarr.abc.buffer`` / ``zarr.core.buffer``
Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ._util import _legacy

__all__ = [
    "Buffer",
    "NDBuffer",
    "BufferPrototype",
    "default_buffer_prototype",
]

NDArrayLike = Any
Self = Any


@_legacy(
    replaced_by="zarr.store.ReadResult / memoryview read contract",
    migration="Read bytes into caller-provided buffers via read_into instead of the Buffer abstraction.",
)
class Buffer(ABC):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.store.ReadResult` / `memoryview` read contract
        **Migration:** Read bytes into caller-provided buffers via read_into instead of the Buffer abstraction.

    The CPU/GPU byte buffer abstraction.

    Real 3.x location: `zarr.core.buffer.Buffer`
    Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
    """

    @classmethod
    @abstractmethod
    def from_bytes(cls, bytes_like: Any) -> Self:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.ReadResult`
            **Migration:** Wrap raw bytes in a ReadResult / memoryview instead.

        Create a buffer from a bytes-like object.

        Real 3.x location: `zarr.core.buffer.Buffer.from_bytes`
        Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
        """
        ...

    @abstractmethod
    def as_array_like(self) -> NDArrayLike:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** Array-API namespace selection at materialization
            **Migration:** Materialize via the selected Array-API namespace instead.

        Return the underlying array-like object.

        Real 3.x location: `zarr.core.buffer.Buffer.as_array_like`
        Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
        """
        ...

    @abstractmethod
    def to_bytes(self) -> bytes:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.ReadResult`
            **Migration:** Obtain bytes from the ReadResult / memoryview.

        Return the buffer contents as ``bytes``.

        Real 3.x location: `zarr.core.buffer.Buffer.to_bytes`
        Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
        """
        ...

    @abstractmethod
    def __len__(self) -> int:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.store.ReadResult`
            **Migration:** Use the length of the ReadResult / memoryview.

        Return the number of bytes in the buffer.

        Real 3.x location: `zarr.core.buffer.Buffer.__len__`
        Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
        """
        ...


@_legacy(
    replaced_by="decode_into + Array-API namespace selection",
    migration="Decode chunks into caller-provided arrays via decode_into instead of the NDBuffer abstraction.",
)
class NDBuffer(ABC):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `decode_into` + Array-API namespace selection
        **Migration:** Decode chunks into caller-provided arrays via decode_into instead of the NDBuffer abstraction.

    The n-dimensional array buffer abstraction.

    Real 3.x location: `zarr.core.buffer.NDBuffer`
    Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
    """

    @abstractmethod
    def as_ndarray_like(self) -> NDArrayLike:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** Array-API namespace selection at materialization
            **Migration:** Materialize via the selected Array-API namespace instead.

        Return the underlying n-d array-like object.

        Real 3.x location: `zarr.core.buffer.NDBuffer.as_ndarray_like`
        Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
        """
        ...


@_legacy(
    replaced_by="Array-API namespace selection",
    migration="Select the array namespace at materialization instead of threading a BufferPrototype.",
)
@dataclass(frozen=True)
class BufferPrototype:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** Array-API namespace selection
        **Migration:** Select the array namespace at materialization instead of threading a BufferPrototype.

    Bundle of the ``Buffer`` and ``NDBuffer`` implementations to use.

    Real 3.x location: `zarr.core.buffer.BufferPrototype`
    Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
    """

    buffer: type[Buffer]
    nd_buffer: type[NDBuffer]


default_buffer_prototype: BufferPrototype = ...
"""!!! warning "Removed in 4.0.0"
    **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
    **Replaced by:** Array-API namespace selection
    **Migration:** Select the array namespace at materialization instead of relying on a default prototype.

The default CPU ``BufferPrototype``.

Real 3.x location: `zarr.core.buffer.default_buffer_prototype`
Source: [proposals/gpu.md](../proposals/gpu.md), stores.md
"""
