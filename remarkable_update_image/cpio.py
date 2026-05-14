import errno
import io
from collections.abc import (
    KeysView,
    ValuesView,
)
from ctypes import (
    BigEndianStructure,
    LittleEndianStructure,
    Structure,
    c_char,
    c_ushort,
    sizeof,
)
from struct import pack
from typing import final

from ._compat import FileObj


class MagicError(Exception):
    pass


class ChecksumError(Exception):
    pass


def to_hex(data: int | str) -> str:
    if isinstance(data, int):
        return f"0x{data:02X}"

    return "0x" + "".join([f"{x:02X}" for x in data])


_header_old_cpio = [
    ("c_magic", c_ushort),
    ("c_dev", c_ushort),
    ("c_ino", c_ushort),
    ("c_mode", c_ushort),
    ("c_uid", c_ushort),
    ("c_gid", c_ushort),
    ("c_nlink", c_ushort),
    ("c_rdev", c_ushort),
    ("c_mtime", c_ushort * 2),
    ("c_namesize", c_ushort),
    ("c_filesize", c_ushort * 2),
]


@final
class header_old_cpio_le(LittleEndianStructure):
    _fields_ = _header_old_cpio


@final
class header_old_cpio_be(BigEndianStructure):
    _fields_ = _header_old_cpio


def _header_old_cpio_verify(self: header_old_cpio_le | header_old_cpio_be) -> None:
    if self.c_magic != 0o070707:  # pyright: ignore[reportAny]
        raise MagicError(
            f"{self} magic bytes do not match! "
            + f"expected={to_hex(0o070707)}, "
            + f"actual={to_hex(self.c_magic)}"  # pyright: ignore[reportAny]
        )


def _header_old_cpio_namesize(self: header_old_cpio_le | header_old_cpio_be) -> int:
    return self.c_namesize.value  # pyright: ignore[reportAny]


def _header_old_cpio_filesize(self: header_old_cpio_le | header_old_cpio_be) -> int:
    return self.c_filesize.value  # pyright: ignore[reportAny]


def _header_old_cpio_entrysize(self: header_old_cpio_le | header_old_cpio_be) -> int:
    return self.size + self.filesize + (self.filesize % 2)  # pyright: ignore[reportAny]


def _header_old_cpio_size(self: header_old_cpio_le | header_old_cpio_be) -> int:
    return sizeof(self) + self.namesize + (self.namesize % 2)  # pyright: ignore[reportAny]


header_old_cpio_le.verify = _header_old_cpio_verify  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_be.verify = _header_old_cpio_verify  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_le.namesize = property(_header_old_cpio_namesize)  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_be.namesize = property(_header_old_cpio_namesize)  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_le.filesize = property(_header_old_cpio_filesize)  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_be.filesize = property(_header_old_cpio_filesize)  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_le.entrysize = property(_header_old_cpio_entrysize)  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_be.entrysize = property(_header_old_cpio_entrysize)  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_le.size = property(_header_old_cpio_size)  # pyright: ignore[reportAttributeAccessIssue]
header_old_cpio_be.size = property(_header_old_cpio_size)  # pyright: ignore[reportAttributeAccessIssue]

_cpio_odc_header = [
    ("c_magic", c_char * 6),
    ("c_dev", c_char * 6),
    ("c_ino", c_char * 6),
    ("c_mode", c_char * 6),
    ("c_uid", c_char * 6),
    ("c_gid", c_char * 6),
    ("c_nlink", c_char * 6),
    ("c_rdev", c_char * 6),
    ("c_mtime", c_char * 11),
    ("c_namesize", c_char * 6),
    ("c_filesize", c_char * 11),
]


@final
class cpio_odc_header_le(LittleEndianStructure):
    _fields_ = _cpio_odc_header


@final
class cpio_odc_header_be(BigEndianStructure):
    _fields_ = _cpio_odc_header


def _cpio_odc_header_verify(self: cpio_odc_header_le | cpio_odc_header_be) -> None:
    if self.c_magic != "070707":  # pyright: ignore[reportAny]
        raise MagicError(
            f"{self} magic bytes do not match! "
            + f"expected={'070707'}, "
            + f"actual={self.c_magic}"  # pyright: ignore[reportAny]
        )


def _cpio_odc_header_namesize(self: cpio_odc_header_le | cpio_odc_header_be) -> int:
    return int(self.c_namesize, 8)  # pyright: ignore[reportAny]


def _cpio_odc_header_filesize(self: cpio_odc_header_le | cpio_odc_header_be) -> int:
    return int(self.c_filesize, 8)  # pyright: ignore[reportAny]


def _cpio_odc_header_entrysize(self: cpio_odc_header_le | cpio_odc_header_be) -> int:
    return self.size + self.filesize + (self.filesize % 2)  # pyright: ignore[reportAny]


def _cpio_odc_header_size(self: cpio_odc_header_le | cpio_odc_header_be) -> int:
    return sizeof(self) + self.namesize + (self.namesize % 2)  # pyright: ignore[reportAny]


cpio_odc_header_le.verify = _cpio_odc_header_verify  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_be.verify = _cpio_odc_header_verify  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_le.namesize = property(_cpio_odc_header_namesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_be.namesize = property(_cpio_odc_header_namesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_le.filesize = property(_cpio_odc_header_filesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_be.filesize = property(_cpio_odc_header_filesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_le.entrysize = property(_cpio_odc_header_entrysize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_be.entrysize = property(_cpio_odc_header_entrysize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_le.size = property(_cpio_odc_header_size)  # pyright: ignore[reportAttributeAccessIssue]
cpio_odc_header_be.size = property(_cpio_odc_header_size)  # pyright: ignore[reportAttributeAccessIssue]

_cpio_newc_header = [
    ("c_magic", c_char * 6),
    ("c_ino", c_char * 8),
    ("c_mode", c_char * 8),
    ("c_uid", c_char * 8),
    ("c_gid", c_char * 8),
    ("c_nlink", c_char * 8),
    ("c_mtime", c_char * 8),
    ("c_filesize", c_char * 8),
    ("c_devmajor", c_char * 8),
    ("c_devminor", c_char * 8),
    ("c_rdevmajor", c_char * 8),
    ("c_rdevminor", c_char * 8),
    ("c_namesize", c_char * 8),
    ("c_check", c_char * 8),
]


@final
class cpio_newc_header_le(LittleEndianStructure):
    _fields_ = _cpio_newc_header


@final
class cpio_newc_header_be(BigEndianStructure):
    _fields_ = _cpio_newc_header


def _cpio_newc_header_verify(self: cpio_newc_header_le | cpio_newc_header_be) -> None:
    if self.c_magic not in (b"070701", b"070702"):  # pyright: ignore[reportAny]
        raise MagicError(
            f"{self} magic bytes do not match! "
            + "expected=070701 or 070702, "
            + f"actual={self.c_magic}"  # pyright: ignore[reportAny]
        )

    if self.c_magic == b"070702":
        # TODO - verify data
        pass


def _cpio_newc_header_namesize(self: cpio_newc_header_le | cpio_newc_header_be) -> int:
    return int(self.c_namesize, 16)  # pyright: ignore[reportAny]


def _cpio_newc_header_filesize(self: cpio_newc_header_le | cpio_newc_header_be) -> int:
    return int(self.c_filesize, 16)  # pyright: ignore[reportAny]


def _cpio_newc_header_entrysize(self: cpio_newc_header_le | cpio_newc_header_be) -> int:
    size: int = self.size + self.filesize  # pyright: ignore[reportAny]
    if self.filesize % 4:  # pyright: ignore[reportAny]
        size += 4 - (self.filesize % 4)  # pyright: ignore[reportAny]

    return size


def _cpio_newc_header_size(self: cpio_newc_header_le | cpio_newc_header_be) -> int:
    size: int = sizeof(self) + self.namesize  # pyright: ignore[reportAny]
    if size % 4:
        size += 4 - (size % 4)

    return size


cpio_newc_header_le.verify = _cpio_newc_header_verify  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_be.verify = _cpio_newc_header_verify  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_le.namesize = property(_cpio_newc_header_namesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_be.namesize = property(_cpio_newc_header_namesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_le.filesize = property(_cpio_newc_header_filesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_be.filesize = property(_cpio_newc_header_filesize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_le.entrysize = property(_cpio_newc_header_entrysize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_be.entrysize = property(_cpio_newc_header_entrysize)  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_le.size = property(_cpio_newc_header_size)  # pyright: ignore[reportAttributeAccessIssue]
cpio_newc_header_be.size = property(_cpio_newc_header_size)  # pyright: ignore[reportAttributeAccessIssue]


class Entry:
    def __init__(self, fileobj: FileObj, offset: int) -> None:
        self.fileobj: FileObj = fileobj
        self.offset: int = offset
        self.cursor: int = 0
        self.header: Structure = self.read_header()
        self.header.verify()  # pyright: ignore[reportAny]
        self.dataoffset: int = offset + self.header.size  # pyright: ignore[reportAny]

    def __len__(self) -> int:
        return self.header.filesize  # pyright: ignore[reportAny]

    def read_header(self) -> Structure:
        _ = self.fileobj.seek(self.offset)
        magic = self.fileobj.read(sizeof(c_ushort))
        if magic == pack(">H", 0o070707):
            cls = header_old_cpio_be

        elif magic == pack("<H", 0o070707):
            cls = header_old_cpio_le

        else:
            _ = self.fileobj.seek(self.offset)
            magic = self.fileobj.read(sizeof(c_char * 6))
            if magic == b"070707":
                cls = cpio_odc_header_le

            # elif magic == b"070707":
            #     cls = cpio_odc_header_be

            elif magic in (b"070701", b"070702"):
                cls = cpio_newc_header_le

            # elif magic in (b"070701", b"070702"):
            #     cls = cpio_newc_header_be

            else:
                raise MagicError(f"Unknown magic: {magic}")

        _ = self.fileobj.seek(self.offset)
        data = self.fileobj.read(sizeof(cls))
        return cls.from_buffer_copy(data)

    @property
    def name(self) -> bytes:
        _ = self.fileobj.seek(self.offset + sizeof(self.header))
        return self.fileobj.read(self.header.namesize).rstrip(b"\x00")  # pyright: ignore[reportAny]

    @property
    def data(self) -> bytes:
        _ = self.fileobj.seek(self.dataoffset)
        return self.fileobj.read(self.header.filesize)  # pyright: ignore[reportAny]

    @property
    def size(self) -> int:
        return len(self)

    def writable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, mode: int = io.SEEK_SET) -> None:
        if mode == io.SEEK_CUR:
            offset += self.cursor

        elif mode == io.SEEK_END:
            offset += len(self)

        elif mode != io.SEEK_SET:
            raise NotImplementedError()

        if offset < 0:
            raise OSError(errno.EINVAL, "Invalid argument")

        self.cursor = offset

    def tell(self) -> int:
        return self.cursor

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self) - self.cursor

        data = self.peek(size)
        self.cursor += len(data)
        if size < len(data):
            raise OSError(errno.EIO, "Unexpected EOF")

        return data

    def peek(self, size: int = 0) -> bytes:
        if self.cursor >= len(self):
            return b""

        if not size or size + self.cursor > len(self):
            size = len(self) - self.cursor

        _ = self.fileobj.seek(self.dataoffset + self.cursor)
        return self.fileobj.read(size)


class Archive:
    def __init__(self, fileOrPath: str | FileObj) -> None:
        self.fileOrPath: str | FileObj = fileOrPath
        self.fileobj: FileObj | None = None
        self.entries: dict[bytes, Entry] = {}

    def __enter__(self) -> None:
        self.open()

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
        self.close()

    def __getitem__(self, key: str | bytes) -> Entry | None:
        return self.get(key)

    def __len__(self) -> int:
        return len(self.entries)

    def open(self) -> None:
        if self.fileobj is not None:
            return

        if isinstance(self.fileOrPath, str):
            self.fileobj = open(self.fileOrPath, "rb")

        else:
            self.fileobj = self.fileOrPath

        offset = 0
        _ = self.fileobj.seek(0, io.SEEK_END)
        size = self.fileobj.tell()
        _ = self.fileobj.seek(0, io.SEEK_SET)
        while offset < size:
            entry = Entry(self.fileobj, offset)
            if entry.name == b"TRAILER!!!":
                break

            self.entries[entry.name] = entry
            offset += entry.header.entrysize  # pyright: ignore[reportAny]

    def close(self) -> None:
        if isinstance(self.fileOrPath, str):
            assert self.fileobj is not None
            self.fileobj.close()

        self.fileobj = None
        self.entries = {}

    def get(self, name: str | bytes, default: Entry | None = None) -> Entry | None:
        if isinstance(name, str):
            name = name.encode("ascii")

        return self.entries.get(name, default)

    def keys(self) -> KeysView[bytes]:
        return self.entries.keys()

    def values(self) -> ValuesView[Entry]:
        return self.entries.values()
