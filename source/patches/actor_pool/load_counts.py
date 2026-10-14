"""Prepare immutable-load count bindings. Root/thread/file admission remains required before game use."""
from dataclasses import dataclass
from enum import Enum
import struct
from captured_code import CapturedCode,CodeGuard,Rewrite
from x64_table import rel32

class LoadShape(Enum):
    Legacy64=64
    Expanded500=500


@dataclass(frozen=True)
class LoadCounts:
    base: int

    def __post_init__(self) -> None:
        if self.base<0x10000 or self.base&15 or self.base+24>0x800000000000:
            raise ValueError('Load counts need a complete aligned user address interval.')

    def values(self,shape: LoadShape) -> bytes:
        if not isinstance(shape,LoadShape):raise ValueError('The actor load shape is unknown.')
        actors=shape.value
        return struct.pack('<QQI4x',actors*0x2110,(actors+40)*0x3088,actors)


OWNER_GUARDS=(
    CodeGuard(0xB60E0,614,'f8ccf08f96fb00f58efb462ad3976cbbe14959cd9d79318197ec8e2614a02efe'),
    CodeGuard(0x3101F88,28,'acc80666da6081d81adf827109081d94d5092b0e5a278ca02471ab2488c7f0a9'),
    CodeGuard(0xC44C0,349,'4ca9f29a6763b99c6ea1454dc51c5f692af5f3427c6f61ad5d0e04ad0c595399'),
    CodeGuard(0x3101FC0,28,'d86c5ab4a0090565a699f54fe76dbbeb7da876613745dc787daed53c0f7e8de5'),
    CodeGuard(0xFA0E0,265,'b75cc298d1d1f302c72ff5bbb9cf98e10037a0e2d8638dfb30837ce49ee1266c'),
    CodeGuard(0x3102880,16,'97d91ea60ef54bbb4d3bd65e0b3920ecd70f62c61aced1ede9220557f921069a'),
    CodeGuard(0x12E01A,318,'403c068ba2d52f9e9333a70035ec73c842e41612ed53caad36fa78b3bb3cdaab'),
    CodeGuard(0x3102CE8,16,'7a868deb024caebc0829efa380a80b9583a663e6b4af87bfb7c88df9b971eec4'),
)


def prepare_load_counts(code: CapturedCode,slots: LoadCounts) -> tuple[Rewrite,...]:
    """Use native CMP/MOV operations with RIP loads. Preserve frames and complete instruction windows."""
    for guard in OWNER_GUARDS:code.guarded(guard)
    if slots.base<code.base+code.meta['imageSize'] and code.base<slots.base+24:
        raise ValueError('Load-count storage overlaps the native image.')
    edits=[]
    for name,rva,expected,offset in (
        ('actor_load_extent',0xB631C,'4981ff00440800',0),
        ('sentient_load_extent',0xC45F1,'4981ff40b71300',8),
        ('secondary_load_count',0xFA1A7,'be400000000f1f4000',16),
        ('tagged_secondary_load_count',0x12E10A,'be4000000090',16),
    ):
        original=bytes.fromhex(expected)
        if code.read(rva,len(original))!=original:raise ValueError('A native load-count window differs.')
        opcode=b'\x4c\x3b\x3d' if offset<16 else b'\x8b\x35'
        replacement=opcode+rel32(code.base+rva+len(opcode)+4,slots.base+offset)
        replacement+=b'\x90'*(len(original)-len(replacement))
        edits.append(Rewrite(name,code.guard(rva,len(original)),replacement))
    return tuple(edits)
