"""Prepare coordinated actor packet widths. Client storage and peer admission remain gated."""
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from shape import ActorShape

OWNER_GUARDS=(
    CodeGuard(0x20F0000,0x40000,'4f818c4de9d1c9e55918609c5404e16141a63098699d43032511f7a62ebdf066'),
    CodeGuard(0x13655C0,0x3AE,'669a91c5d84aba1ac5aa753fac4ee46085448a009f03119c9ea027bbb03fd50c'),
    CodeGuard(0x33A3608,24,'e2aacee5dd08839a2752319eab3ca7659794a3c542cb83cecbd998e353624c07'),
    CodeGuard(0x2FC69F0,336,'d5437d724e45ca59b216430dea35e0ef6703d848651a19346ebdadbb995545b1'),
    CodeGuard(0x33B1480,48,'3b0a6418f8c2e5ac7c6d24d4d8c936b56349284a07cbf77ecad26a80ed169a64'),
)


def prepare_actor_wire(code: CapturedCode,shape: ActorShape) -> tuple[Rewrite,...]:
    """Keep native frames/call sites intact. Nine bits also represent the selected clone sentinel."""
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
    return tuple(edits)
