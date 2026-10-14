"""Prepare coordinated actor packet widths and the native invalid ID. Runtime admission remains gated."""
import struct
import json
from pathlib import Path

from captured_code import CapturedCode,CodeGuard,Rewrite
from shape import ActorShape

# Full packet/field-codec closure includes native split families, leaf endpoints, and unwind metadata.
# The former sampled range also contained unrelated randomized protection padding.
_CODEC_INVENTORY=json.loads((Path(__file__).parent/'wire_guard_inventory.json').read_text())
CODEC_CODE_GUARDS=tuple(CodeGuard(**row) for row in _CODEC_INVENTORY['code'])
CODEC_UNWIND_GUARDS=tuple(CodeGuard(**row) for row in _CODEC_INVENTORY['unwind'])
OWNER_GUARDS=CODEC_CODE_GUARDS+CODEC_UNWIND_GUARDS+(
    CodeGuard(0x13655C0,0x3AE,'669a91c5d84aba1ac5aa753fac4ee46085448a009f03119c9ea027bbb03fd50c'),
    CodeGuard(0x33A3608,24,'e2aacee5dd08839a2752319eab3ca7659794a3c542cb83cecbd998e353624c07'),
    CodeGuard(0x2FC69F0,336,'d5437d724e45ca59b216430dea35e0ef6703d848651a19346ebdadbb995545b1'),
    CodeGuard(0x33B1480,48,'3b0a6418f8c2e5ac7c6d24d4d8c936b56349284a07cbf77ecad26a80ed169a64'),
    CodeGuard(0x24AE5E0,0x127,'2bd295d4c09c88bab89bb1d878720a72aa843b4e2fa02bff8cd6d562e5b64fe5'),
    CodeGuard(0x24AE707,0x93,'68311ec4af383408fa4f6da9b16483c2a8e6cd7b0c6d43673ae672ab9a4c8220'),
    CodeGuard(0x31CF418,20,'91a223a03aac5fe7086fce2029e5461da14d6aa74581e14ad304653e1c40e63b'),
    CodeGuard(0x31CF42C,20,'d7b61e6a11327662387b0ff03f158778bf50f6ad11889d759252d12384e12310'),
    CodeGuard(0x488500,0x4B80,'255a98df1fe5478cdd4ded553daa28f08652d4909291d9981a6025f5a501cab6'),
    CodeGuard(0x496470,0x1AC8,'f09438b29163812f4103c8cdd9762f34d3dd1d5077a73e5d52e216dc45a83d9f'),
    CodeGuard(0x310E55C,24,'30c30279f23146ebd512521ac4d9d620acd381ee7ee499bdf00969851a70b390'),
    CodeGuard(0x310E37C,20,'fea717c0dbb0347f01b0aa127d3f2320e6ca55b2ef9aa881dcc78208543b71ba'),
)


def prepare_actor_wire(code: CapturedCode,shape: ActorShape) -> tuple[Rewrite,...]:
    """Keep native frames and zero/no-clone intact. Nine bits represent the largest one-based clone source."""
    for guard in OWNER_GUARDS:code.guarded(guard)
    bits=shape.actors.bit_length()
    if bits!=9:
        raise ValueError('The actor wire preparation requires an admitted nine-bit shape.')
    edits=[]
    for name,rva,expected,offset in (
        ('actor_removal_number_bits',0x212698E,'41b806000000',2),
        ('actor_live_number_bits',0x21269CA,'c744243806000000',4),
        ('actor_client_number_bits',0x1365675,'ba06000000',1),
    ):
        original=bytes.fromhex(expected)
        if code.read(rva,len(original))!=original:
            raise ValueError('An actor packet width instruction differs.')
        replacement=original[:offset]+struct.pack('<I',bits)+original[offset+4:]
        edits.append(Rewrite(name,code.guard(rva,len(original)),replacement))
    for name,rva,string_rva,offset,stock_bits in (
        ('lerp.u.actor.index.actorNum',0x33B1480,0x2FCB3A8,88,6),
        ('lerp.u.actor.clonedFromActorNum',0x33B1498,0x2FCB3C8,92,7),
    ):
        descriptor=struct.unpack('<Qiiii',code.read(rva,24))
        if descriptor!=(code.base+string_rva,offset,4,stock_bits,0) or code.read(string_rva,len(name)+1)!=name.encode('ascii')+b'\0':
            raise ValueError('A named actor-index descriptor differs.')
        edits.append(Rewrite(name+'_bits',code.guard(rva+16,4),struct.pack('<I',bits)))
    original=bytes.fromhex('41c7465840000000')
    if code.read(0x24AE77F,len(original))!=original:
        raise ValueError('The native entity actor invalid-value instruction differs.')
    edits.append(Rewrite('entity_actor_invalid_value',code.guard(0x24AE77F,len(original)),original[:4]+struct.pack('<I',shape.actors)))
    return tuple(edits)
