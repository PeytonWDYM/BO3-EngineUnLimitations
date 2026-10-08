"""Copy dependency license notices next to the Windows distribution."""
import importlib.metadata
from pathlib import Path
import shutil
import sys

output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=False)
shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", output / "Python-LICENSE.txt")
for name in ("PyInstaller", "pefile", "altgraph", "packaging", "pyinstaller-hooks-contrib", "pywin32-ctypes", "setuptools"):
    distribution = importlib.metadata.distribution(name)
    for entry in distribution.files:
        if entry.name.lower().startswith(("license", "copying")) and entry.suffix.lower() in {"", ".txt", ".md", ".apache", ".bsd"}:
            target = output / name / str(entry)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(distribution.locate_file(entry), target)
for notice in (Path(sys.base_prefix) / "tcl").rglob("license.terms"):
    target = output / "Tcl-Tk" / notice.relative_to(Path(sys.base_prefix) / "tcl")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(notice, target)
