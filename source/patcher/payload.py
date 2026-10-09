"""Select one verified game build and stage its complete native payload together."""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from typing import TypedDict

from patcher.coordination import StateLock
from patcher.errors import PatchError
from patcher.paths import private_path, reject_redirects
from patcher.storage import durable_write

PAYLOAD_NAMES = ('BO3-500K-Zombies.exe', 'Bo3EnhancedHelper.dll', 'Bo3StartupGate.dll', 'Detours-LICENSE.md')


class Build(TypedDict):
    id: str
    gameSha256: str
    runtime: str
    files: dict[str, str]


def file_hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def builds(resources: Path) -> list[Build]:
    manifest = json.loads((resources / 'release.json').read_text(encoding='utf-8'))
    if manifest['schemaVersion'] != 1 or not manifest['builds']:
        raise PatchError('The release has no supported game profiles.')
    result: list[Build] = manifest['builds']
    identities: set[str] = set()
    for build in result:
        if (not re.fullmatch(r'[a-z0-9-]+', build['id']) or build['runtime'] != 'windows'
                or set(build['files']) != set(PAYLOAD_NAMES)
                or any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in [build['gameSha256'], *build['files'].values()])
                or build['gameSha256'] in identities):
            raise PatchError('A release game profile is invalid or duplicated.')
        identities.add(build['gameSha256'])
    return result


def supported_build(resources: Path, game: Path) -> Build:
    executable = game / 'BlackOps3.exe'
    reject_redirects(executable, private_files=True)
    digest = file_hash(executable)
    for build in builds(resources):
        if build['gameSha256'] == digest:
            return build
    raise PatchError(f'Unsupported game version (SHA-256 {digest}). Install was refused. Download a release for this build.')


def verify(folder: Path, hashes: dict[str, str]) -> None:
    for name, expected in hashes.items():
        path = folder / name
        reject_redirects(path, private_files=True)
        if file_hash(path) != expected:
            raise PatchError(f'The {name} release file changed. Install was refused.')


def prepare(resources: Path, game: Path, *, tools_root: Path | None = None) -> Path:
    build = supported_build(resources, game)
    source = resources / 'native' / build['id']
    verify(source, build['files'])
    root = private_path(tools_root or Path(os.environ['LOCALAPPDATA']) / 'BO3 Engine UnLimitations/500k', installations=(game,))
    identity = hashlib.sha256(json.dumps(build['files'], sort_keys=True).encode()).hexdigest()[:20]
    folder = private_path(root, build['id'] + '-' + identity, (game,))
    with StateLock(root):
        if folder.exists():
            if {p.name for p in folder.iterdir()} != set(PAYLOAD_NAMES):
                raise PatchError('The installed launcher folder has unexpected files.')
            verify(folder, build['files'])
        else:
            stage = private_path(root, 'stage-' + uuid.uuid4().hex, (game,))
            stage.mkdir()
            try:
                for name in PAYLOAD_NAMES:
                    durable_write(private_path(stage, name, (game,)), (source / name).read_bytes())
                verify(stage, build['files'])
                stage.rename(folder)
            finally:
                if stage.exists():
                    for path in stage.iterdir():
                        path.unlink()
                    stage.rmdir()
        verify(folder, build['files'])
    return folder
