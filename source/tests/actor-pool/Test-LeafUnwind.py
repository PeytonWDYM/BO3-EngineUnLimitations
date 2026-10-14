"""Export exact guarded leaf stubs and phase records for a Windows unwind replay."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from shape import ActorShape
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from storage_plan import StorageLayout
from table_plan import prepare
from unwind import requirements
from leaf_unwind import prepare_leaf_phases


def run(module: Path, executable: Path, output: Path, actors: int = 300) -> dict:
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    layout = TableLayout(NativeSentientAddress(code.base + 0x21000000), ExternalTableAddress(code.base + 0x22000000), ActorShape(actors))
    storage = StorageLayout(*(code.base + offset for offset in (0x24000000, 0x26000000, 0x28000000, 0x2A000000, 0x2C000000)))
    plan = prepare(code, layout, code.base + 0x20000000, storage)
    owners = requirements(code, plan.rewrites)
    leaf_sites = {int(row['siteRva'], 0) for row in owners if row['kind'] in ('verified_native_leaf', 'leaf_allocation')}
    leaves = [edit for edit in plan.rewrites if edit.guard.rva in leaf_sites]
    assert len(leaves) == 17
    data = bytearray(b'BO3LFUW1' + struct.pack('<I', len(leaves)))
    rows = []
    for edit in leaves:
        phases = prepare_leaf_phases(edit)
        assert phases[0].begin == 0 and phases[-1].end == len(edit.stub)
        data += struct.pack('<II', len(edit.stub), len(phases)) + edit.stub
        for phase in phases:
            data += struct.pack('<IIII', phase.begin, phase.end, phase.stack_bytes, len(phase.unwind_info))
            data += phase.unwind_info
        rows.append({'siteRva': hex(edit.guard.rva), 'stubSha256': hashlib.sha256(edit.stub).hexdigest(),
                     'instructionBoundaryProbes': len(phases), 'stackDepths': sorted({phase.stack_bytes for phase in phases})})
    output.mkdir(parents=True)
    (output / 'leaf-unwind.bin').write_bytes(data)
    result = {'scope': 'Owned Windows unwind input only. Native frame continuations and live registration remain gated.',
              'leafStubs': rows, 'fixtureSha256': hashlib.sha256(data).hexdigest(), 'actors': actors,
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [PATCHES / 'leaf_unwind.py', PATCHES / 'leaf_frames.py', Path(__file__)]},
              'moduleManifestSha256': hashlib.sha256(module.read_bytes()).hexdigest(), 'gameWrites': 0}
    (output / 'input-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    return {'output': str(output), 'leafStubs': len(leaves), 'fixtureSha256': result['fixtureSha256']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--actors', type=int, choices=(300, 500), default=300)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output, args.actors), indent=2))
