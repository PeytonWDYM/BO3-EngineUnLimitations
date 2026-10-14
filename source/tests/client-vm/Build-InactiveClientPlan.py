"""Build guarded client count edits as an inactive artifact. Never opens a process."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from native_capture import EXACT_EXECUTABLE, file_digest, require

GUARD_RECEIPT_SHA256 = "605bbdad55f4f75d4e6759e6eaa93a71a0f9734ab49db4dfe2e78578f6c65975"


def build(inventory_path, executable, receipt_path):
    require(file_digest(executable) == EXACT_EXECUTABLE, "Unknown executable. Plan refused.")
    require(file_digest(receipt_path) == GUARD_RECEIPT_SHA256, "Unknown native guard receipt. Plan refused.")
    inventory = json.loads(inventory_path.read_text())
    require(inventory["executableSha256"] == EXACT_EXECUTABLE and inventory["stockTotal"] == 65000,
            "The client inventory identity differs.")
    receipt = json.loads(receipt_path.read_text())
    require(receipt["sha256"] == EXACT_EXECUTABLE and receipt["allGuardsMatch"]
            and receipt["allClientCountInstructionsMatch"], "The pinned native proof failed.")
    guards = inventory["codeGuards"]
    instructions = inventory["clientCountInstructions"]
    require(len(guards) == 40 and len(instructions) == 19, "The client guard/count inventory is incomplete.")
    require(len({row["rva"] for row in guards}) == 40 and len({row["rva"] for row in instructions}) == 19,
            "The client guard/count inventory has duplicate entries.")
    captured = {row["rva"]: row for row in receipt["guards"]}
    verified = []
    for guard in guards:
        source = captured[guard["rva"]]
        require(all(source[field] == guard[field] for field in ("ownerRva", "rva", "size", "sha256")),
                "A client guard differs from the pinned native proof.")
        data = (receipt_path.parent / source["file"]).read_bytes()
        require(len(data) == guard["size"] and hashlib.sha256(data).hexdigest() == guard["sha256"],
                f"Native guard bytes differ at RVA{guard['rva']:x}. Plan refused.")
        verified.append((guard, data))
    edits = []
    for instruction in instructions:
        expected = bytes.fromhex(instruction["bytes"])
        guard, data = next((guard, data) for guard, data in verified
                          if guard["rva"] <= instruction["rva"]
                          and instruction["rva"] + len(expected) <= guard["rva"] + len(data))
        start = instruction["rva"] - guard["rva"]
        offset = instruction["immediateOffset"]
        require(data[start:start + len(expected)] == expected
                and instruction["stockTotal"] == 65000
                and struct.unpack_from("<I", expected, offset)[0] == 65000,
                "A guarded native client instruction differs.")
        changed = bytearray(expected)
        struct.pack_into("<I", changed, offset, 250001)
        edits.append({"rva": instruction["rva"], "original": expected.hex(), "changed": changed.hex(),
                      "stockTotal": 65000, "candidateTotal": 250001, "immediateOffset": offset,
                      "guardOwnerRva": guard["ownerRva"], "pairedServerRva": instruction["pairedServerRva"]})
    return {"executableSha256": EXACT_EXECUTABLE, "guardReceiptSha256": GUARD_RECEIPT_SHA256,
            "scope": "Guarded count-edit artifact only. No process writes or production activation.",
            "candidateUsable": 250000, "codeGuards": guards, "instructionEdits": edits,
            "activationAllowed": False,
            "unclosedContracts": ["External module and retained-pointer ownership",
                "Complete unload/restart callbacks and arena lifetime", "Native string/module/API ownership",
                "Complete client save-container and compressed byte budgets",
                "Peer recipe and full Windows game-session evidence"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--guard-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    require(not output.is_relative_to(repo) and not output.exists(), "Use a new output folder outside Git.")
    plan = build(repo / "source/patches/client_vm/exact_build_inventory.json", args.executable, args.guard_receipt)
    output.mkdir(parents=True)
    (output / "inactive-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print("Nineteen client250001 instruction edits passed forty code guards. Activation remains disabled.")


if __name__ == "__main__":
    main()
