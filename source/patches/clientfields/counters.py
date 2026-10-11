"""Guarded relocation of the native clientfield counter table."""
import hashlib
import json
from pathlib import Path

from captured_code import CapturedCode,CodeGuard,Rewrite

CAPACITY=8192
STORAGE_BYTES=CAPACITY*24
INVENTORY_SHA256='4c6fb064bab167a8d3763173fb2cb1a735fb7d682f32442ed0b0aa1de754f79c'


def load_inventory(path: Path) -> dict:
    raw=path.read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest()!=INVENTORY_SHA256:
        raise ValueError('The counter inventory differs from the pinned exact capture.')
    return json.loads(raw)


def prepare(code: CapturedCode,pool: int) -> tuple[Rewrite,...]:
    inventory=load_inventory(Path(__file__).with_name('counter_inventory.json'))
    if (pool<0x10000 or pool%16 or pool+STORAGE_BYTES>=2**64
            or not (pool+STORAGE_BYTES<=code.base or pool>=code.base+inventory['imageSize'])):
        raise ValueError('The complete counter backing must be aligned outside the native image.')
    for row in inventory['guards']:code.guarded(CodeGuard(**row))
    offsets={'pool':0,'end':STORAGE_BYTES,'lastField':STORAGE_BYTES-24,'lastState':STORAGE_BYTES-16,'lastCount':STORAGE_BYTES-8}
    result=[]
    for row in inventory['instructions']:
        raw=bytes.fromhex(row['bytes'])
        guard=CodeGuard(row['rva'],len(raw),hashlib.sha256(raw).hexdigest());code.guarded(guard)
        kind=row['kind']
        if kind in offsets:
            value=pool+offsets[kind]-(code.base+row['rva']+len(raw))
            if not -2**31<=value<2**31:raise ValueError('The complete counter backing is outside native reach.')
        else:value={'capacity':CAPACITY,'bytes':STORAGE_BYTES}[kind]
        replacement=bytearray(raw);offset=row['operandOffset']
        replacement[offset:offset+4]=value.to_bytes(4,'little',signed=kind in offsets)
        result.append(Rewrite(f'counter-{kind}-{row["rva"]:x}',guard,bytes(replacement)))
    return tuple(result)
