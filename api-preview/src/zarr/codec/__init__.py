"""Codec capability bundle and concrete codecs for Zarr-Python v4.

Source: [proposals/codecs.md](../proposals/codecs.md)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# These scalar aliases are owned elsewhere in the real package. ``ArraySpec`` is
# the per-array decode/encode context and ``Buffer`` is the engine's byte buffer
# abstraction; both live outside this module. ``CI``/``CO`` stand for the codec's
# decoded ("in") and encoded ("out") representations respectively.
CI = Any  # decoded chunk representation (input side of a codec)
CO = Any  # encoded chunk representation (output side of a codec)
ArraySpec = Any  # owned elsewhere (per-array codec context)
Buffer = Any  # owned elsewhere (engine byte buffer)

__all__ = [
    "PartialDecodeCapability",
    "RecommendedConcurrency",
    "Codec",
    "SupportsSyncCodec",
    "ChunkTransform",
    "BloscCodec",
    "GzipCodec",
    "BytesCodec",
    "ShardingCodec",
    "NumcodecsCompatCodec",
]


@dataclass(frozen=True)
class PartialDecodeCapability:
    """Declares whether a codec supports partial reads and partial decodes.

    Source: [proposals/codecs.md](../proposals/codecs.md)
    """

    partial_read: bool = False
    partial_decode: bool = False


@dataclass(frozen=True)
class RecommendedConcurrency:
    """Concurrency hint a codec advertises to the engine.

    Source: [proposals/codecs.md](../proposals/codecs.md)
    """

    min: int = 1
    max: int = 1


@runtime_checkable
class Codec(Protocol):
    """Sync-first codec capability bundle.

    Source: [proposals/codecs.md](../proposals/codecs.md)
    """

    def encode(self, chunk: CI, spec: ArraySpec) -> CO:
        """Encode a decoded chunk into its on-disk representation.

        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...

    def decode(self, chunk: CO, spec: ArraySpec) -> CI:
        """Decode an on-disk chunk back into its in-memory representation.

        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...

    def encode_into(self, chunk: CI, buffer: Buffer, spec: ArraySpec) -> int:
        """Encode a chunk directly into ``buffer``, returning bytes written.

        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...

    def decode_into(self, chunk: CO, buffer: Buffer, spec: ArraySpec) -> int:
        """Decode a chunk directly into ``buffer``, returning bytes written.

        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...

    def recommended_concurrency(self) -> RecommendedConcurrency:
        """Report the concurrency this codec recommends to the engine.

        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...

    def partial_decode_capability(self) -> PartialDecodeCapability:
        """Report whether the codec supports partial read/decode.

        Source: [proposals/codecs.md](../proposals/codecs.md)
        """
        ...


class SupportsSyncCodec(Protocol):
    """Marker protocol for codecs on the merged synchronous path.

    This protocol already exists in zarr-python today (the merged sync codec
    path); it is shown here for continuity with the v4 capability bundle.

    Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
    """

    def encode(self, chunk: CI, spec: ArraySpec) -> CO:
        """Synchronously encode a chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode(self, chunk: CO, spec: ArraySpec) -> CI:
        """Synchronously decode a chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...


class ChunkTransform(Protocol):
    """Protocol for a single array->array or bytes->bytes chunk transform.

    This protocol already exists in zarr-python today as part of the merged
    sync codec pipeline; it is shown here for continuity with the v4 bundle.

    Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
    """

    def apply(self, chunk: Any, spec: ArraySpec) -> Any:
        """Apply the transform to a chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...


class BloscCodec:
    """Blosc meta-compressor codec.

    Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
    """

    def __init__(
        self,
        *,
        cname: str = "zstd",
        clevel: int = 5,
        shuffle: str = "shuffle",
        blocksize: int = 0,
    ) -> None:
        """Configure a Blosc codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode(self, chunk: CI, spec: ArraySpec) -> CO:
        """Blosc-compress a chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode(self, chunk: CO, spec: ArraySpec) -> CI:
        """Blosc-decompress a chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode_into(self, chunk: CI, buffer: Buffer, spec: ArraySpec) -> int:
        """Blosc-compress directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode_into(self, chunk: CO, buffer: Buffer, spec: ArraySpec) -> int:
        """Blosc-decompress directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def recommended_concurrency(self) -> RecommendedConcurrency:
        """Report Blosc's recommended concurrency.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def partial_decode_capability(self) -> PartialDecodeCapability:
        """Report Blosc's partial read/decode capability.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...


class GzipCodec:
    """Gzip compression codec.

    Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
    """

    def __init__(self, *, level: int = 5) -> None:
        """Configure a Gzip codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode(self, chunk: CI, spec: ArraySpec) -> CO:
        """Gzip-compress a chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode(self, chunk: CO, spec: ArraySpec) -> CI:
        """Gzip-decompress a chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode_into(self, chunk: CI, buffer: Buffer, spec: ArraySpec) -> int:
        """Gzip-compress directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode_into(self, chunk: CO, buffer: Buffer, spec: ArraySpec) -> int:
        """Gzip-decompress directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def recommended_concurrency(self) -> RecommendedConcurrency:
        """Report Gzip's recommended concurrency.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def partial_decode_capability(self) -> PartialDecodeCapability:
        """Report Gzip's partial read/decode capability.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...


class BytesCodec:
    """Array-to-bytes codec controlling endianness.

    Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
    """

    def __init__(self, *, endian: str | None = "little") -> None:
        """Configure a Bytes codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode(self, chunk: CI, spec: ArraySpec) -> CO:
        """Serialize an array chunk to bytes.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode(self, chunk: CO, spec: ArraySpec) -> CI:
        """Deserialize bytes into an array chunk.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode_into(self, chunk: CI, buffer: Buffer, spec: ArraySpec) -> int:
        """Serialize an array chunk directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode_into(self, chunk: CO, buffer: Buffer, spec: ArraySpec) -> int:
        """Deserialize bytes directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def recommended_concurrency(self) -> RecommendedConcurrency:
        """Report the Bytes codec's recommended concurrency.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def partial_decode_capability(self) -> PartialDecodeCapability:
        """Report the Bytes codec's partial read/decode capability.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...


class ShardingCodec:
    """Sharding codec packing sub-chunks into a single store key.

    Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
    """

    def __init__(
        self,
        *,
        chunk_shape: tuple[int, ...],
        codecs: Sequence[Codec] = (),
        index_codecs: Sequence[Codec] = (),
        index_location: str = "end",
    ) -> None:
        """Configure a Sharding codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode(self, chunk: CI, spec: ArraySpec) -> CO:
        """Encode and pack sub-chunks into a shard.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode(self, chunk: CO, spec: ArraySpec) -> CI:
        """Unpack and decode sub-chunks from a shard.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode_into(self, chunk: CI, buffer: Buffer, spec: ArraySpec) -> int:
        """Encode a shard directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode_into(self, chunk: CO, buffer: Buffer, spec: ArraySpec) -> int:
        """Decode a shard directly into ``buffer``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def recommended_concurrency(self) -> RecommendedConcurrency:
        """Report the Sharding codec's recommended concurrency.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def partial_decode_capability(self) -> PartialDecodeCapability:
        """Report the Sharding codec's partial read/decode capability.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...


class NumcodecsCompatCodec:
    """Shim that bridges existing Numcodecs codecs during migration.

    Wraps a legacy numcodecs codec so it satisfies the v4 ``Codec`` bundle,
    easing the transition from the numcodecs-based pipeline.

    Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
    """

    def __init__(self, codec_id: str, **config: Any) -> None:
        """Wrap the numcodecs codec named ``codec_id`` with ``config``.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode(self, chunk: CI, spec: ArraySpec) -> CO:
        """Encode via the wrapped numcodecs codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode(self, chunk: CO, spec: ArraySpec) -> CI:
        """Decode via the wrapped numcodecs codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def encode_into(self, chunk: CI, buffer: Buffer, spec: ArraySpec) -> int:
        """Encode into ``buffer`` via the wrapped numcodecs codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def decode_into(self, chunk: CO, buffer: Buffer, spec: ArraySpec) -> int:
        """Decode into ``buffer`` via the wrapped numcodecs codec.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def recommended_concurrency(self) -> RecommendedConcurrency:
        """Report the wrapped codec's recommended concurrency.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...

    def partial_decode_capability(self) -> PartialDecodeCapability:
        """Report the wrapped codec's partial read/decode capability.

        Source: [proposals/codecs.md](../proposals/codecs.md) (inferred)
        """
        ...
