"""Generate the pinned client250K manifest for the default launcher."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

INVENTORY_SHA256 = 'ebef4676a7f935d93ea231adeec349ddad5d03de8fecdc3008898528c1875110'


def generate(inventory_path: Path, output: Path) -> None:
    # Git checkouts can change source line endings. Native guard digests remain exact binary digests.
    raw = inventory_path.read_bytes().replace(b'\r\n', b'\n')
    if hashlib.sha256(raw).hexdigest() != INVENTORY_SHA256:
        raise ValueError('The client inventory differs from the reviewed exact-build profile.')
    inventory = json.loads(raw)
    counts, guards = inventory['clientCountInstructions'], inventory['codeGuards']
    if len(counts) != 19 or len(guards) != 40:
        raise ValueError('The exact client inventory is incomplete.')
    if len({row['rva'] for row in counts}) != 19 or len({row['rva'] for row in guards}) != 40:
        raise ValueError('The exact client inventory has duplicate sites.')

    def byte_list(data: bytes) -> str:
        return '{' + ','.join(f'0x{value:02x}' for value in data) + '}'

    lines = ['#pragma once', '#include "ClientProfile.h"', 'namespace bo3::enhanced {',
             'inline constexpr std::array<CountInstruction,19> ClientCounts{{']
    for row in counts:
        data = bytes.fromhex(row['bytes'])
        offset = row['immediateOffset']
        if not (5 <= len(data) <= 6 and 0 <= offset <= len(data) - 4
                and struct.unpack_from('<I', data, offset)[0] == 65000
                and any(guard['rva'] <= row['rva'] and row['rva'] + len(data) <= guard['rva'] + guard['size'] for guard in guards)):
            raise ValueError('A complete client instruction lacks its stock count or guard.')
        lines.append(f'{{0x{row["rva"]:x},{byte_list(data)},{len(data)},{offset}}},')
    lines += ['}};', 'inline constexpr std::array<CodeGuard,40> ClientGuards{{']
    for row in guards:
        digest = bytes.fromhex(row['sha256'])
        if not (len(digest) == 32 and row['size'] > 0 and 0 <= row['rva'] <= inventory['imageSize'] - row['size']):
            raise ValueError('A client guard exceeds the admitted image.')
        lines.append(f'{{0x{row["rva"]:x},{row["size"]},{byte_list(digest)}}},')
    lines += ['}};', 'inline constexpr ClientManifest ExactClientManifest{ClientCounts,ClientGuards};', '}']
    if output.exists():
        raise FileExistsError('Use a new generated client header path.')
    output.write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.inventory, args.output)
