"""Prepare separate native client snapshots. Reset, ring ownership, and activation remain gated."""
from dataclasses import dataclass
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from shape import ActorShape
from x64_table import Emitter,rel32

OWNER_GUARDS=(
    CodeGuard(0x1321250,0x780,'a39b1db9f4007c669c3ae34d218a95b37d120984a4b964e3efb84c12a1247b06'),
    CodeGuard(0xFDCA50,0x1B27,'e6bd6a4a1733bfe0544224aa8f22acbbb4abfbe15c7e468218fd0d14d894ab00'),
    CodeGuard(0xFC26D0,0x319C,'c28c9ab6b295c9dbca798153cc161716df58f81999ba796008435c4c06a62702'),
    CodeGuard(0x3120D6C,16,'69e1ef0711bd452a74cae9b11beb6ef64708ab53c554d753d27ce7da81f358aa'),
    CodeGuard(0x3120D7C,24,'1fbce4f07f1dcb38c76c4805743b6c9b0c5aba628cd5aa532aec3bd09508d1c9'),
)


@dataclass(frozen=True)
class ClientSnapshots:
    base: int
    shape: ActorShape

    def __post_init__(self) -> None:
        if self.base<=0 or self.base&4095 or self.base+self.total_bytes>0x800000000000:
            raise ValueError('Client snapshot storage requires a complete aligned user address interval.')

    @property
    def actor_offset(self) -> int:
        # Append the array after the complete stock snapshot. Keep every native member offset.
        return 0x8D420

    @property
    def snapshot_bytes(self) -> int:
        return self.actor_offset+self.shape.actors*80

    @property
    def client_bytes(self) -> int:
        return 2*self.snapshot_bytes

    @property
    def total_bytes(self) -> int:
        return 2*self.client_bytes


def prepare_client_snapshots(code: CapturedCode,layout: ClientSnapshots,stub_base: int) -> tuple[Rewrite,...]:
    """Keep the native retry entry and caller frame. Bind only owned preparation addresses."""
    for guard in OWNER_GUARDS:code.guarded(guard)
    intervals=((layout.base,layout.base+layout.total_bytes),(stub_base,stub_base+512))
    image=(code.base,code.base+code.meta['imageSize'])
    if (stub_base<=0 or stub_base&15 or stub_base+512>0x800000000000
            or any(start<image[1] and image[0]<end for start,end in intervals)
            or intervals[0][0]<intervals[1][1] and intervals[1][0]<intervals[0][1]):
        raise ValueError('The snapshot preparation code and complete storage must be separate from the native image.')
    edits=[]
    for name,rva,expected,offset,value in (
        ('client_snapshot_actor_clamp',0x13218D6,'b940000000',1,layout.shape.actors),
        ('client_snapshot_export_actor_offset',0x13218F1,'4c8d8780af0800',3,layout.actor_offset),
        ('client_snapshot_consumer_actor_offset',0xFDCADF,'4881c680af0800',3,layout.actor_offset),
    ):
        original=bytes.fromhex(expected)
        if code.read(rva,len(original))!=original:
            raise ValueError('A native client snapshot operand differs.')
        replacement=original[:offset]+struct.pack('<I',value)+original[offset+4:]
        edits.append(Rewrite(name,code.guard(rva,len(original)),replacement))
    # The native retry jumps to 0xFC57E0. Replace only the preceding LEA and NOP.
    first=Emitter(stub_base)
    first.mov('rsi','r15')
    first.put(b'\x48\x69\xf6'+struct.pack('<I',layout.client_bytes))
    first.put(b'\x48\xb8'+struct.pack('<Q',layout.base))
    first.add('rsi','rax')
    first.rip(b'\xe9',code.base+0xFC57E0)
    selected=Emitter(stub_base+256)
    selected.put(b'\x48\x69\xc0'+struct.pack('<I',layout.snapshot_bytes))
    selected.mov('rdi','rsi')
    selected.add('rdi','rax')
    selected.rip(b'\xe9',code.base+0xFC5800)
    for name,rva,original,emitter in (
        ('client_snapshot_first_slot',0xFC57D5,'498d76400f1f8000000000',first),
        ('client_snapshot_selected_slot',0xFC57F2,'4869c020d40800488d78404903fe',selected),
    ):
        expected=bytes.fromhex(original)
        if code.read(rva,len(expected))!=expected:
            raise ValueError('The native snapshot slot selection differs.')
        replacement=b'\xe9'+rel32(code.base+rva+5,emitter.address)+b'\x90'*(len(expected)-5)
        edits.append(Rewrite(name,code.guard(rva,len(expected)),replacement,emitter.address,bytes(emitter.code)))
    return tuple(edits)
