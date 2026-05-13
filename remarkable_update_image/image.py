import bz2
import io
import os
import struct
import sys
import time
from collections.abc import Callable, Generator
from hashlib import sha256
from typing import (
    Any,
    cast,
)

import libconf
from cachetools import TTLCache
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from indexed_gzip import (
    IndexedGzipFile as GzipFile,  # pyright: ignore[reportUnknownVariableType]
)

from ._compat import override
from .cpio import (
    Archive,
    Entry,
)
from .update_metadata_pb2 import (
    DeltaArchiveManifest,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
    InstallOperation,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
    Signatures,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
)


def sizeof_fmt(num: int | float, suffix: str = "B") -> str:
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0

    return f"{num:.1f}Yi{suffix}"


def range_contains(range1: range, range2: range) -> bool:
    return range1.start < range2.stop and range2.start < range1.stop


class BlockCache(TTLCache[tuple[int, int] | int, bytes]):
    def __init__(
        self,
        maxsize: int,
        ttl: int,
        timer: Callable[[], float] = time.monotonic,
        getsizeof: Callable[[object], int] = sys.getsizeof,
    ) -> None:
        super().__init__(maxsize, ttl, timer, getsizeof)

    @property
    def usage_str(self) -> str:
        return f"{self.curr_size_str}/{self.max_size_str}"

    @property
    def curr_size_str(self) -> str:
        return sizeof_fmt(self.currsize)

    @property
    def max_size_str(self) -> str:
        return sizeof_fmt(self.maxsize)

    def will_fit(self, value: bytes) -> bool:
        return self.maxsize >= self.getsizeof(value)


class UpdateImageException(Exception):
    pass


class UpdateImageSignatureException(UpdateImageException):
    def __init__(self, message: str, signed_hash: bytes, actual_hash: bytes) -> None:
        super().__init__(message)
        self.signed_hash: bytes = signed_hash
        self.actual_hash: bytes = actual_hash


class ProtobufUpdateImage(io.RawIOBase):
    def __init__(
        self, update_file: str, cache_size: int = 500, cache_ttl: int = 60
    ) -> None:
        self._pos: int = 0
        self.update_file: str = update_file
        self.cache_size: int = cache_size
        self._cache: BlockCache = BlockCache(
            maxsize=cache_size * 1024 * 1024,
            ttl=cache_ttl,
        )
        with open(self.update_file, "rb") as f:
            magic = f.read(4)
            if magic != b"CrAU":
                raise UpdateImageException("Wrong header")

            major = cast(int, struct.unpack(">Q", f.read(8))[0])
            if major != 1:
                raise UpdateImageException("Unsupported version")

            size = cast(int, struct.unpack(">Q", f.read(8))[0])
            data = f.read(size)
            self._manifest: DeltaArchiveManifest = DeltaArchiveManifest.FromString(data)  # pyright: ignore[reportUnknownMemberType]
            self._offset: int = f.tell()

        self._size: int = 0
        for _, _, length, _ in self._blobs:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            self._size += length

    def verify(self, publickey: bytes) -> None:
        _publickey = load_pem_public_key(publickey)
        with open(self.update_file, "rb") as f:
            data = f.read(self._offset + self._manifest.signatures_offset)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]

        actual_hash = sha256(data).digest()
        signature = self.signature
        assert signature is not None
        signed_hash = _publickey.recover_data_from_signature(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType, reportAttributeAccessIssue]
            signature,
            PKCS1v15(),
            SHA256(),
        )
        if actual_hash != signed_hash:
            raise UpdateImageSignatureException(
                "Actual hash does not match signed hash",
                signed_hash,  # pyright: ignore[reportUnknownArgumentType]
                actual_hash,
            )

    @property
    def block_size(self) -> int:
        return self._manifest.block_size  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    @property
    def signature(self) -> bytes | None:
        for signature in self._signatures:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if signature.version == 2:  # pyright: ignore[reportUnknownMemberType]
                return signature.data  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        return None

    @property
    def _signatures(self) -> Generator[Signatures.Signature]:  # pyright: ignore[reportUnknownParameterType, reportUnknownMemberType]
        with open(self.update_file, "rb") as f:
            _ = f.seek(self._offset + self._manifest.signatures_offset)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            yield from Signatures.FromString(  # pyright: ignore[reportUnknownMemberType]
                f.read(self._manifest.signatures_size)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
            ).signatures

    @property
    def _blobs(self) -> Generator[tuple[InstallOperation, int, int, io.BufferedReader]]:  # pyright: ignore[reportUnknownParameterType]
        with open(self.update_file, "rb") as f:
            for blob in self._manifest.partition_operations:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                _ = f.seek(self._offset + blob.data_offset)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                dst_offset = cast(
                    int,
                    blob.dst_extents[0].start_block * self.block_size,  # pyright: ignore[reportUnknownMemberType]
                )
                dst_length = cast(int, blob.dst_extents[0].num_blocks * self.block_size)  # pyright: ignore[reportUnknownMemberType]
                if blob.type not in (0, 1):  # pyright: ignore[reportUnknownMemberType]
                    raise UpdateImageException(f"Unsupported type {blob.type}")  # pyright: ignore[reportUnknownMemberType]

                yield blob, dst_offset, dst_length, f

        self.expire()

    def _read_blob(
        self,
        blob: InstallOperation,  # pyright: ignore[reportUnknownParameterType]
        blob_offset: int,
        blob_length: int,
        f: io.BufferedReader,
    ) -> bytes:
        if blob_offset in self._cache:
            return self._cache[blob_offset]

        if blob.type not in (  # pyright: ignore[reportUnknownMemberType]
            InstallOperation.Type.REPLACE,  # pyright: ignore[reportUnknownMemberType]
            InstallOperation.Type.REPLACE_BZ,  # pyright: ignore[reportUnknownMemberType]
        ):
            raise NotImplementedError(
                f"Error: {InstallOperation.Type.keys()[blob.type]} has not been implemented yet"  # pyright: ignore[reportUnknownMemberType]
            )

        blob_data = f.read(blob.data_length)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        if sha256(blob_data).digest() != blob.data_sha256_hash:  # pyright: ignore[reportUnknownMemberType]
            raise UpdateImageException("Error: Data has wrong sha256sum")

        if blob.type == InstallOperation.Type.REPLACE_BZ:  # pyright: ignore[reportUnknownMemberType]
            try:
                blob_data = bz2.decompress(blob_data)

            except ValueError as err:
                raise UpdateImageException(f"Error: {err}") from err

            if blob_length - len(blob_data) < 0:
                raise UpdateImageException(
                    f"Error: Bz2 compressed data was too large {len(blob_data)}"
                )

        # Zero padd data to fit
        if len(blob_data) < blob_length:
            blob_data += b"\0" * (blob_length - len(blob_data))

        assert len(blob_data) == blob_length
        if self._cache.will_fit(blob_data):
            self._cache[blob_offset] = blob_data

        return blob_data

    @property
    def cache(self) -> BlockCache:
        return self._cache

    @property
    def size(self) -> int:
        return self._size

    def expire(self) -> None:
        _ = self._cache.expire()

    @override
    def writable(self) -> bool:
        return False

    @override
    def seekable(self) -> bool:
        return True

    @override
    def readable(self) -> bool:
        return True

    @override
    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if whence not in (os.SEEK_SET, os.SEEK_CUR, os.SEEK_END):
            raise OSError("Not supported whence")

        if whence == os.SEEK_SET and offset < 0:
            raise ValueError("offset can't be negative")

        if whence == os.SEEK_END and offset > 0:
            raise ValueError("offset can't be positive")

        if whence == os.SEEK_SET:
            self._pos = min(max(offset, 0), self._size)

        elif whence == os.SEEK_CUR:
            self._pos = min(max(self._pos + offset, 0), self._size)

        elif whence == os.SEEK_END:
            self._pos = min(max(self._size + offset, 0), self._size)

        return self._pos

    @override
    def tell(self) -> int:
        return self._pos

    @override
    def read(self, size: int = -1) -> bytes:
        res = self.peek(size)
        _ = self.seek(len(res), whence=os.SEEK_CUR)
        return res

    def peek(self, size: int = 0) -> bytes:
        offset = self._pos
        if offset >= self._size:
            return b""

        if size <= 0 or offset + size > self._size:
            size = self._size - offset

        res = bytearray(size)
        for blob, blob_offset, blob_length, f in self._blobs:  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            if not range_contains(
                range(offset, offset + size),
                range(blob_offset, blob_offset + blob_length),
            ):
                if size >= self._size:
                    print(f"Skipping blob {blob_offset} to {blob_length}, {offset}")

                continue

            blob_data = self._read_blob(blob, blob_offset, blob_length, f)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            blob_start_offset = max(offset - blob_offset, 0)
            blob_end_offset = min(offset - blob_offset + size, blob_length)
            data = blob_data[blob_start_offset:blob_end_offset]

            assert blob_start_offset >= 0, (
                f"blob start offset is negative number: {blob_start_offset}"
            )
            assert blob_end_offset <= blob_length, (
                f"blob end offset is larger than blob length: {blob_end_offset}, {blob_length}"
            )
            assert blob_end_offset - blob_start_offset == len(data), (
                f"blob start and end is larger than data: {blob_end_offset - blob_start_offset}, {len(data)}"
                + f"\n  offset: {offset}"
                + f"\n  blob_offset: {blob_offset}"
                + f"\n  size: {size}"
                + f"\n  blob_length: {blob_length}"
                + f"\n  blob_start_offset: {blob_start_offset}"
                + f"\n  blob_end_offset: {blob_end_offset}"
                + f"\n  len(blob_data): {len(blob_data)}"
                + f"\n  blob.type: {blob.type}"  # pyright: ignore[reportUnknownMemberType]
            )

            start_offset = blob_offset + blob_start_offset - offset
            end_offset = blob_offset + blob_end_offset - offset
            res[start_offset:end_offset] = data

            assert start_offset >= 0, f"start offset is negative number: {start_offset}"
            assert start_offset < len(res), (
                f"start offset is larger than size of data: {start_offset}, {len(res)}"
            )
            assert end_offset <= blob_offset + blob_length, (
                f"end offset is larger than size of blob: {end_offset}, {blob_offset + blob_length}"
            )
            assert end_offset - start_offset == len(data), (
                f"size of offsets does not equal size of data, {end_offset - start_offset}, {len(data)}"
            )
            assert end_offset <= len(res), (
                f"end offset is larger than size of data, {end_offset}, {len(res)}"
            )
            assert res[start_offset:end_offset] == data, "data does not match"

        assert len(res) == size, (
            f"size of data does not match expected size: {len(res)}, {size}"
        )
        return bytes(res)


class CPIOUpdateImage(io.RawIOBase):
    def __init__(
        self, update_file: str, cache_size: int = 500, cache_ttl: int = 60
    ) -> None:
        self.update_file: str = update_file
        self.cache_size: int = cache_size
        self._cache: BlockCache = BlockCache(
            maxsize=cache_size * 1024 * 1024,
            ttl=cache_ttl,
        )
        self._archive: Archive = Archive(self.update_file)
        self._archive.open()
        if b"sw-description" not in self._archive.keys():
            raise UpdateImageException("Not a swupdate file")

        description = self._archive["sw-description"]
        assert description is not None
        info = cast(
            dict[str, dict[str, Any]],  # pyright: ignore[reportExplicitAny]
            libconf.loads(description.read().decode("utf-8")),  # pyright: ignore[reportUnknownMemberType]
        )["software"]
        self._version: str = cast(str, info.get("version"))

        self._hardware_type: str
        self._info: Any  # pyright: ignore[reportExplicitAny]
        if "reMarkable1" in info:
            self._hardware_type = "reMarkable1"
            self._info = info["reMarkable1"]

        elif "reMarkable2" in info:
            self._hardware_type = "reMarkable2"
            self._info = info["reMarkable2"]

        elif "ferrari" in info:
            self._hardware_type = "ferrari"
            self._info = info["ferrari"]

        elif "chiappa" in info:
            self._hardware_type = "chiappa"
            self._info = info["chiappa"]

        else:
            raise UpdateImageException("Unsupported swupdate file")

        # TODO - handle non-stable images
        # TODO - handle possibilities of multiple images
        entry = self._archive[self._info["stable"]["copy1"]["images"][0]["filename"]]  # pyright: ignore[reportAny]
        self._image: GzipFile = GzipFile(fileobj=entry, mode="rb")
        # Read entire image to allow seeking based on io.SEEK_END
        while self._image.read(131_672):  # pyright: ignore[reportUnknownMemberType]
            pass

        _ = self._image.seek(0, io.SEEK_SET)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    def verify(self, _publickey: str) -> None:
        # TODO - verify signature
        def verify_hash(expected_hash: str, entry: Entry) -> None:
            actual_hash = sha256(entry.peek()).hexdigest()
            if expected_hash != actual_hash:
                raise UpdateImageException(
                    "Actual hash does not match metadata hash",
                    expected_hash,
                    actual_hash,
                )

        def verify_copy(copy: dict[str, list[dict[str, str]]]) -> None:
            for image in (
                copy["images"] + copy.get("files", []) + copy.get("scripts", [])
            ):
                archive = self._archive[image["filename"]]
                assert archive is not None
                verify_hash(image["sha256"], archive)

        for copy in ("copy1", "copy2"):
            verify_copy(self._info["stable"][copy])  # pyright: ignore[reportAny]

    @property
    def signature(self) -> str | None:
        # TODO - get from entry
        return None

    @property
    def version(self) -> str | None:
        return self._version

    @property
    def hardware_type(self) -> str:
        return self._hardware_type

    @property
    def archive(self) -> Archive:
        return self._archive

    @property
    def cache(self) -> BlockCache:
        return self._cache

    @property
    def size(self) -> int:
        return self._image.size  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]

    def expire(self) -> None:
        _ = self._cache.expire()

    @override
    def close(self) -> None:
        try:
            self._archive.close()

        finally:
            super().close()

    @override
    def writable(self) -> bool:
        return False

    @override
    def seekable(self) -> bool:
        return True

    @override
    def readable(self) -> bool:
        return True

    @override
    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        return self._image.seek(offset, whence)  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]

    @override
    def tell(self) -> int:
        return self._image.tell()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    @override
    def read(self, size: int = -1) -> bytes:
        key = (self.tell(), size)
        if key in self._cache:
            return self._cache[key]

        data = self._image.read(size)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if self._cache.will_fit(data):  # pyright: ignore[reportUnknownArgumentType]
            self._cache[key] = data

        return data  # pyright: ignore[reportUnknownVariableType]

    def peek(self, size: int = 0) -> bytes:
        key = (self.tell(), size)
        if key in self._cache:
            return self._cache[key]

        data = self._image.peek(size)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if self._cache.will_fit(data):  # pyright: ignore[reportUnknownArgumentType]
            self._cache[key] = data

        return data  # pyright: ignore[reportUnknownVariableType]


class UpdateImage:
    def __new__(
        cls,
        update_file: str,
        cache_size: int = 500,
        cache_ttl: int = 60,
    ) -> ProtobufUpdateImage | CPIOUpdateImage:
        try:
            return ProtobufUpdateImage(update_file, cache_size, cache_ttl)

        except UpdateImageException:
            pass

        return CPIOUpdateImage(update_file, cache_size, cache_ttl)
