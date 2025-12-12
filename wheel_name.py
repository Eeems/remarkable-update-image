import sys
import json


def get_platform() -> str:
    import platform

    if platform.system() != "Darwin":
        from setuptools.command.bdist_wheel import get_platform  # pyright: ignore[reportMissingModuleSource]

        return get_platform(None)

    arch = platform.machine()
    if arch == "arm64":
        return f"macosx-11.0-{arch}"

    return f"macosx-10.13-{arch}"


def get_arch() -> str:
    import platform

    return platform.machine()


def get_abi() -> str:
    try:
        from wheel.pep425tags import get_abi_tag  # pyright: ignore[reportMissingImports, reportUnknownVariableType]

        return get_abi_tag()  # pyright: ignore[reportUnknownVariableType]

    except ModuleNotFoundError:
        pass

    try:
        from wheel.vendored.packaging import tags  # pyright: ignore[reportMissingImports, reportUnknownVariableType]

    except ModuleNotFoundError:
        from packaging import tags

    return f"{tags.interpreter_name()}{tags.interpreter_version()}"  # pyright: ignore[reportUnknownMemberType]


match sys.argv[-1]:
    case "--platform":
        _ = sys.stdout.write(get_platform())

    case "--archflags":
        _ = sys.stdout.write(f"-arch {get_arch()}")

    case _:
        with open("pyproject.toml", "r") as f:
            lines = f.read().splitlines()

        package = json.loads(  # pyright: ignore[reportAny]
            [x for x in lines if x.startswith("name = ")][0].split("=")[1].strip()
        )
        version = json.loads(  # pyright: ignore[reportAny]
            [x for x in lines if x.startswith("version = ")][0].split("=")[1].strip()
        )
        platform = get_platform().replace(".", "_").replace("-", "_")
        abi = get_abi()
        _ = sys.stdout.write(f"{package}-{version}-{abi}-{abi}-{platform}.whl")
