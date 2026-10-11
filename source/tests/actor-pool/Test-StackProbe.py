"""Export the complete guarded native stack probe for an owned Windows thread fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from temporal_rewind import PROBE_FUNCTION


def run(module: Path, executable: Path, output: Path) -> dict:
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    probe = code.guarded(PROBE_FUNCTION)
    output.mkdir(parents=True)
    binary = b'BO3PROB1' + struct.pack('<I', len(probe)) + probe
    (output / 'probe.bin').write_bytes(binary)
    receipt = {'scope': 'Guarded native helper export for owned Windows execution. No game patch.',
               'executableSha256': code.executable_sha256, 'helperSha256': PROBE_FUNCTION.sha256,
               'helperBytes': len(probe), 'inputSha256': hashlib.sha256(binary).hexdigest(),
               'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (PATCHES / 'temporal_rewind.py', Path(__file__))},
               'gameWrites': 0, 'activationAllowed': False}
    (output / 'input-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return {'output': str(output), 'bytes': len(probe)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output), indent=2))
