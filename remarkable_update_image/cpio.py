import io
import errno

from struct import pack

from ctypes import c_ushort
from ctypes import c_char
from ctypes import sizeof
from ctypes import Structure
from ctypes import LittleEndianStructure
from ctypes import BigEndianStructure


class MagicError(Exception):
    pass


class ChecksumError(Exception):
    pass


def to_hex(data):
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


class header_old_cpio_le(LittleEndianStructure):
    _fields_ = _header_old_cpio


class header_old_cpio_be(BigEndianStructure):
    _fields_ = _header_old_cpio


def _header_old_cpio_verify(self) -> None:
    if self.c_magic != 0o070707:
        raise MagicError(
            f"{self} magic bytes do not match! "
            f"expected={to_hex(0o070707)}, "
            f"actual={to_hex(self.c_magic)}"
        )


def _header_old_cpio_namesize(self) -> int:
    return self.c_namesize.value


def _header_old_cpio_filesize(self) -> int:
    return self.c_filesize.value


def _header_old_cpio_entrysize(self) -> int:
    return self.size + self.filesize + (self.filesize % 2)


def _header_old_cpio_size(self) -> int:
    return sizeof(self) + self.namesize + (self.namesize % 2)


header_old_cpio_le.verify = _header_old_cpio_verify
header_old_cpio_be.verify = _header_old_cpio_verify
header_old_cpio_le.namesize = property(_header_old_cpio_namesize)
header_old_cpio_be.namesize = property(_header_old_cpio_namesize)
header_old_cpio_le.filesize = property(_header_old_cpio_filesize)
header_old_cpio_be.filesize = property(_header_old_cpio_filesize)
header_old_cpio_le.entrysize = property(_header_old_cpio_entrysize)
header_old_cpio_be.entrysize = property(_header_old_cpio_entrysize)
header_old_cpio_le.size = property(_header_old_cpio_size)
header_old_cpio_be.size = property(_header_old_cpio_size)

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


class cpio_odc_header_le(LittleEndianStructure):
    _fields_ = _cpio_odc_header


class cpio_odc_header_be(BigEndianStructure):
    _fields_ = _cpio_odc_header


def _cpio_odc_header_verify(self) -> None:
    if self.c_magic != "070707":
        raise MagicError(
            f"{self} magic bytes do not match! "
            f"expected={'070707'}, "
            f"actual={self.c_magic}"
        )


def _cpio_odc_header_namesize(self) -> int:
    return int(self.c_namesize, 8)


def _cpio_odc_header_filesize(self) -> int:
    return int(self.c_filesize, 8)


def _cpio_odc_header_entrysize(self) -> int:
    return self.size + self.filesize + (self.filesize % 2)


def _cpio_odc_header_size(self) -> int:
    return sizeof(self) + self.namesize + (self.namesize % 2)


cpio_odc_header_le.verify = _cpio_odc_header_verify
cpio_odc_header_be.verify = _cpio_odc_header_verify
cpio_odc_header_le.namesize = property(_cpio_odc_header_namesize)
cpio_odc_header_be.namesize = property(_cpio_odc_header_namesize)
cpio_odc_header_le.filesize = property(_cpio_odc_header_filesize)
cpio_odc_header_be.filesize = property(_cpio_odc_header_filesize)
cpio_odc_header_le.entrysize = property(_cpio_odc_header_entrysize)
cpio_odc_header_be.entrysize = property(_cpio_odc_header_entrysize)
cpio_odc_header_le.size = property(_cpio_odc_header_size)
cpio_odc_header_be.size = property(_cpio_odc_header_size)

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


class cpio_newc_header_le(LittleEndianStructure):
    _fields_ = _cpio_newc_header


class cpio_newc_header_be(BigEndianStructure):
    _fields_ = _cpio_newc_header


def _cpio_newc_header_verify(self) -> None:
    if self.c_magic not in (b"070701", b"070702"):
        raise MagicError(
            f"{self} magic bytes do not match! "
            f"expected=070701 or 070702, "
            f"actual={self.c_magic}"
        )

    if self.c_magic == b"070702":
        # TODO - verify data
        pass


def _cpio_newc_header_namesize(self) -> int:
    return int(self.c_namesize, 16)


def _cpio_newc_header_filesize(self) -> int:
    return int(self.c_filesize, 16)


def _cpio_newc_header_entrysize(self) -> int:
    size = self.size + self.filesize
    if self.filesize % 4:
        size += 4 - (self.filesize % 4)

    return size


def _cpio_newc_header_size(self) -> int:
    size = sizeof(self) + self.namesize
    if size % 4:
        size += 4 - (size % 4)

    return size


cpio_newc_header_le.verify = _cpio_newc_header_verify
cpio_newc_header_be.verify = _cpio_newc_header_verify
cpio_newc_header_le.namesize = property(_cpio_newc_header_namesize)
cpio_newc_header_be.namesize = property(_cpio_newc_header_namesize)
cpio_newc_header_le.filesize = property(_cpio_newc_header_filesize)
cpio_newc_header_be.filesize = property(_cpio_newc_header_filesize)
cpio_newc_header_le.entrysize = property(_cpio_newc_header_entrysize)
cpio_newc_header_be.entrysize = property(_cpio_newc_header_entrysize)
cpio_newc_header_le.size = property(_cpio_newc_header_size)
cpio_newc_header_be.size = property(_cpio_newc_header_size)


class Entry:
    def __init__(self, fileobj, offset):
        self.fileobj = fileobj
        self.offset = offset
        self.cursor = 0
        self.header = self.read_header()
        self.header.verify()
        self.dataoffset = offset + self.header.size

    def __len__(self):
        return self.header.filesize

    def read_header(self) -> Structure:
        self.fileobj.seek(self.offset)
        magic = self.fileobj.read(sizeof(c_ushort))
        if magic == pack(">H", 0o070707):
            cls = header_old_cpio_be

        elif magic == pack("<H", 0o070707):
            cls = header_old_cpio_le

        else:
            self.fileobj.seek(self.offset)
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

        self.fileobj.seek(self.offset)
        data = self.fileobj.read(sizeof(cls))
        return cls.from_buffer_copy(data)

    @property
    def name(self) -> bytes:
        self.fileobj.seek(self.offset + sizeof(self.header))
        return self.fileobj.read(self.header.namesize).rstrip(b"\x00")

    @property
    def data(self) -> bytes:
        self.fileobj.seek(self.dataoffset)
        return self.fileobj.read(self.header.filesize)

    @property
    def size(self):
        return len(self)

    def writable(self):
        return False

    def seekable(self):
        return False

    def readable(self):
        return True

    def seek(self, offset, mode=io.SEEK_SET) -> None:
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

    def read(self, size=-1) -> bytes:
        if size < 0:
            size = len(self) - self.cursor

        data = self.peek(size)
        self.cursor += len(data)
        if size < len(data):
            raise OSError(errno.EIO, "Unexpected EOF")

        return data

    def peek(self, size=0) -> bytes:
        if self.cursor >= len(self):
            return b""

        if not size or size + self.cursor > len(self):
            size = len(self) - self.cursor

        self.fileobj.seek(self.dataoffset + self.cursor)
        return self.fileobj.read(size)


class Archive:
    def __init__(self, fileOrPath):
        self.fileOrPath = fileOrPath
        self.fileobj = None
        self.entries = {}

    def __enter__(self):
        self.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __getitem__(self, key: str | bytes) -> Entry | None:
        return self.get(key)

    def __len__(self) -> int:
        return len(self.entries)

    def open(self):
        if self.fileobj is not None:
            return

        if isinstance(self.fileOrPath, str):
            self.fileobj = open(self.fileOrPath, "rb")

        else:
            self.fileobj = self.fileOrPath

        offset = 0
        self.fileobj.seek(0, io.SEEK_END)
        size = self.fileobj.tell()
        self.fileobj.seek(0, io.SEEK_SET)
        while offset < size:
            entry = Entry(self.fileobj, offset)
            if entry.name == b"TRAILER!!!":
                break

            self.entries[entry.name] = entry
            offset += entry.header.entrysize

    def close(self):
        if isinstance(self.fileOrPath, str):
            self.fileobj.close()

        self.fileobj = None
        self.entries = {}

    def get(self, name: str | bytes, default=None) -> Entry | None:
        if isinstance(name, str):
            name = name.encode("ascii")

        if not isinstance(name, bytes):
            raise NotImplementedError()

        return self.entries.get(name, default)

    def keys(self) -> list[bytes]:
        return self.entries.keys()

    def values(self) -> list[Entry]:
        return self.entries.values()
