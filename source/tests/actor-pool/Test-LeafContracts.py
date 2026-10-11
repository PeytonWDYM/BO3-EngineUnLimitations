"""Replay guarded leaf admission against native captures and owned ABI failures."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode
from leaf_frames import verify_leaves
from unwind import native_frames


class OwnedCode:
    base = 0x10000000

    def __init__(self, raw: bytes):
        self.raw = raw

    def guarded(self, guard):
        assert guard.rva == 0x1000 and guard.size == len(self.raw)
        assert guard.sha256 == hashlib.sha256(self.raw).hexdigest()
        return self.raw


def run(module: Path, executable: Path, output: Path) -> dict:
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result path inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    contracts = json.loads((PATCHES / 'leaf_frames.json').read_text())['functions']
    native = verify_leaves(code, native_frames(code), contracts)
    cases = []
    failures = {
        'bl': 'b301c3', 'bh': 'b701c3', 'bx': '66bb0100c3',
        'bpl': '40b501c3', 'sil': '40b601c3', 'dil': '40b701c3',
        'r12b': '41b401c3', 'r15w': '6641bf0100c3',
        'xmm6': '660fef f6c3', 'xmm15': '66450fef ffc3',
        'ymm6': 'c5cdef f6c3', 'vzeroall': 'c5fc77c3',
        'mxcsr': '0fae10c3', 'x87_control': 'd928c3',
        'spl': '40b401c3', 'push': '50c3', 'call': 'e800000000c3',
        'indirect_jump': 'ffe0', 'conditional_escape': '750fc3',
        'ret_adjustment': 'c21000', 'far_return': 'cb',
        'privileged_exit': '0f07', 'fallthrough': '90',
    }
    for name, hex_bytes in failures.items():
        owned = OwnedCode(bytes.fromhex(hex_bytes))
        contract = [{'beginRva': '0x1000', 'endRva': hex(0x1000 + len(owned.raw)),
                     'sha256': hashlib.sha256(owned.raw).hexdigest()}]
        try:
            verify_leaves(owned, (), contract)
        except ValueError:
            cases.append({'case': name, 'refused': True, 'fixtureSha256': contract[0]['sha256']})
        else:
            raise AssertionError(f'The leaf admission accepted {name}.')
    for name, raw in [('volatile', bytes.fromhex('b001c3')), ('tail_jump', bytes.fromhex('e900100000')),
                      ('upper_vector_clear', bytes.fromhex('c5f877c3'))]:
        owned = OwnedCode(raw)
        contract = [{'beginRva': '0x1000', 'endRva': hex(0x1000 + len(raw)),
                     'sha256': hashlib.sha256(raw).hexdigest()}]
        verify_leaves(owned, (), contract)
        cases.append({'case': name, 'admitted': True})
    result = {'status': 'leaf_contract_admission_passed', 'nativeLeafFunctions': len(native),
              'cases': cases, 'moduleManifestSha256': hashlib.sha256(module.read_bytes()).hexdigest(),
              'sourceFiles': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [PATCHES / 'leaf_frames.py', PATCHES / 'leaf_frames.json', Path(__file__)]},
              'scope': 'Guarded native leaf classification and owned failure fixtures. No game writes or Windows unwind registration.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'status': result['status'], 'nativeLeafFunctions': len(native), 'cases': len(cases), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.output), indent=2))
