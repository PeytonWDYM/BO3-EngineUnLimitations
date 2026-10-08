"""Kill this owned fixture after its first target replacement."""
import os
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_transactions import Engine, features

base = Path(sys.argv[1])
original_replace = os.replace
def replace(source, target):
    mode = sys.argv[2] if len(sys.argv) > 2 else "first"
    if len(sys.argv) > 2 and sys.argv[2] == "original" and Path(target) == base / "state" / "originals" / "first.bin":
        os._exit(42)
    if mode == "receipt" and Path(target).parent.name == "active":
        os._exit(42)
    committed = mode == "commit" and Path(target).parent.name == "active" and json.loads(Path(source).read_text())["phase"] == "committed"
    original_replace(source, target)
    if mode == "first" and Path(target) == base / "install" / "first.ff":
        os._exit(42)
    if mode == "final" and Path(target) == base / "install" / "second.ff":
        os._exit(42)
    if committed:
        os._exit(42)

os.replace = replace
coordination_root = Path(sys.argv[3]) if len(sys.argv) > 3 else None
Engine({"workshop": base / "install"}, base / "state", features(), base, lambda: False, coordination_root=coordination_root).run("apply")
