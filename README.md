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
- python-build
- python-pip
- python-pipx
- python-venv
- python-wheel

```bash
make # Build wheel and sdist packages in dist/
make wheel # Build wheel package in dist/
make sdist # Build sdist package in dist/
make test # Run unit tests
make install # Build wheel and install it with pipx or pip install --user
```
