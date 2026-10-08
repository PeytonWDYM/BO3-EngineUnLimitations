"""Rebuild a private sprint-fire asset and inspect its native attack cancellation path."""
import argparse, hashlib, json, struct, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'source'))
from patches.grenade_cleanup.fastfile_candidate import decode, SOURCE_HASH
from patches.gameplay.script_features import apply_spawn_delay, rebuild
from patches.weapon_tuning.sprint_fire import apply_decoded, SCRIPT_SIZE
from sprint_eligibility_replay import verify as verify_eligibility


def run(source: Path, acts: Path, output: Path):
    source_bytes = source.read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == SOURCE_HASH
    output = output.resolve()
    lab = (Path.home() / '.codex/labs/bo3-engine').resolve()
    if lab not in output.parents or output.exists():
        raise ValueError('Use a new private lab result directory.')
    decoded, _ = decode(source_bytes)
    # The composer applies the separately verified spawn edit before sprint-fire.
    spawn = apply_spawn_delay(decoded)
    before = bytes(decoded)
    report = apply_decoded(decoded)
    start = report['scriptStart']
    expected = {start + 0x2adbc + i for i, (a,b) in enumerate(zip(bytes.fromhex('01426e3a8fe03c5401000104'), bytes.fromhex('cf2f54885ce7d7d401000124'))) if a != b}
    assert {i for i,(a,b) in enumerate(zip(before, decoded)) if a != b} == expected
    assert decoded[start+0x1864e:start+0x18652] == bytes.fromhex('bd362c00')
    for name, bad in [('repeat', decoded), ('truncated', decoded[:start+40])]:
        try: apply_decoded(bytearray(bad))
        except ValueError: pass
        else: raise AssertionError(f'Accepted {name}')
    corrupted = bytearray(before); corrupted[start+0x2adc7] ^= 1
    try: apply_decoded(corrupted)
    except ValueError: pass
    else: raise AssertionError('Accepted changed prototype')
    restored = bytearray(decoded); restored[start+0x2adbc:start+0x2adc8] = bytes.fromhex('01426e3a8fe03c5401000104')
    assert restored == before
    candidate = rebuild(source_bytes, decoded)
    assert decode(candidate)[0] == decoded
    output.mkdir(parents=True)
    (output/'core_mod.ff').write_bytes(candidate)
    script = output/'commands-sprintfire.gscc'; script.write_bytes(decoded[start:start+SCRIPT_SIZE])
    completed = subprocess.run([str(acts),'gscd','-g','-a','-H','-L','-o',str(output/'decompiled'),str(script)], capture_output=True,text=True,check=True)
    (output/'acts.txt').write_text(completed.stdout+completed.stderr)
    text = next((output/'decompiled').rglob('motherfucker.gsc')).read_text()
    assert 'self setperk( "specialty_sprintfire" );' not in text
    assert 'self function_e974f053( "specialty_sprintfire" );' in text
    assert 'self function_92f3c278( "specialty_sprintfire" );' in text
    assert 'self hasperk( "specialty_staminup" ) || isdefined( self.beastmode ) && self.beastmode == 1 || weapon.name == "t6_xl_shockhands"' in text
    assert 'if ( self namespace_543ce08f::function_3a6e4201( "specialty_staminup" ) )' in text
    report['eligibilityBytecodeReplay'] = verify_eligibility(before[start:start+SCRIPT_SIZE], bytes(decoded[start:start+SCRIPT_SIZE]))
    report['eligibilityReplayScope'] = 'Restricted bytecode/import/branch replay; complete GSC VM and gameplay remain unvalidated.'
    report.update(sourceSha256=SOURCE_HASH, candidateSha256=hashlib.sha256(candidate).hexdigest(), unrelatedDecodedBytesPreserved=True, restorationVerified=True, independentDisassemblyVerified=True, nativeCancellationReplay='Passed in separate sprint-predicate-replay.json artifact', gameLaunched=False, gameplayValidated=False)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True); p.add_argument('--acts',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); print(json.dumps(run(a.source,a.acts,a.output),indent=2))
