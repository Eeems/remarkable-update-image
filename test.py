import os
import sys
import ext4
import errno
import difflib

from tempfile import TemporaryFile
from ext4 import ChecksumError
from ext4 import SymbolicLink
from ext4.struct import to_hex
from hashlib import md5
from hashlib import sha256
from remarkable_update_image import UpdateImage
from remarkable_update_image import UpdateImageSignatureException
from remarkable_update_image.image import sizeof_fmt
from remarkable_update_image.image import ProtobufUpdateImage
from remarkable_update_image.image import CPIOUpdateImage

FAILED = False


def assert_byte(reader, offset, byte):
    global FAILED
    reader.seek(offset)
    data = reader.read(1)
    print(f"checking offset {offset:08X} is {to_hex(byte)}: ", end="")
    if len(data) != 1:
        print("fail")
        FAILED = True
        print(f"  Error: {len(data)} bytes returned, only 1 expected: {to_hex(data)}")
        return

    if data != byte:
        print("fail")
        FAILED = True
        print(f"  Error: Data returned is {to_hex(data)}")
        return

    print("pass")


def assert_raw_byte(image, offset, byte):
    global FAILED
    _ = image.seek(offset)
    data = image.read(1)
    print(f"checking raw offset {offset:08X} is {to_hex(byte)}: ", end="")
    if len(data) != 1:
        print("fail")
        FAILED = True
        print(f"  Error: {len(data)} bytes returned, only 1 expected: {to_hex(data)}")
        return

    if data != byte:
        print("fail")
        FAILED = True
        print(f"  Error: Data returned is {to_hex(data)}")
        return

    print("pass")


def assert_exists(volume, path):
    global FAILED
    print(f"checking that {path} exists: ", end="")
    try:
        _ = volume.inode_at(path)
        print("pass")

    except FileNotFoundError:
        print("fail")
        FAILED = True


def assert_hash(volume, expected_hash, path):
    global FAILED
    print(f"checking {path} md5sum is {expected_hash}: ", end="")
    inode = volume.inode_at(path)
    actual_hash = md5(inode.open().read()).hexdigest()
    if actual_hash != expected_hash:
        print("fail")
        print(f"  Error: Hash returned is {actual_hash}")
        FAILED = True
        return

    print("pass")


def assert_symlink_to(volume, path, symlink):
    assert isinstance(symlink, bytes)
    global FAILED
    print(f"checking {path} is symlink to {symlink}: ", end="")
    inode = volume.inode_at(path)
    if not isinstance(inode, SymbolicLink):
        print("fail")
        FAILED = True
        print(f"  Error: Inode is not symlink: {inode}")
        return

    data = inode.readlink()
    if data != symlink:
        print("fail")
        print(f"  Error: symlink is actually to {data}")
        FAILED = True
        return

    print("pass")


def assert_ls(volume, path, expected):
    global FAILED
    print(f"checking {path} contents: ", end="")
    actual = [d.name_str for d, _ in volume.inode_at(path).opendir()]
    if expected == actual:
        print("pass")
        return

    print("fail")
    FAILED = True
    for diff in difflib.ndiff(expected, actual):
        print(f"  {diff}")


def assert_image_type(image, expected_type):
    global FAILED
    print(f"checking image is {expected_type.__name__}: ", end="")
    if isinstance(image, expected_type):
        print("pass")
        return

    print("fail")
    FAILED = True
    print(f"  Error: image is {type(image).__name__}")


def assert_attr(obj, attr, expected):
    global FAILED
    print(f"checking {attr} is {expected!r}: ", end="")
    actual = getattr(obj, attr)
    if actual == expected:
        print("pass")
        return

    print("fail")
    FAILED = True
    print(f"  Error: {attr} is {actual!r}")


def assert_no_attr(obj, attr):
    global FAILED
    print(f"checking {attr} attribute does not exist: ", end="")
    if not hasattr(obj, attr):
        print("pass")
        return

    print("fail")
    FAILED = True
    print(f"  Error: {attr} attribute exists with value {getattr(obj, attr)!r}")


def assert_in_archive(image, key):
    global FAILED
    print(f"checking archive contains {key}: ", end="")
    if key.encode() in image.archive.keys():
        print("pass")
        return

    print("fail")
    FAILED = True
    print(f"  Error: {key} not in archive")


def assert_extract(image, expected_digest):
    global FAILED
    print(f"checking extracting {image.update_file}: ", end="")
    try:
        _ = image.seek(0, os.SEEK_SET)
        with TemporaryFile(mode="wb") as f:
            digest = sha256(image.peek()).hexdigest()
            if expected_digest != digest:
                raise Exception(f"Incorrect digest: {digest}")

            _ = f.write(image.read())

        print("pass")

    except Exception as e:
        FAILED = True
        print("fail")
        print("  ", end="")
        print(e)


def validate_root_inode(volume):
    global FAILED
    print(f"validating root inode {volume.uuid}: ", end="")
    try:
        volume.root.validate()
        print("pass")

    except ChecksumError:
        print("fail")
        print(
            f"  {volume.root.checksum} != {volume.root.expected_checksum} {volume.root.fits_in_hi}"
        )
        FAILED = True


def assert_value(name, value, expected):
    global FAILED
    print(f"checking {name} is {expected}: ", end="")
    if value == expected:
        print("pass")
        return

    print("fail")
    print(f"  Error: {value}")
    FAILED = True


path = ".data/remarkable-production-memfault-image-3.11.3.3-rm1-public"
with UpdateImage(path) as image:
    assert_image_type(image, CPIOUpdateImage)
    assert_attr(image, "version", "3.11.3.3")
    assert_attr(image, "hardware_type", "reMarkable1")
    assert_in_archive(image, "sw-description")
    volume = ext4.Volume(image)
    validate_root_inode(volume)
    assert_ls(
        volume,
        "/",
        [
            ".",
            "..",
            "lost+found",
            "bin",
            "boot",
            "dev",
            "etc",
            "home",
            "lib",
            "media",
            "mnt",
            "postinst",
            "proc",
            "run",
            "sbin",
            "srv",
            "sys",
            "tmp",
            "uboot-version",
            "usr",
            "var",
        ],
    )
    assert_ls(
        volume,
        "/bin",
        [
            ".",
            "..",
            "rmdir",
            "sed",
            "chgrp",
            "systemctl",
            "bash.bash",
            "mountpoint",
            "chattr",
            "stat",
            "mount",
            "busybox",
            "systemd-sysext",
            "networkctl",
            "chown",
            "systemd-tmpfiles",
            "mktemp",
            "lsmod",
            "stty",
            "kill",
            "cpio",
            "true",
            "gzip",
            "df",
            "ps",
            "systemd-sysusers",
            "systemd-machine-id-setup",
            "dnsdomainname",
            "netstat",
            "dumpkmap",
            "su.shadow",
            "systemd-tty-ask-password-agent",
            "date",
            "kmod",
            "systemd-escape",
            "ln",
            "loginctl",
            "watch",
            "dmesg",
            "uname",
            "dd",
            "chmod",
            "busybox.nosuid",
            "busybox.suid",
            "usleep",
            "umount.util-linux",
            "cp",
            "more",
            "login",
            "journalctl",
            "ls",
            "false",
            "systemd-creds",
            "ash",
            "hostname",
            "touch",
            "base32",
            "ping",
            "sleep",
            "pidof",
            "systemd-inhibit",
            "grep",
            "tar",
            "getopt",
            "zcat",
            "umount",
            "egrep",
            "mknod",
            "rm",
            "fgrep",
            "cat",
            "sh",
            "pwd",
            "vi",
            "rev",
            "mkdir",
            "systemd-hwdb",
            "gunzip",
            "sync",
            "login.shadow",
            "lsmod.kmod",
            "systemd-notify",
            "systemd-ask-password",
            "su",
            "systemd-firstboot",
            "mv",
            "udevadm",
            "bash",
            "echo",
            "mount.util-linux",
            "run-parts",
        ],
    )
    assert_symlink_to(volume, "/bin/ash", b"/bin/busybox.nosuid")

cache_size = 1
raw_cache_size = cache_size * 1024 * 1024
read_size = raw_cache_size + 1
with UpdateImage(path, cache_size=cache_size) as image:
    print(
        f"checking reading larger than {sizeof_fmt(raw_cache_size)} cache size: ",
        end="",
    )
    try:
        data = image.read(read_size)
        data_size = len(data)
        if data_size != read_size:
            raise ValueError(
                f"data returned is not {sizeof_fmt(read_size)}: {sizeof_fmt(data_size)}"
            )

        print("pass")

    except ValueError as e:
        FAILED = True
        print("fail")
        print("  ", end="")
        print(e)

with UpdateImage(".data/2.13.0.758_reMarkable2-2N5B5nvpZ4-.signed") as image:
    assert_image_type(image, ProtobufUpdateImage)
    assert_no_attr(image, "version")
    volume = ext4.Volume(image)
    validate_root_inode(volume)
    print("checking image signature: ", end="")
    try:
        image.verify(
            volume.inode_at("/usr/share/update_engine/update-payload-key.pub.pem")
            .open()
            .read()
        )
        print("pass")

    except UpdateImageSignatureException:
        print("fail")

    assert_value("block count", volume.superblock.s_blocks_count, 261888)
    assert_value("free block count", volume.superblock.s_free_blocks_count, 38220)
    assert_value("inode count", volume.superblock.s_inodes_count, 65024)
    assert_value("free inode count", volume.superblock.s_free_inodes_count, 56414)

    inode = volume.inode_at("/bin/bash.bash")
    with inode.open() as reader:
        # Make sure that we aren't reading zeros where there should be a larger block of data
        assert_byte(reader, 0x00020000, b"\x0c")
        assert_byte(reader, 0x00020001, b"\x60")
        assert_byte(reader, 0x00020002, b"\x9d")
        # Make sure we return a non-zero where a kernel loopback would return data
        assert_byte(reader, 0x000BBFFF, b"\xe5")
        assert_byte(reader, 0x000BC000, b"\x54")

    assert_exists(volume, "/bin/bash.bash")
    assert_exists(volume, "/uboot-version")
    assert_exists(volume, "/home/root")
    assert_hash(volume, "21442141a3b145d11763862fcbecc40a", "/uboot-version")
    assert_hash(volume, "233a2dc8f0ab70fbd956b036438adefb", "/bin/bash.bash")
    assert_hash(
        volume,
        "6a67b9873c57fbb8589ef4a4f744beb3",
        "/usr/share/update_engine/update-payload-key.pub.pem",
    )
    assert_ls(
        volume,
        "/",
        [
            ".",
            "..",
            "lost+found",
            "bin",
            "boot",
            "dev",
            "etc",
            "home",
            "lib",
            "media",
            "mnt",
            "postinst",
            "proc",
            "run",
            "sbin",
            "sys",
            "tmp",
            "uboot-postinst",
            "uboot-version",
            "usr",
            "var",
        ],
    )
    assert_symlink_to(volume, "/bin/ash", b"/bin/busybox.nosuid")

    print("checking path that contains file raises ENOTDIR: ", end="")
    try:
        _ = volume.inode_at("/uboot-version/test")
        print("fail")
        print("  No error raised")
        FAILED = True

    except OSError as e:
        if e.errno == errno.ENOTDIR:
            print("pass")

        else:
            print("fail")
            FAILED = True
            print(
                f"  Unexpected error: {os.strerror(e.errno) if e.errno is not None else e}"
            )

    assert_extract(
        image,
        "ca65563b992e6d38e539f0a837416b8078903d7490d63aa9f6a059e431918d88",
    )

    # Make sure we aren't reading zeros in the raw image where there should be data
    assert_raw_byte(image, 0x00100000, b"\xed")
    assert_raw_byte(image, 0x00100001, b"\x41")
    assert_raw_byte(image, 0x00100002, b"\x00")

path = ".data/remarkable-production-memfault-image-3.20.0.92-rmpp-public"
with UpdateImage(path) as image:
    assert_image_type(image, CPIOUpdateImage)
    assert_attr(image, "version", "3.20.0.92")
    assert_attr(image, "hardware_type", "ferrari")
    assert_in_archive(image, "sw-description")
    volume = ext4.Volume(image)
    validate_root_inode(volume)
    assert_extract(
        image,
        "e8eec783c885df92d05dd53ba454949b6f0e5bd793038013df092786b54d6d5d",
    )

if FAILED:
    sys.exit(1)
