"""Lock one private setup folder during a complete transaction."""
from contextlib import AbstractContextManager
import os
from pathlib import Path

from patcher.errors import PatchError
from patcher.paths import private_path, reject_redirects


class StateLock(AbstractContextManager):
    def __init__(self, directory: Path):
        reject_redirects(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = private_path(directory, "lock")
        self.file = path.open("a+b")
        if self.file.seek(0, 2) == 0:
            self.file.write(b"\0")
            self.file.flush()
        self.file.seek(0)

    def __enter__(self):
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise PatchError("Another patcher uses an overlapping installation target.") from exc
        return self

    def __exit__(self, *_):
        self.file.close()
