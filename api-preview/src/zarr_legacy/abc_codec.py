"""Legacy 3.x codec abstract base classes.

Mirrors the async, batched codec ABCs from ``zarr.abc.codec``: the array/array,
array/bytes and bytes/bytes split, the partial decode/encode mixins, and the
``CodecPipeline``. In 4.0.0 these collapse into a single sync-first
``zarr.codec.Codec`` bundle with single-element signatures and capability flags.

Real 3.x location: ``zarr.abc.codec``
Source: [proposals/codecs.md](../proposals/codecs.md)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from ._util import _legacy

__all__ = [
    "BaseCodec",
    "ArrayArrayCodec",
    "ArrayBytesCodec",
    "BytesBytesCodec",
    "ArrayBytesCodecPartialDecodeMixin",
    "ArrayBytesCodecPartialEncodeMixin",
    "CodecPipeline",
]

Buffer = Any
NDBuffer = Any
ArraySpec = Any


@_legacy(
    replaced_by="zarr.codec.Codec",
    migration="Implement the sync-first zarr.codec.Codec with single-element decode/encode and optional decode_into.",
)
class BaseCodec(ABC):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.codec.Codec`
        **Migration:** Implement the sync-first zarr.codec.Codec with single-element decode/encode and optional decode_into.

    The async, batched base class for all codecs.

    Real 3.x location: `zarr.abc.codec.BaseCodec`
    Source: [proposals/codecs.md](../proposals/codecs.md)
    """

    @abstractmethod
    async def decode(
        self,
        chunks_and_specs: Iterable[tuple[Buffer | None, ArraySpec]],
    ) -> Iterable[NDBuffer | None]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.codec.Codec.decode`
            **Migration:** Decode a single chunk synchronously; batching moves to the invocation path.

        Decode a batch of encoded chunks.

        Real 3.x location: `zarr.abc.codec.BaseCodec.decode`
        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...

    @abstractmethod
    async def encode(
        self,
        chunks_and_specs: Iterable[tuple[NDBuffer | None, ArraySpec]],
    ) -> Iterable[Buffer | None]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.codec.Codec.encode`
            **Migration:** Encode a single chunk synchronously; batching moves to the invocation path.

        Encode a batch of decoded chunks.

        Real 3.x location: `zarr.abc.codec.BaseCodec.encode`
        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...


@_legacy(
    replaced_by="zarr.codec.Codec",
    migration="The array/array vs array/bytes distinction is dropped; implement the single Codec bundle.",
)
class ArrayArrayCodec(BaseCodec):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.codec.Codec`
        **Migration:** The array/array vs array/bytes distinction is dropped; implement the single Codec bundle.

    Marker base class for codecs that map arrays to arrays.

    Real 3.x location: `zarr.abc.codec.ArrayArrayCodec`
    Source: [proposals/codecs.md](../proposals/codecs.md)
    """


@_legacy(
    replaced_by="zarr.codec.Codec",
    migration="The array/array vs array/bytes distinction is dropped; implement the single Codec bundle.",
)
class ArrayBytesCodec(BaseCodec):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.codec.Codec`
        **Migration:** The array/array vs array/bytes distinction is dropped; implement the single Codec bundle.

    Marker base class for codecs that map arrays to bytes.

    Real 3.x location: `zarr.abc.codec.ArrayBytesCodec`
    Source: [proposals/codecs.md](../proposals/codecs.md)
    """


@_legacy(
    replaced_by="zarr.codec.Codec",
    migration="The array/array vs array/bytes distinction is dropped; implement the single Codec bundle.",
)
class BytesBytesCodec(BaseCodec):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.codec.Codec`
        **Migration:** The array/array vs array/bytes distinction is dropped; implement the single Codec bundle.

    Marker base class for codecs that map bytes to bytes.

    Real 3.x location: `zarr.abc.codec.BytesBytesCodec`
    Source: [proposals/codecs.md](../proposals/codecs.md)
    """


@_legacy(
    replaced_by="zarr.codec.PartialDecodeCapability",
    migration="Advertise partial decode via a capability flag on zarr.codec.Codec instead of a mixin.",
)
class ArrayBytesCodecPartialDecodeMixin:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.codec.PartialDecodeCapability`
        **Migration:** Advertise partial decode via a capability flag on zarr.codec.Codec instead of a mixin.

    Mixin granting an array/bytes codec the ability to decode partial chunks.

    Real 3.x location: `zarr.abc.codec.ArrayBytesCodecPartialDecodeMixin`
    Source: [proposals/codecs.md](../proposals/codecs.md)
    """

    @abstractmethod
    async def decode_partial(
        self,
        batch_info: Iterable[tuple[Any, Any, ArraySpec]],
    ) -> Iterable[NDBuffer | None]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.codec.PartialDecodeCapability`
            **Migration:** Implement partial decode behind the capability flag on Codec.

        Decode a partial selection from a batch of encoded chunks.

        Real 3.x location: `zarr.abc.codec.ArrayBytesCodecPartialDecodeMixin.decode_partial`
        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...


@_legacy(
    replaced_by="zarr.codec.PartialDecodeCapability",
    migration="Advertise partial encode via a capability flag on zarr.codec.Codec instead of a mixin.",
)
class ArrayBytesCodecPartialEncodeMixin:
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.codec.PartialDecodeCapability`
        **Migration:** Advertise partial encode via a capability flag on zarr.codec.Codec instead of a mixin.

    Mixin granting an array/bytes codec the ability to encode partial chunks.

    Real 3.x location: `zarr.abc.codec.ArrayBytesCodecPartialEncodeMixin`
    Source: [proposals/codecs.md](../proposals/codecs.md)
    """

    @abstractmethod
    async def encode_partial(
        self,
        batch_info: Iterable[tuple[Any, Any, ArraySpec]],
    ) -> None:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.codec.PartialDecodeCapability`
            **Migration:** Implement partial encode behind the capability flag on Codec.

        Encode a partial selection into a batch of encoded chunks.

        Real 3.x location: `zarr.abc.codec.ArrayBytesCodecPartialEncodeMixin.encode_partial`
        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...


@_legacy(
    replaced_by="zarr.codec (slim codec invocation path)",
    migration="Drop the pipeline ABC; the slimmer zarr.codec invocation path orchestrates codecs.",
)
class CodecPipeline(ABC):
    """!!! warning "Removed in 4.0.0"
        **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
        **Replaced by:** `zarr.codec` slim codec invocation path
        **Migration:** Drop the pipeline ABC; the slimmer zarr.codec invocation path orchestrates codecs.

    The async, batched codec pipeline abstract base class.

    Real 3.x location: `zarr.abc.codec.CodecPipeline`
    Source: [proposals/codecs.md](../proposals/codecs.md)
    """

    @abstractmethod
    async def decode(
        self,
        chunks_and_specs: Iterable[tuple[Buffer | None, ArraySpec]],
    ) -> Iterable[NDBuffer | None]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.codec` invocation path
            **Migration:** Let the zarr.codec invocation path drive decoding.

        Decode a whole batch of chunks through the pipeline.

        Real 3.x location: `zarr.abc.codec.CodecPipeline.decode`
        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...

    @abstractmethod
    async def encode(
        self,
        chunks_and_specs: Iterable[tuple[NDBuffer | None, ArraySpec]],
    ) -> Iterable[Buffer | None]:
        """!!! warning "Removed in 4.0.0"
            **Deprecated in:** 3.x &nbsp; **Removed in:** 4.0.0
            **Replaced by:** `zarr.codec` invocation path
            **Migration:** Let the zarr.codec invocation path drive encoding.

        Encode a whole batch of chunks through the pipeline.

        Real 3.x location: `zarr.abc.codec.CodecPipeline.encode`
        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...
