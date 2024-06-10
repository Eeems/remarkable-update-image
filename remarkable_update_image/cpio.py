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


"""
https://manpages.ubuntu.com/manpages/focal/man5/cpio.5.html

Use c_magic to determine if little or big endian

struct header_old_cpio {
   unsigned short   c_magic;
   unsigned short   c_dev;
   unsigned short   c_ino;
   unsigned short   c_mode;
   unsigned short   c_uid;
   unsigned short   c_gid;
   unsigned short   c_nlink;
   unsigned short   c_rdev;
   unsigned short   c_mtime[2];
   unsigned short   c_namesize;
   unsigned short   c_filesize[2];
};
c_magic = 070707

struct cpio_odc_header {
   char    c_magic[6];
   char    c_dev[6];
   char    c_ino[6];
   char    c_mode[6];
   char    c_uid[6];
   char    c_gid[6];
   char    c_nlink[6];
   char    c_rdev[6];
   char    c_mtime[11];
   char    c_namesize[6];
   char    c_filesize[11];
};
c_magic = '070707'

struct cpio_newc_header {
   char    c_magic[6];
   char    c_ino[8];
   char    c_mode[8];
   char    c_uid[8];
   char    c_gid[8];
   char    c_nlink[8];
   char    c_mtime[8];
   char    c_filesize[8];
   char    c_devmajor[8];
   char    c_devminor[8];
   char    c_rdevmajor[8];
   char    c_rdevminor[8];
   char    c_namesize[8];
   char    c_check[8];
};
c_magic = 070701

struct cpio_newcrc_header{
    cpio_newc_header;
}
c_magic = 070702
c_check is least-significant 32 bits of the sum of all bytes in file data treated as unsigned integers
"""