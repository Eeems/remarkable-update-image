import bz2
import io
import os
import struct
import sys
import time
import libconf

from indexed_gzip import IndexedGzipFile as GzipFile

from cachetools import TTLCache
from hashlib import sha256
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256

from .update_metadata_pb2 import DeltaArchiveManifest
from .update_metadata_pb2 import InstallOperation
from .update_metadata_pb2 import Signatures

from .cpio import Archive


def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def range_contains(range1, range2):
    return range1.start < range2.stop and range2.start < range1.stop


class BlockCache(TTLCache):
    def __init__(self, maxsize, ttl, timer=time.monotonic, getsizeof=sys.getsizeof):
        super().__init__(maxsize, ttl, timer, getsizeof)

    @property
    def usage_str(self):
        return f"{self.curr_size_str}/{self.max_size_str}"

    @property
    def curr_size_str(self):
        return sizeof_fmt(self.currsize)

    @property
    def max_size_str(self):
        return sizeof_fmt(self.maxsize)


class UpdateImageException(Exception):
    pass


class UpdateImageSignatureException(UpdateImageException):
    def __init__(self, message, signed_hash, actual_hash):
        super().__init__(self, message)
        self.signed_hash = signed_hash
        self.actual_hash = actual_hash


class ProtobufUpdateImage(io.RawIOBase):
    _manifest = None
    _offset = -1
    _size = 0
    _pos = 0

    def __init__(self, update_file, cache_size=500, cache_ttl=60):
        self.update_file = update_file
        self.cache_size = cache_size
        self._cache = BlockCache(
            maxsize=cache_size * 1024 * 1024,
            ttl=cache_ttl,
        )
        with open(self.update_file, "rb") as f:
            magic = f.read(4)
            if magic != b"CrAU":
                raise UpdateImageException("Wrong header")

            major = struct.unpack(">Q", f.read(8))[0]
            if major != 1:
                raise UpdateImageException("Unsupported version")

            size = struct.unpack(">Q", f.read(8))[0]
            data = f.read(size)
            self._manifest = DeltaArchiveManifest.FromString(data)
            self._offset = f.tell()

        for blob, offset, length, f in self._blobs:
            self._size += length

    def verify(self, publickey):
        _publickey = load_pem_public_key(publickey)
        with open(self.update_file, "rb") as f:
            data = f.read(self._offset + self._manifest.signatures_offset)

        actual_hash = sha256(data).digest()
        signed_hash = _publickey.recover_data_from_signature(
            self.signature,
            PKCS1v15(),
            SHA256(),
        )
        if actual_hash != signed_hash:
            raise UpdateImageSignatureException(
                "Actual hash does not match signed hash", signed_hash, actual_hash
            )

    @property
    def block_size(self):
        return self._manifest.block_size

    @property
    def signature(self):
        for signature in self._signatures:
            if signature.version == 2:
                return signature.data

        return None

    @property
    def _signatures(self):
        with open(self.update_file, "rb") as f:
            f.seek(self._offset + self._manifest.signatures_offset)
            for signature in Signatures.FromString(
                f.read(self._manifest.signatures_size)
            ).signatures:
                yield signature

    @property
    def _blobs(self):
        with open(self.update_file, "rb") as f:
            for blob in self._manifest.partition_operations:
                f.seek(self._offset + blob.data_offset)
                dst_offset = blob.dst_extents[0].start_block * self.block_size
                dst_length = blob.dst_extents[0].num_blocks * self.block_size
                if blob.type not in (0, 1):
                    raise UpdateImageException(f"Unsupported type {blob.type}")

                yield blob, dst_offset, dst_length, f

        self.expire()

    def _read_blob(self, blob, blob_offset, blob_length, f):
        if blob_offset in self._cache:
            return self._cache[blob_offset]

        if blob.type not in (
            InstallOperation.Type.REPLACE,
            InstallOperation.Type.REPLACE_BZ,
        ):
            raise NotImplementedError(
                f"Error: {InstallOperation.Type.keys()[blob.type]} has not been implemented yet"
            )

        blob_data = f.read(blob.data_length)
        if sha256(blob_data).digest() != blob.data_sha256_hash:
            raise UpdateImageException("Error: Data has wrong sha256sum")

        if blob.type == InstallOperation.Type.REPLACE_BZ:
            try:
                blob_data = bz2.decompress(blob_data)

            except ValueError as err:
                raise UpdateImageException(f"Error: {err}") from err

            if blob_length - len(blob_data) < 0:
                raise UpdateImageException(
                    f"Error: Bz2 compressed data was the wrong length {len(blob_data)}"
                )

        try:
            self._cache[blob_offset] = blob_data
        except ValueError as err:
            if str(err) != "value too large":
                raise err

        return blob_data

    @property
    def cache(self):
        return self._cache

    @property
    def size(self):
        return self._size

    def expire(self):
        self._cache.expire()

    def writable(self):
        return False

    def seekable(self):
        return False

    def readable(self):
        return True

    def seek(self, offset, whence=os.SEEK_SET):
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
            self._pos = min(max(self._pos + offset + self._size, 0), self._size)
        return self._pos

    def tell(self):
        return self._pos

    def read(self, size=-1):
        res = self.peek(size)
        self.seek(len(res), whence=os.SEEK_CUR)
        return res

    def peek(self, size=0):
        offset = self._pos
        if offset >= self._size:
            return b""

        if size <= 0 or offset + size > self._size:
            size = self._size - offset

        res = bytearray(size)
        for blob, blob_offset, blob_length, f in self._blobs:
            if not range_contains(
                range(offset, offset + size),
                range(blob_offset, blob_offset + blob_length),
            ):
                if size >= self._size:
                    print(f"Skipping blob {blob_offset} to {blob_length}, {offset}")

                continue

            blob_data = self._read_blob(blob, blob_offset, blob_length, f)
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
    def __init__(self, update_file, cache_size=500, cache_ttl=60):
        self.update_file = update_file
        self.cache_size = cache_size
        self._cache = BlockCache(
            maxsize=cache_size * 1024 * 1024,
            ttl=cache_ttl,
        )
        self._archive = Archive(self.update_file)
        self._archive.open()
        if b"sw-description" not in self._archive.keys():
            raise UpdateImageException("Not a swupdate file")

        info = libconf.loads(self._archive["sw-description"].read().decode("utf-8"))[
            "software"
        ]
        if "reMarkable1" in info:
            self._info = info["reMarkable1"]

        elif "reMarkable2" in info:
            self._info = info["reMarkable2"]

        elif "ferrari" in info:
            self._info = info["ferrari"]

        else:
            raise UpdateImageException("Unsupported swupdate file")

        # TODO - handle non-stable images
        # TODO - handle possibilities of multiple images
        info = self._info["stable"]["copy1"]["images"][0]
        entry = self._archive[info["filename"]]
        self._image = GzipFile(fileobj=entry, mode="rb")

    def verify(self, publickey):
        # TODO - verify signature
        def verify_hash(expected_hash, entry):
            actual_hash = sha256(entry.peek()).hexdigest()
            if expected_hash != actual_hash:
                raise UpdateImageException(
                    "Actual hash does not match metadata hash",
                    expected_hash,
                    actual_hash,
                )

        def verify_copy(copy):
            for image in copy["images"]:
                verify_hash(image["sha256"], self._archive[image["filename"]])

            for image in copy.get("files", []):
                verify_hash(image["sha256"], self._archive[image["filename"]])

            for image in copy.get("scripts", []):
                verify_hash(image["sha256"], self._archive[image["filename"]])

        for copy in ("copy1", "copy2"):
            verify_copy(self._info["stable"][copy])

    @property
    def signature(self):
        # TODO - get from entry
        return None

    @property
    def cache(self):
        return self._cache

    @property
    def size(self):
        return self._image.size

    def expire(self):
        self._cache.expire()

    def writable(self):
        return False

    def seekable(self):
        return False

    def readable(self):
        return True

    def seek(self, offset, whence=os.SEEK_SET):
        return self._image.seek(offset, whence)

    def tell(self):
        return self._image.tell()

    def read(self, size=-1):
        key = (self.tell(), size)
        if key in self._cache:
            return self._cache[key]

        self._cache[key] = data = self._image.read(size)
        return data

    def peek(self, size=0):
        key = (self.tell(), size)
        if key in self._cache:
            return self._cache[key]

        self._cache[key] = data = self._image.peek(size)
        return data


class UpdateImage:
    def __new__(cls, *args, **kwds):
        try:
            return ProtobufUpdateImage(*args, **kwds)

        except UpdateImageException:
            pass

        return CPIOUpdateImage(*args, **kwds)
