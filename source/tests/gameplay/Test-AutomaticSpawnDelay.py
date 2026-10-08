"""Build a private complete fastfile for automatic zero normal-spawn pacing."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "source"))
from patches.grenade_cleanup.fastfile_candidate import decode
from patches.gameplay.spawn_delay import apply, transform


def run(original: Path, output: Path, acts: Path) -> dict:
    lab = (Path.home() / ".codex/labs/bo3-engine").resolve()
    output = output.resolve()
    if lab not in output.parents or output.exists():
        raise ValueError("Use a new result directory inside the private BO3 lab.")
    source = original.read_bytes()
    assert hashlib.sha256(source).hexdigest() == "ed2134e10b1f57812bf8662926a269962a75b44d377cb5cca9245e86f2194a05"
    decoded, _ = decode(source)
    before = bytes(decoded)
    edit = apply(decoded)
    start = edit["scriptStart"]
    assert [i for i, (a, b) in enumerate(zip(before, decoded)) if a != b] == edit["changedOffsets"]
    assert len(edit["changedOffsets"]) == 5
    # The only new transfer skips normal pacing and enters the stock frame yield.
    delta = struct.unpack_from("<h", decoded, start + 0xDE36)[0]
    assert 0xDE38 + delta == 0xDE58
    assert struct.unpack_from("<f", decoded, start + 0xDE3C)[0] == 0.0
    assert decoded[start + 0xDE38:start + 0xDE3C] == before[start + 0xDE38:start + 0xDE3C]
    assert decoded[start + 0xDE40:start + 0xDE46] == before[start + 0xDE40:start + 0xDE46]
    assert decoded[start + 0xDE58:start + 0xDE6E] == before[start + 0xDE58:start + 0xDE6E]
    refused = []
    for name, data in [("repeated_apply", decoded), ("missing_script", bytearray(before[:start] + before[start + edit["scriptSize"]:])), ("changed_script", bytearray(before))]:
        if name == "changed_script":
            data[start + 0xDE36] ^= 1
        try:
            apply(data)
        except ValueError:
            refused.append(name)
        else:
            raise AssertionError("An unsupported stock script passed admission.")
    candidate = transform(source, output)
    assert decode(candidate)[0] == decoded
    output.mkdir(parents=True)
    (output / "zm_patch.ff").write_bytes(candidate)
    script = output / "normal-spawn.gscc"
    script.write_bytes(decoded[start:start + edit["scriptSize"]])
    result = subprocess.run([str(acts), "gscd", "-g", "-a", "-H", "-L", "-o", str(output / "decompiled"), str(script)], text=True, capture_output=True, check=True)
    (output / "acts.txt").write_text(result.stdout + result.stderr)
    text = next((output / "decompiled").rglob("_zm.gsc")).read_text()
    region = text[text.index("function round_spawning()\n{"):text.index("function get_zombie_count_for_round()")]
    assert 'wait level.zombie_vars[ "zombie_spawn_delay" ];' not in region
    assert "util::wait_network_frame();" in region
    assert "wait 0;" in region
    assert "wait 0.1;" in region
    assert 'level.zombie_vars[ "zombie_spawn_delay" ] = [[ level.func_get_zombie_spawn_delay ]]( get_round_number() );' in text
    report = {"status": "automatic_all_ordinary_spawn_zero_offline_asset_e2e_passed", "edit": edit, "candidateSha256": hashlib.sha256(candidate).hexdigest(), "refusals": refused, "normalConfiguredWaitSkipped": True, "positiveCounterSpawnWaitSeconds": 0, "preSpawnCapacityWaitsPreserved": True, "networkFrameYieldPreserved": True, "roundDelayWritersPreserved": True, "profilesWritten": False, "gameLaunched": False, "gameplayValidated": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--acts", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.original, args.output, args.acts), indent=2))
