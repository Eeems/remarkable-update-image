[![remarkable_update_image on PyPI](https://img.shields.io/pypi/v/remarkable_update_image)](https://pypi.org/project/remarkable_update_image)

# reMarkable Update Image
Read a reMarkable update image as a block device.

## Known Issues

- Will report checksum errors for Directory inode, even though they are fine
- Will report checksum errors for extent headers, even though they are fine

## Usage

```python
from ext4 import Volume
from remarkable_update_image import UpdateImage

image = UpdateImage("path/to/update/file.signed")

# Extract raw ext4 image
with open("image.ext4", "wb") as f:
    f.write(image.read())

# Extract specific file
volume = Volume(image)
inode = volume.inode_at("/etc/version")
with open("version", "wb") as f:
    f.write(inode.open().read())
```

## Building
Dependencies:
- curl
- protoc
- python
- [emake](https://github.com/Eeems/emake)

```shell
emake build --wheel --native
make images
emake test --wheel
```
