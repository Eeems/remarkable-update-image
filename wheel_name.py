import sys
import json

from setuptools.command.bdist_wheel import get_platform


def get_abi():
    try:
        from wheel.pep425tags import get_abi_tag

        return get_abi_tag()
    except ModuleNotFoundError:
        pass

    try:
        from wheel.vendored.packaging import tags
    except ModuleNotFoundError:
        from packaging import tags

    name = tags.interpreter_name()
    version = tags.interpreter_version()
    return f"{name}{version}"


platform = get_platform(".")
abi = get_abi()
with open("pyproject.toml", "r") as f:
    lines = f.read().splitlines()

package = json.loads(
    [x for x in lines if x.startswith("name = ")][0].split("=")[1].strip()
)
version = json.loads(
    [x for x in lines if x.startswith("version = ")][0].split("=")[1].strip()
)

sys.stdout.write(f"{package}-{version}-{abi}-{abi}-{platform}.whl")
