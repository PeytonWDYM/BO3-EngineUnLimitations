"""Failure-first fixture for the inactive client plan, using pinned native proof files."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from native_capture import require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--guard-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.is_relative_to(Path(__file__).resolve().parents[3]), "Keep evidence outside Git.")
    output.mkdir(parents=True, exist_ok=False)
    planner = Path(__file__).with_name("Build-InactiveClientPlan.py")
    rows = []

    def run(name, executable, receipt, successful):
        target = output / name
        result = subprocess.run([sys.executable, str(planner), "--executable", str(executable),
                                 "--guard-receipt", str(receipt), "--output", str(target)], capture_output=True, text=True)
        (output / f"{name}.stdout.txt").write_text(result.stdout)
        (output / f"{name}.stderr.txt").write_text(result.stderr)
        require((result.returncode == 0) == successful, f"Unexpected inactive plan outcome: {name}.")
        require(target.exists() == successful, "A refused plan wrote output.")
        rows.append({"case": name, "exitCode": result.returncode, "artifactWritten": successful})

    unknown = output / "unknown-executable.bin"
    unknown.write_bytes(b"unknown native identity")
    run("unknown-identity-refused", unknown, args.guard_receipt, False)
    unknown_receipt = output / "unknown-receipt.json"
    unknown_receipt.write_text("{}")
    run("unknown-guard-proof-refused", args.executable, unknown_receipt, False)
    captured = output / "mutated-native-guard"
    shutil.copytree(args.guard_receipt.parent, captured)
    receipt = json.loads(args.guard_receipt.read_text())
    guard = captured / receipt["guards"][0]["file"]
    original = guard.read_bytes(); changed = bytearray(original); changed[-1] ^= 1
    guard.write_bytes(changed)
    run("one-native-byte-refused", args.executable, captured / args.guard_receipt.name, False)
    run("exact-guarded-inactive-plan", args.executable, args.guard_receipt, True)
    plan_path = output / "exact-guarded-inactive-plan/inactive-plan.json"
    plan = json.loads(plan_path.read_text())
    require(len(plan["instructionEdits"]) == 19 and len(plan["codeGuards"]) == 40
            and plan["candidateUsable"] == 250000 and not plan["activationAllowed"], "The inactive candidate contract differs.")
    result = {"cases": rows, "passed": True, "activationAllowed": False,
              "planSha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
              "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Three refusal cases and the exact guarded inactive client plan passed.")


if __name__ == "__main__":
    main()
