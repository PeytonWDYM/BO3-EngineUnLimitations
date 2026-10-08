"""Extract a verified optional launcher pair and hand it the selected game."""
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from patcher.errors import PatchError
from patcher.paths import private_path, reject_redirects
from patcher.coordination import StateLock
from patcher.storage import durable_write
from patcher.windows import game_running

PAYLOAD_NAMES = ("BO3-Enhanced-Zombies.exe", "Bo3EnhancedHelper.dll", "Detours-LICENSE.md")
EXPERIMENTAL_NOTICE = ("EXPERIMENTAL: 500,000 server script slots for ordinary Zombies. "
                       "The 200 feature is unfinished. Game loading and friends are unvalidated. "
                       "Keep the launcher console open until the game exits.")


def available(resources: Path) -> bool:
    """Ordinary builds intentionally omit this optional native payload."""
    return (resources / "enhanced/manifest.json").is_file()


def _manifest(resources: Path) -> tuple[str, str, dict[str, str]]:
    if not available(resources):
        raise PatchError("The optional enhanced Zombies launcher is not bundled in this build.")
    manifest = json.loads((resources / "enhanced/manifest.json").read_text(encoding="utf-8-sig"))
    version = manifest.get("version", "")
    files = manifest.get("files", {})
    game_hash = manifest.get("gameSha256", "")
    if (manifest.get("schemaVersion") != 1 or manifest.get("status") != "experimental"
            or not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.-]{0,63}", version)
            or not isinstance(files, dict) or set(files) != set(PAYLOAD_NAMES)
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in [game_hash, *files.values()])):
        raise PatchError("The optional enhanced launcher manifest is invalid.")
    return version, game_hash, files


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _verify(folder: Path, hashes: dict[str, str], *, exact: bool) -> None:
    reject_redirects(folder, private_files=True)
    if exact and {path.name for path in folder.iterdir()} != set(hashes):
        raise PatchError("The extracted enhanced launcher folder contains unexpected files.")
    for name, expected in hashes.items():
        path = folder / name
        reject_redirects(path, private_files=True)
        if _hash(path) != expected:
            raise PatchError(f"Enhanced launcher payload hash mismatch: {name}")


def _admit_processes(process_running: Callable[[str], bool]) -> None:
    if process_running("BlackOps3.exe"):
        raise PatchError("Close Black Ops III before starting enhanced Zombies.")
    if process_running(PAYLOAD_NAMES[0]):
        raise PatchError("The enhanced Zombies launcher is already running. Wait for it to exit.")
    if not process_running("steam.exe"):
        raise PatchError("Start Steam before starting enhanced Zombies.")


@dataclass(frozen=True)
class LaunchIdentity:
    version: str
    hashes: dict[str, str]
    game: Path
    executable: Path


def _identity(resources: Path, game: Path) -> LaunchIdentity:
    version, game_hash, hashes = _manifest(resources)
    game = game.resolve(strict=True)
    executable = (game / "BlackOps3.exe").resolve(strict=True)
    if executable.parent != game or _hash(executable) != game_hash:
        raise PatchError("The selected BlackOps3.exe identity is unsupported for enhanced Zombies.")
    return LaunchIdentity(version, hashes, game, executable)


def _extract(resources: Path, identity: LaunchIdentity, tools_root: Path | None) -> Path:
    version, hashes, game = identity.version, identity.hashes, identity.game
    bundle = resources / "enhanced"
    _verify(bundle, hashes, exact=False)
    root = tools_root or Path(os.environ["LOCALAPPDATA"]) / "BO3 Engine UnLimitations/tools"
    root = private_path(root, installations=(game,))
    payload_id = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
    folder = private_path(root, f"{version}-{payload_id}", (game,))
    private_path(root, "lock", (game,))
    # Stage all files together; interruption cannot publish half of the pair.
    root.mkdir(parents=True, exist_ok=True)
    with StateLock(root):
        if folder.exists():
            _verify(folder, hashes, exact=True)
        else:
            stage = private_path(root, "stage-" + uuid.uuid4().hex, (game,))
            stage.mkdir()
            try:
                for name in PAYLOAD_NAMES:
                    durable_write(private_path(stage, name, (game,)), (bundle / name).read_bytes())
                _verify(stage, hashes, exact=True)
                private_path(root, folder.name, (game,))
                os.rename(stage, folder)
            finally:
                if stage.exists():
                    for name in PAYLOAD_NAMES:
                        private_path(stage, name, (game,)).unlink(missing_ok=True)
                    stage.rmdir()
        _verify(folder, hashes, exact=True)
    return folder


def prepare(resources: Path, game: Path, *, tools_root: Path | None = None) -> Path:
    """Verify and extract the complete pair without starting a game or requiring Steam."""
    return _extract(resources, _identity(resources, game), tools_root)


def play(resources: Path, game: Path, *, tools_root: Path | None = None,
         process_running: Callable[[str], bool] = game_running,
         spawn: Callable = subprocess.Popen) -> dict:
    """Provider arguments support owned fixtures; GUI/CLI always use the real providers."""
    identity = _identity(resources, game)
    _admit_processes(process_running)
    folder = _extract(resources, identity, tools_root)
    with StateLock(folder.parent):
        _admit_processes(process_running)
        _verify(folder, identity.hashes, exact=True)
        child = spawn([str(folder / PAYLOAD_NAMES[0]), str(identity.executable)], cwd=str(folder),
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
    return {"status": "launcher-started", "pid": child.pid, "toolsFolder": str(folder),
            "notice": EXPERIMENTAL_NOTICE}
