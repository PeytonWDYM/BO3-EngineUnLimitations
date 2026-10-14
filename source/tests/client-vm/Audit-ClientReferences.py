"""Inventory exact captured VM code and unresolved consumers. This never opens a process."""
import argparse
import bisect
import hashlib
import json
import re
import struct
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_IMM, CS_OP_MEM
from capstone.x86_const import X86_REG_RIP
from native_capture import NativeCapture, require


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = NativeCapture(args.manifest, args.executable)
    output = args.output.resolve()
    require(not output.is_relative_to(Path(__file__).resolve().parents[3]), "Keep evidence outside Git.")
    output.mkdir(exist_ok=False)
    pe = pefile.PE(data=capture.read(0, 0x49000), fast_load=True)
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    functions = sorted(struct.iter_unpack("<III", capture.read(directory.VirtualAddress, directory.Size)))
    starts = [row[0] for row in functions]

    def owner(rva):
        index = bisect.bisect_right(starts, rva) - 1
        if index >= 0 and functions[index][0] <= rva < functions[index][1]:
            return functions[index]
        return None

    # Candidate encodings are checked against decoded instructions in their unwind fragment.
    selected = {row for row in functions if 0x12c8000 <= row[0] < 0x12f1000}
    unowned = set()
    section_hashes = []
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        start = section.VirtualAddress
        code = capture.read(start, section.Misc_VirtualSize)
        section_hashes.append({"rva": start, "size": len(code), "sha256": hashlib.sha256(code).hexdigest()})
        candidates = set()
        for match in re.finditer(rb"..[\x12\x13]\x05", code, re.S):
            value = struct.unpack("<I", match.group())[0]
            if 0x5124500 <= value < 0x5140000:
                candidates.add(start + match.start())
        for match in re.finditer(rb"[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....", code, re.S):
            target = start + match.start() + 5 + struct.unpack_from("<i", match.group(), 1)[0]
            if 0x5124500 <= target < 0x5140000 or 0x3267228 <= target < 0x3267240:
                candidates.add(start + match.start())
        for match in re.finditer(rb"[\xe8\xe9]....", code, re.S):
            target = start + match.start() + 5 + struct.unpack_from("<i", match.group(), 1)[0]
            if 0x12c8000 <= target < 0x12f1000:
                candidates.add(start + match.start())
        for rva in candidates:
            fragment = owner(rva)
            if fragment is None:
                unowned.add(rva)
            else:
                selected.add(fragment)

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True
    globals_found, vm_calls, indirect_calls, fragments = [], [], [], []
    for start, end, unwind in sorted(selected):
        code = capture.read(start, end - start)
        instructions = list(md.disasm(code, start))
        rows = []
        for ins in instructions:
            rows.append(f"{ins.address:08x} {ins.bytes.hex()} {ins.mnemonic} {ins.op_str}")
            for operand in ins.operands:
                if operand.type != CS_OP_MEM:
                    continue
                address = operand.mem.disp
                kind = "module displacement candidate"
                if operand.mem.base == X86_REG_RIP:
                    address += ins.address + ins.size
                    kind = "RIP-relative native global"
                if 0x5124500 <= address < 0x5140000 or 0x3267228 <= address < 0x3267240:
                    globals_found.append({"instructionRva": ins.address, "fragmentRva": start,
                        "targetRva": address, "operandBytes": operand.size, "kind": kind,
                        "instruction": f"{ins.mnemonic} {ins.op_str}"})
            if ins.mnemonic in ("call", "jmp"):
                target = ins.operands[0]
                if target.type == CS_OP_IMM and 0x12c8000 <= target.imm < 0x12f1000:
                    vm_calls.append({"instructionRva": ins.address, "fragmentRva": start,
                                     "targetRva": target.imm, "kind": ins.mnemonic})
                elif target.type != CS_OP_IMM:
                    indirect_calls.append({"instructionRva": ins.address, "fragmentRva": start,
                                           "instruction": f"{ins.mnemonic} {ins.op_str}"})
        if any(row["fragmentRva"] == start for row in globals_found) or 0x12c8000 <= start < 0x12f1000:
            (output / f"fragment-{start:x}.asm").write_text("\n".join(rows) + "\n")
        fragments.append({"startRva": start, "endRva": end, "unwindRva": unwind,
                          "bytesSha256": hashlib.sha256(code).hexdigest(),
                          "decodedBytes": sum(ins.size for ins in instructions), "size": len(code)})

    reader = struct.unpack("<26I", capture.read(0x12d5eac, 26 * 4))
    writer = struct.unpack("<26I", capture.read(0x12d70dc, 26 * 4))
    branches = {0x12d5d49: "DWORD payload", 0x12d5d64: "native string import",
                0x12d5d81: "three floats and native vector allocation", 0x12d5de2: "float payload",
                0x12d5e01: "QWORD payload", 0x12d5e18: "byte namespace and DWORD API index",
                0x12d5e75: "native code-position import", 0x12d5e81: "native suspended-stack import",
                0x12d5d17: "two DWORD payload fields"}
    types = []
    for numeric_type in range(28):
        pointer = struct.unpack("<Q", capture.read(0x3267240 + numeric_type * 8, 8))[0]
        name = capture.read(pointer - capture.base, 100).split(b"\0")[0].decode("ascii")
        row = {"numericType": numeric_type, "nativeName": name}
        if 1 <= numeric_type <= 26:
            row.update(readerBranchRva=reader[numeric_type - 1], writerBranchRva=writer[numeric_type - 1],
                       readerContract=branches[reader[numeric_type - 1]])
        else:
            row["readerContract"] = "no typed payload" if numeric_type == 0 else "free record: QWORD link payload"
        types.append(row)
    report = {"executableSha256": hashlib.file_digest(args.executable.open("rb"), "sha256").hexdigest(),
              "manifestSha256": hashlib.file_digest(args.manifest.open("rb"), "sha256").hexdigest(),
              "mode": "exact saved capture only", "sectionHashes": section_hashes,
              "unwindFragmentsInspected": fragments, "nativeTypes": types,
              "vmGlobalOperandCandidates": globals_found, "directVmCallInstructions": vm_calls,
              "indirectCallOrJumpInstructions": indirect_calls,
              "unownedEncodingCandidates": sorted(unowned),
              "completeness": {"nativeTypeDispatch": "all numeric types 0 through 27 inventoried",
                  "nativeFunctionScan": "unwind fragments plus encoding candidates, not a complete dataflow proof",
                  "externalModules": "not inventoried by a main-module capture",
                  "retainedHeapConsumers": "not proven by static global-reference scan",
                  "indirectCallTargets": "unresolved except separately decoded type dispatch tables",
                  "unownedCode": "leaf and unlisted code candidates require separate instruction-boundary verification"},
              "activationAllowed": False}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"types": len(types), "fragments": len(fragments), "globalOperands": len(globals_found),
                      "directVmCalls": len(vm_calls), "indirectTransfers": len(indirect_calls),
                      "unownedCandidates": len(unowned), "activationAllowed": False}))


if __name__ == "__main__":
    main()
