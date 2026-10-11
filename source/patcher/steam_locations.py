"""Read installed game paths from Steam library and app manifests."""
from pathlib import Path

from patcher.errors import PatchError
from patcher.vdf_span import Block, Token, parse


def installed_games(steam: Path) -> list[Path]:
    libraries = [steam]
    folders = steam / 'steamapps/libraryfolders.vdf'
    if folders.is_file():
        entries = parse(folders.read_text(encoding='utf-8-sig')).get('libraryfolders')
        if not isinstance(entries, Block):
            raise PatchError('Steam library folders are invalid. Select the game folder with Browse or --game.')
        for key, value in entries.entries:
            if not key.value.isdecimal():
                continue
            location = value.get('path') if isinstance(value, Block) else value
            if not isinstance(location, Token) or not Path(location.value).is_absolute():
                raise PatchError('A Steam library path is invalid. Select the game folder with Browse or --game.')
            libraries.append(Path(location.value))

    results = []
    seen: set[Path] = set()
    for library in libraries:
        library = library.resolve()
        if library in seen:
            continue
        seen.add(library)
        manifest = library / 'steamapps/appmanifest_311210.acf'
        directory = 'Call of Duty Black Ops III'
        if manifest.is_file():
            state = parse(manifest.read_text(encoding='utf-8-sig')).get('AppState')
            if not isinstance(state, Block):
                raise PatchError('The Black Ops III Steam manifest has no AppState block.')
            identity = state.get('appid')
            install = state.get('installdir')
            if not isinstance(identity, Token) or identity.value != '311210' or not isinstance(install, Token):
                raise PatchError('The Black Ops III Steam manifest has an invalid app ID or game folder.')
            relative = Path(install.value)
            if relative.anchor or len(relative.parts) != 1 or install.value in ('.', '..'):
                raise PatchError('The Black Ops III Steam manifest game folder must stay inside steamapps/common.')
            directory = install.value
        game = library / 'steamapps/common' / directory
        if (game / 'BlackOps3.exe').is_file():
            physical = game.resolve()
            if physical not in results:
                results.append(physical)
    return results
