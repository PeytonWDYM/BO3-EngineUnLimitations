"""Prepare independent snapshot and actor-bank clears without changing native client frames."""
from dataclasses import dataclass
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from client_actors import NATIVE_CLIENT_STRIDE,ACTOR_BANK_OFFSET
from client_snapshots import ClientSnapshots
from x64_table import Emitter,rel32

OWNER_GUARDS=(
    CodeGuard(0x8ED490,24328,'6a067e7a03998c4108abe707c5b7e2d83b73681747d537c2f5d5f7c7081205d8'),
    CodeGuard(0x926D90,32684,'4dcf85e4f20a9c0a5fe049f060125b0430bc7bc684b281ed9790431d71c83372'),
    CodeGuard(0x31164A8,36,'86479059d86938cd804d557a37a3c51e80f395e12248c9aaf632f421ab2660a6'),
    CodeGuard(0x31164D0,24,'fadb901313e2849d62901dda1c3bfab62305665fe043c2944cfba9e8f307e1ca'),
)


@dataclass(frozen=True)
class ClientResetFrame:
    rewrite: Rewrite
    unwind: bytes


def prepare_client_snapshot_resets(code: CapturedCode,layout: ClientSnapshots,
                                  helper_base: int) -> tuple[ClientResetFrame,...]:
    """Retain each original memset and clear its snapshots and complete appended actor bank."""
    for guard in OWNER_GUARDS:code.guarded(guard)
    intervals=((layout.base,layout.base+layout.total_bytes),(helper_base,helper_base+512))
    image=(code.base,code.base+code.meta['imageSize'])
    if (helper_base<=0 or helper_base&15 or helper_base+512>0x800000000000
            or any(start<image[1] and image[0]<end for start,end in intervals)
            or intervals[0][0]<intervals[1][1] and intervals[1][0]<intervals[0][1]):
        raise ValueError('Client reset code and complete storage require separate owned address intervals.')
    frames=[]
    for index,(name,rva,expected,prefix) in enumerate((
        ('client_snapshot_startup_reset',0x8F0AB4,'e8f7482d02',bytes.fromhex('458bce')),
        ('client_snapshot_shutdown_reset',0x92EC08,'e9a3672902',bytes.fromhex('448b4c2408')),
    )):
        original=bytes.fromhex(expected)
        if code.read(rva,5)!=original:
            raise ValueError('The native client clear call or tail jump differs.')
        helper=Emitter(helper_base+index*256)
        # Startup still owns r14d. Shutdown has restored it, so use the native argument home slot.
        helper.put(prefix+b'\x48\x83\xec\x38')
        helper.put(bytes.fromhex('48894c24204c894c2428'))
        helper.rip(b'\xe8',code.base+0x2BC53B0)
        helper.put(bytes.fromhex('488b4c24284869c9')+struct.pack('<I',layout.client_bytes))
        helper.put(b'\x48\xb8'+struct.pack('<Q',layout.base))
        helper.put(bytes.fromhex('4801c133d241b8')+struct.pack('<I',layout.client_bytes))
        helper.rip(b'\xe8',code.base+0x2BC53B0)
        helper.put(bytes.fromhex('488b4c24204881c1')+struct.pack('<I',ACTOR_BANK_OFFSET))
        helper.put(bytes.fromhex('33d241b8')+struct.pack('<I',NATIVE_CLIENT_STRIDE))
        helper.rip(b'\xe8',code.base+0x2BC53B0)
        helper.put(bytes.fromhex('488b4424204883c438c3'))
        # Independent 56-byte allocation; the prefix does not change the frame or nonvolatile registers.
        prolog=len(prefix)+4
        unwind=bytes((1,prolog,1,0,prolog,0x62,0,0))
        rewrite=Rewrite(name,code.guard(rva,5),original[:1]+rel32(code.base+rva+5,helper.address),
                        helper.address,bytes(helper.code))
        frames.append(ClientResetFrame(rewrite,unwind))
    return tuple(frames)
