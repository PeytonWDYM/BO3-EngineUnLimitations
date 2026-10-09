"""Terminate an owned fixture at the VDF atomic-replacement boundary."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from patcher import steam_launch

root = Path(sys.argv[1])
action, moment = sys.argv[2:]
original = steam_launch.replace_bytes
config = root / "Steam/userdata/42/config/localconfig.vdf"


def interrupt(path, data):
    if path == config and moment == "before":
        os._exit(42)
    original(path, data)
    if path == config and moment == "after":
        os._exit(42)


steam_launch.replace_bytes = interrupt
manager = steam_launch.SteamPlay(root / "Steam", state=root / "state", process_running=lambda name: False)
if action == "enable":
    manager.enable(root / "resources", root / "game", tools_root=root / "tools")
else:
    manager.remove()
raise SystemExit("The owned crash boundary did not execute")
