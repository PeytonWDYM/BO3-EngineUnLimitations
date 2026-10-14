"""Guarded callback backing relocation; packed clientfield layouts stay unchanged."""
import hashlib
import json
from pathlib import Path

from captured_code import CapturedCode,CodeGuard,Rewrite

CAPACITY = 8192
COUNT_OFFSET = CAPACITY*32*2
STORAGE_BYTES = COUNT_OFFSET+8
INVENTORY_SHA256 = '5238f4c67ea98b686be93a3026876786e7f512b8ad74b5c19896686aa32712a3'


def load_inventory(path: Path) -> dict:
    raw=path.read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(raw).hexdigest()!=INVENTORY_SHA256:
        raise ValueError('The callback inventory differs from the pinned exact capture.')
    return json.loads(raw)


def prepare(code: CapturedCode,pool: int) -> tuple[Rewrite,...]:
    inventory=load_inventory(Path(__file__).with_name('pending_inventory.json'))
    if (pool<0x10000 or pool%4096 or pool+STORAGE_BYTES>2**64
            or not (pool+STORAGE_BYTES<=code.base or pool>=code.base+inventory['imageSize'])):
        raise ValueError('The complete owned callback backing must be outside the native image.')
    for row in inventory['guards']:code.guarded(CodeGuard(**row))
    result=[]
    for row in inventory['instructions']:
        raw=bytes.fromhex(row['bytes'])
        guard=CodeGuard(row['rva'],len(raw),hashlib.sha256(raw).hexdigest())
        code.guarded(guard)
        kind=row['kind']
        value={'capacity':CAPACITY,'counts':COUNT_OFFSET,'bytes':STORAGE_BYTES,'shift':13}.get(kind)
        if kind=='pool':
            value=pool-(code.base+row['rva']+len(raw))
            if not -2**31<=value<2**31:raise ValueError('The callback backing is outside native RIP-relative reach.')
        replacement=bytearray(raw)
        offset,size=row['operandOffset'],row['operandSize']
        replacement[offset:offset+size]=value.to_bytes(size,'little',signed=kind=='pool')
        result.append(Rewrite(f'pending-{kind}-{row["rva"]:x}',guard,bytes(replacement)))
    return tuple(result)
