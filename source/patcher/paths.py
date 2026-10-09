"""Private write paths cannot redirect through reparse points or symlinks."""
import os
from pathlib import Path
import stat

from patcher.errors import PatchError


def reject_redirects(path: Path, *, private_files: bool = False) -> None:
    for ancestor in (*reversed(path.parents), path):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise PatchError(f"A private patcher path redirects through a link: {ancestor}")
        if private_files and stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise PatchError(f"A private patcher file has multiple hard links: {ancestor}")


def private_path(base: Path, relative: str = ".", installations=()) -> Path:
    path = Path(os.path.abspath(base / relative))
    reject_redirects(path, private_files=True)
    physical = path.resolve()
    physical_base = base.resolve()
    if physical != physical_base and physical_base not in physical.parents:
        raise PatchError("A private patcher path is outside its backup or coordination folder.")
    if any(physical == root or root in physical.parents for root in installations):
        raise PatchError("Keep patcher backups and coordination outside the game and Workshop folders.")
    return path


def check_state(base: Path, installations=()) -> None:
    private_path(base, installations=installations)
    for name in ("lock", "journal.json", "originals"):
        private_path(base, name, installations)
    if base.exists():
        for directory in base.iterdir():
            if directory.name == "originals" or directory.name.startswith("txn-"):
                private_path(base, directory.name, installations)
                if directory.is_dir():
                    for child in directory.iterdir():
                        private_path(base, str(child.relative_to(base)), installations)
