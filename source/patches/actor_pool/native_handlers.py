"""Guard researched GS-only owner recipes. This does not bind or activate a game handler."""
from dataclasses import dataclass
import json
from pathlib import Path
import struct

from captured_code import CapturedCode, CodeGuard
from native_unwind import NativeFrame


@dataclass(frozen=True)
class NativeHandlerRecipe:
    image_base: int
    runtime: tuple[int, int, int]
    handler_address: int
    handler_data_address: int
    prolog_bytes: int
    cookie_offset: int


def prepare_native_handler(code: CapturedCode, frame: NativeFrame) -> NativeHandlerRecipe:
    inventory = json.loads((Path(__file__).parent / 'native_handlers.json').read_text())
    for name in ('handler', 'common', 'cookie'):
        item = inventory[name]
        code.guarded(CodeGuard(int(item['rva'], 0), item['size'], item['sha256']))
    while frame.parent is not None:
        frame = frame.parent
    item = next((item for item in inventory['roots'] if tuple(int(value, 0) for value in item['runtime']) == frame.runtime), None)
    if item is None:
        raise ValueError('The native handler owner has no admitted GS-only recipe.')
    metadata = code.guarded(CodeGuard(frame.runtime[2], item['size'], item['sha256']))
    tail = 4 + ((metadata[2] + 1) & ~1) * 2
    handler, cookie_word = struct.unpack_from('<II', metadata, tail)
    if handler != 0x2BC3A04 or metadata[0] >> 3 != 3 or metadata[3] or cookie_word & 7 or tail + 8 != len(metadata):
        raise ValueError('The native root differs from its researched GS-only frame contract.')
    return NativeHandlerRecipe(code.base, frame.runtime, code.base + handler,
                               code.base + frame.runtime[2] + tail + 4, metadata[1], cookie_word)
