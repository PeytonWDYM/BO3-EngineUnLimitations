"""Private complete-asset checks for script enhancement preparation.

Record failure cases before implementation. This test never launches BO3.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "source"))
from patches.grenade_cleanup.fastfile_candidate import decode, change_script, find_script, SCRIPT_SIZE
from patches.gameplay.script_features import apply_commands, apply_spawn_delay, apply_storm, rebuild


def rejected(call):
    try:
        call()
    except ValueError:
        return True
    raise AssertionError("An unsupported asset passed admission.")


def run(original: Path, map_original: Path, output: Path, acts: Path):
    output = output.resolve()
    lab = (Path.home() / ".codex/labs/bo3-engine").resolve()
    if lab not in output.parents or output.exists():
        raise ValueError("Use a new result directory inside the private BO3 lab.")
    output.mkdir(exist_ok=False, parents=True)
    source = original.read_bytes()
    decoded, _ = decode(source)
    cleanup_start = find_script(decoded)
    clean, _ = change_script(decoded[cleanup_start:cleanup_start + SCRIPT_SIZE])
    decoded[cleanup_start:cleanup_start + SCRIPT_SIZE] = clean
    before = bytes(decoded)
    release_decoded = bytearray(before)
    release_edit = apply_spawn_delay(release_decoded)
    assert release_decoded[cleanup_start:cleanup_start + SCRIPT_SIZE] == clean
    assert [i for i, (a, b) in enumerate(zip(before, release_decoded)) if a != b] == release_edit["changedOffsets"]
    start = release_edit["scriptStart"]
    for offset in (0x184A2, 0x184AC, 0x184B8, 0x184C6):
        assert release_decoded[start + offset] == 64
    rejected(lambda: apply_spawn_delay(release_decoded))
    release_candidate = rebuild(source, release_decoded)
    assert decode(release_candidate)[0] == release_decoded
    (output / "core_mod-zero-only.ff").write_bytes(release_candidate)
    release_script = output / "commands-zero-only.gscc"
    release_script.write_bytes(release_decoded[start:start + release_edit["scriptSize"]])
    edits = apply_commands(decoded)
    assert decoded[cleanup_start:cleanup_start + SCRIPT_SIZE] == clean
    assert [i for i, (a, b) in enumerate(zip(before, decoded)) if a != b] == sorted(edits["changedOffsets"])
    rejected(lambda: apply_commands(decoded))
    absent = bytearray(before)
    absent[edits["scriptStart"]] ^= 1
    rejected(lambda: apply_commands(absent))
    repeated = bytearray(before + before[edits["scriptStart"]:edits["scriptStart"] + edits["scriptSize"]])
    rejected(lambda: apply_commands(repeated))
    candidate = rebuild(source, decoded)
    assert decode(candidate)[0] == decoded
    (output / "core_mod.ff").write_bytes(candidate)
    (output / "commands.gscc").write_bytes(decoded[edits["scriptStart"]:edits["scriptStart"] + edits["scriptSize"]])
    map_source = map_original.read_bytes()
    map_decoded, _ = decode(map_source)
    storm_before = bytes(map_decoded)
    storm = apply_storm(map_decoded)
    assert [i for i, (a, b) in enumerate(zip(storm_before, map_decoded)) if a != b] == storm["changedOffsets"]
    rejected(lambda: apply_storm(map_decoded))
    storm_candidate = rebuild(map_source, map_decoded)
    assert decode(storm_candidate)[0] == map_decoded
    (output / "zm_castle_patch.ff").write_bytes(storm_candidate)
    (output / "storm.gscc").write_bytes(map_decoded[storm["scriptStart"]:storm["scriptStart"] + storm["scriptSize"]])
    # Independent decompiler checks the transformed code and every branch target.
    completed = subprocess.run([str(acts), "gscd", "-g", "-a", "-H", "-L", "-o", str(output / "decompiled"), str(output / "commands.gscc"), str(output / "storm.gscc")], capture_output=True, text=True, check=True)
    (output / "acts.txt").write_text(completed.stdout + completed.stderr)
    commands = next((output / "decompiled").rglob("motherfucker.gsc")).read_text()
    storm_text = next((output / "decompiled").rglob("_zm_weap_elemental_bow_storm.gsc")).read_text()
    assert commands.count("level.zombie_ai_limit = 200;") == 1
    assert commands.count("level.zombie_actor_limit = 200;") == 1
    assert "getdvarint( \"zm_limit\" ) > 200" in commands
    assert 'level.zombie_vars[ "zombie_spawn_delay" ] = getdvarfloat( "spawn" );' in commands
    assert "i < 3" in storm_text
    assert 'waittill_any_timeout( 7.8, "elem_storm_whirlwind_force_off" )' in storm_text
    assert 'notify( #"elem_storm_whirlwind_done" )' in storm_text
    zero_result = subprocess.run([str(acts), "gscd", "-g", "-a", "-H", "-L", "-o", str(output / "zero-decompiled"), str(release_script)], capture_output=True, text=True, check=True)
    (output / "acts-zero.txt").write_text(zero_result.stdout + zero_result.stderr)
    zero_text = next((output / "zero-decompiled").rglob("motherfucker.gsc")).read_text()
    assert "getdvarint( \"zm_limit\" ) > 64" in zero_text
    assert "level.zombie_ai_limit = 64;" in zero_text
    assert "level.zombie_actor_limit = 64;" in zero_text
    assert "level.zombie_ai_limit = 200;" not in zero_text
    assert "goto LOC_0000094e;" in zero_text
    report = {"status": "offline_asset_e2e_passed", "cleanupPreserved": True, "commands": edits, "releaseZeroOnly": release_edit, "releaseStockActorClampPreserved": True, "storm": storm, "coreCandidateSha256": hashlib.sha256(candidate).hexdigest(), "releaseZeroOnlyCoreSha256": hashlib.sha256(release_candidate).hexdigest(), "stormCandidateSha256": hashlib.sha256(storm_candidate).hexdigest(), "gameLaunched": False, "nativeActorCapacityValidated": False, "multiplayerValidated": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--map-original", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--acts", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.original, args.map_original, args.output, args.acts), indent=2))
