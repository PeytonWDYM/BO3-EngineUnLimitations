"""Prepare the complete demo writer frame and prior records. Reader/reset and game admission remain gated."""
from dataclasses import dataclass
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from native_unwind import read_frame
from native_handlers import prepare_native_handler
from shape import ActorShape
from x64_table import rel32

WRITER=CodeGuard(0x25CE9D0,0x2B9,'89c8076c9976cedb05c99e10ecbd94c0e3c505c3754ac61e038e66e43a69806e')
METADATA=CodeGuard(0x31DBB00,40,'48ef5b465c6b75a6337c03b160b50b12bed06a721b3db44de357ca0fdc2825ae')


@dataclass(frozen=True)
class DemoWriter:
    base: int
    shape: ActorShape

    def __post_init__(self) -> None:
        if self.base<=0 or self.base&4095 or self.base+self.bytes>0x800000000000:
            raise ValueError('Demo prior records require a complete aligned user interval.')

    @property
    def bytes(self) -> int:return self.shape.actors*80

    @property
    def growth(self) -> int:return (self.shape.actors-64)*4

    @property
    def frame(self) -> int:return 0x170+self.growth

    @property
    def cookie(self) -> int:return 0x160+self.growth


def prepare_demo_writer(code: CapturedCode,layout: DemoWriter,helper: int) -> tuple[Rewrite,...]:
    """Keep index units and all original prolog lengths. Move every high-frame member with the ID list."""
    code.guarded(WRITER);metadata=bytearray(code.guarded(METADATA))
    intervals=((layout.base,layout.base+layout.bytes),(helper,helper+256))
    image=(code.base,code.base+code.meta['imageSize'])
    if (helper<=0 or helper&15 or helper+256>0x800000000000
            or any(first<image[1] and image[0]<last for first,last in intervals)
            or intervals[0][0]<intervals[1][1] and intervals[1][0]<intervals[0][1]):
        raise ValueError('Demo code and complete prior-record storage must be separate from the native image.')
    edits=[]
    for name,rva,expected,offset,value in (
        ('demo_writer_frame_allocation',0x25CE9E8,'4881ec70010000',3,layout.frame),
        ('demo_writer_frame_cookie_save',0x25CE9F9,'4889842460010000',4,layout.cookie),
        ('demo_writer_frame_cookie_read',0x25CEC58,'488b8c2460010000',4,layout.cookie),
        ('demo_writer_frame_epilogue',0x25CEC68,'4c8d9c2470010000',4,layout.frame),
    ):
        original=bytes.fromhex(expected)
        if code.read(rva,len(original))!=original:raise ValueError('A demo writer frame instruction differs.')
        edits.append(Rewrite(name,code.guard(rva,len(original)),original[:offset]+struct.pack('<I',value)))
    original=bytes.fromhex('83f8407ce448633db99f0f17')
    if code.read(0x25CEA37,len(original))!=original:raise ValueError('The complete native demo actor scan block differs.')
    # A direct jump here looks like an epilogue to Windows. The leaf call keeps the native frame active.
    stub=(b'\x3d'+struct.pack('<I',layout.shape.actors)+b'\x7c\x07\x48\x63\x3d'
          +rel32(helper+14,code.base+0x196C89FC)+b'\xc3')
    block=(b'\xe8'+rel32(code.base+0x25CEA3C,helper)
           +b'\x0f\x8c'+rel32(code.base+0x25CEA42,code.base+0x25CEA20)+b'\x90')
    edits.append(Rewrite('demo_writer_actor_scan',code.guard(0x25CEA37,len(original)),block,helper,stub))
    original=bytes.fromhex('4c8d3d8a8b0f17')
    if code.read(0x25CEA6B,7)!=original:raise ValueError('The demo prior-record base differs.')
    edits.append(Rewrite('demo_writer_prior_records',code.guard(0x25CEA6B,7),original[:3]+rel32(code.base+0x25CEA72,layout.base)))
    native=read_frame(code,(WRITER.rva,WRITER.rva+WRITER.size,METADATA.rva))
    prepare_native_handler(code,native)
    slot=saves=allocations=0
    for operation in native.operations:
        position=4+slot*2
        if operation.opcode==1:
            if operation.info or operation.allocation!=0x170:raise ValueError('The demo writer native allocation differs.')
            struct.pack_into('<H',metadata,position+2,layout.frame//8);allocations+=1
        elif operation.opcode==4:
            struct.pack_into('<H',metadata,position+2,operation.value+layout.growth//8);saves+=1
        elif operation.opcode!=0:raise ValueError('The demo writer has an unclassified unwind operation.')
        slot+=2 if operation.opcode in (1,4) else 1
    if (slot,saves,allocations)!=(13,3,1) or struct.unpack_from('<II',metadata,32)!=(0x2BC3A04,0x160):
        raise ValueError('The demo writer complete GS frame differs.')
    struct.pack_into('<I',metadata,36,layout.cookie)
    edits.append(Rewrite('demo_writer_frame_metadata',METADATA,bytes(metadata)))
    return tuple(edits)
