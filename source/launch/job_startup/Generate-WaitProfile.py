"""Pin the native wait and wrapper returns from one exact gate image."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import capstone
import pefile

p = argparse.ArgumentParser()
p.add_argument("--gate", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
pe = pefile.PE(str(a.gate))
base = pe.OPTIONAL_HEADER.ImageBase
imports = {entry.address - base: entry.name for dll in pe.DIRECTORY_ENTRY_IMPORT for entry in dll.imports}
dis = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
dis.detail = True
functions = []
for row in pe.DIRECTORY_ENTRY_EXCEPTION:
    start, end = row.struct.BeginAddress, row.struct.EndAddress
    unwind = row.struct.UnwindData
    root = start
    for _ in range(8):
        info = pe.get_data(unwind, 4)
        if not (info[0] >> 3) & 4:
            break
        root, _, unwind = struct.unpack("<III", pe.get_data(unwind + 4 + ((info[2] + 1) & ~1) * 2, 12))
    else:
        raise AssertionError("The gate unwind chain is too deep.")
    functions.append((start, end, root, list(dis.disasm(pe.get_data(start, end - start), start))))
waits = []
for start, end, root, instructions in functions:
    for instruction in instructions:
        if instruction.mnemonic != "call" or len(instruction.operands) != 1:
            continue
        op = instruction.operands[0]
        if op.type == capstone.CS_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            iat = instruction.address + instruction.size + op.mem.disp
            if imports.get(iat) == b"WaitForMultipleObjects":
                waits.append((root, end, instruction.address + instruction.size))
assert len(waits) == 1, "The gate must contain exactly one native wait call."
enter, end, wait_return = waits[0]
wrappers = []
for start, stop, root, instructions in functions:
    for instruction in instructions:
        if instruction.mnemonic == "call" and len(instruction.operands) == 1:
            op = instruction.operands[0]
            if op.type == capstone.CS_OP_IMM and op.imm == enter:
                wrappers.append(instruction.address + instruction.size)
assert len(wrappers) == 1, "The gate must contain exactly one Enter wrapper call."
a.output.write_text(f"#pragma once\nconstexpr DWORD kGateWaitReturnRva={wait_return}u;\n"
                    f"constexpr DWORD kGateWrapperReturnRva={wrappers[0]}u;\n", encoding="ascii")
a.output.with_suffix(".json").write_text(json.dumps({"gateSha256": hashlib.sha256(a.gate.read_bytes()).hexdigest(),
    "enterStartRva": enter, "enterEndRva": end, "waitReturnRva": wait_return,
    "wrapperReturnRva": wrappers[0]}, indent=2), encoding="utf-8")
