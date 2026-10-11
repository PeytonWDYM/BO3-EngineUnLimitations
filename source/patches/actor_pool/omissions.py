"""Prepare proven DObj and iterator omissions. Keep unresolved contracts gated."""

import json
from pathlib import Path
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite
from shape import ActorShape
from x64_table import Emitter, count_stub, rel32


def omission_inventory() -> list[dict]:
    return json.loads((Path(__file__).parent/'actor_omissions.json').read_text())['sites']


def prepare_omissions(code: CapturedCode, shape: ActorShape, dobj: int, stub_base: int) -> tuple[Rewrite, ...]:
    edits = []
    cursor = stub_base
    for site in omission_inventory():
        guard = CodeGuard(int(site['rva'],0),site['size'],site['sha256'])
        original = code.guarded(guard)
        role = site['role']
        if site['status'] == 'blocked':
            continue
        stub = b''
        if role.startswith('actor_dobj_') and role != 'actor_dobj_cleanup_count':
            destination = dobj+shape.dobj_bytes if role.endswith('_end') else dobj
            replacement = original[:3]+rel32(code.base+guard.rva+7,destination)
        elif role == 'actor_dobj_cleanup_count':
            replacement = original[:1]+struct.pack('<I',shape.actors)
        elif role == 'actor_iterator':
            stub = count_stub(cursor,shape.actors,code.base+int(site['branchTargetRva'],0),
                              code.base+guard.rva+guard.size,'r8',site['condition'])
            replacement = b'\xe9'+rel32(code.base+guard.rva+5,cursor)+b'\x90'
        elif role == 'live_actor_admission_groups':
            replacement = original[:-1]+bytes([shape.four_actor_groups])
        elif role == 'adjacent_static_array_boundary':
            # The DObj setup also uses r14 as the end of an unrelated six-entry array.
            emitter = Emitter(cursor)
            emitter.put(b'\x49\xbe'+struct.pack('<Q',code.base+0xA588868))
            destination = code.base+guard.rva+7+struct.unpack('<i',original[3:])[0]
            emitter.rip(original[:3],destination)
            emitter.rip(b'\xe9',code.base+guard.rva+guard.size)
            stub = bytes(emitter.code)
            replacement = b'\xe9'+rel32(code.base+guard.rva+5,cursor)+b'\x90'*(guard.size-5)
        else:
            raise ValueError(f'No admitted omission emitter exists for {role}.')
        edits.append(Rewrite(role,guard,replacement,cursor if stub else None,stub))
        if stub:
            cursor += 0x1000
    return tuple(edits)
