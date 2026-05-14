# pyright: reportUnnecessaryTypeIgnoreComment=false
# pyright: reportIgnoreCommentWithoutRule=false
# pyright: reportUnreachable=false
# pyright: reportExplicitAny=false
# pyright: reportAny=false
import os
import sys
from typing import (
    Protocol,
    runtime_checkable,
)

if sys.version_info < (3, 12):
    from typing_extensions import override

else:
    from typing import override


@runtime_checkable
class FileObj(Protocol):
    def read(self, size: int | None = -1, /) -> bytes: ...

    def tell(self) -> int: ...

    def seek(self, offset: int, whence: int = os.SEEK_SET, /) -> int: ...

    def close(self) -> None: ...


__all__ = ["override", "FileObj"]
