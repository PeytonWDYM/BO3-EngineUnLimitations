"""Verify fixed physics preparation against a repeatable native crash and allocator replay."""
import argparse
from contextlib import redirect_stdout
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode


def run(module: Path, executable: Path, native_replay: Path, output: Path) -> dict:
    output = output.resolve()
    lab = (Path.home() / '.codex/labs/bo3-engine').resolve()
    if output.exists() or lab not in output.parents or lab not in native_replay.resolve().parents:
        raise ValueError('Use a private native replay and a new result file in the BO3 lab.')
    from physics_state import prepare_physics_state, GUARDS
    from runtime_recipe import prepare_recipe
    from runtime_templates import make_template, render_template

    code = CapturedCode(module, executable)
    edits = prepare_physics_state(code)
    assert len(edits) == 7 and all(not edit.stub for edit in edits)
    assert all(not edit.image_relative_operands and not edit.context_relative_operands for edit in edits)
    with redirect_stdout(io.StringIO()):
        native = runpy.run_path(str(native_replay))
    expected = {rva: bytes.fromhex(replacement) for rva, original, replacement in native['PRIVATE_CANDIDATE']}
    assert {edit.guard.rva: edit.replacement for edit in edits} == expected
    assert native['failure']['rip'] == '0x23f8515' and native['failure']['selectedRow'] == 95
    assert native['expanded']['rip'] == '0x23f8518' and not native['expanded']['faults']
    assert all(not row['faults'] for row in native['sizing'])
    assert all(not row['faults'] for row in native['contracts'])

    recipe = prepare_recipe(code, code.base + 0x20000000)
    sites = set(expected)
    assert tuple(edit for edit in recipe.edits if edit.guard.rva in sites) == edits
    render_cases = []
    for shift, delta in ((0, 0x20000000), (0x100000000, 0x24000000), (-0x100000000, 0x28000000)):
        for edit in edits:
            template = make_template(code, recipe, 'game', edit.guard.rva, edit.replacement)
            assert render_template(template, code, code.base + shift, code.base + shift + delta) == edit.replacement
        render_cases.append({'game': hex(code.base + shift), 'arena': hex(code.base + shift + delta)})

    class ChangedCode(CapturedCode):
        def read(self, rva, size):
            raw = bytearray(super().read(rva, size))
            if rva <= self.mutation < rva + size:
                raw[self.mutation-rva] ^= 1
            return bytes(raw)

    changed = object.__new__(ChangedCode)
    changed.__dict__.update(code.__dict__)
    refusals = []
    for guard in GUARDS:
        changed.mutation = guard.rva + guard.size // 2
        try:
            prepare_physics_state(changed)
        except ValueError:
            refusals.append({'rva': hex(changed.mutation), 'size': guard.size})
        else:
            raise AssertionError('A changed native physics guard escaped admission.')
    changed.mutation = -1
    changed.executable_sha256 = 'unknown'
    try:
        prepare_physics_state(changed)
    except ValueError:
        refusals.append({'kind': 'unknown executable'})
    else:
        raise AssertionError('An unknown executable escaped physics admission.')

    paths = (Path(__file__), PATCHES / 'physics_state.py', PATCHES / 'runtime_recipe.py', native_replay)
    report = {'passed': True, 'gameWrites': 0, 'authoredProviderEndpoints': 0,
              'edits': [asdict(edit) | {'replacement': edit.replacement.hex(), 'stub': edit.stub.hex()} for edit in edits],
              'nativeSizingCases': len(native['sizing']), 'nativeContracts': len(native['contracts']),
              'refusals': refusals, 'renderCases': render_cases,
              'sourceEdits': len(recipe.edits),
              'sourcePublications': sum((edit.guard.rva % 0x1000 + len(edit.replacement) + 0xFFF)//0x1000 for edit in recipe.edits),
              'bodies': sum(bool(edit.stub) for edit in recipe.edits),
              'sources': {str(path): hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for path in paths},
              'scope': 'Native preparation, original crash, complete sizing constructors, and native runtime row contracts. '
                       'OS hunk commits, complete DObj callbacks, persisted formats, and live gameplay require separate checks.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return {'passed': True, 'nativeSizingCases': report['nativeSizingCases'], 'nativeContracts': report['nativeContracts'],
            'refusals': len(refusals), 'renderCases': len(render_cases), 'sourceEdits': report['sourceEdits'], 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'native-replay', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.native_replay, args.output)))
