"""Prepare fixed-width client actor operand relocation. Native root discovery remains gated."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from shape import ActorShape

NATIVE_CLIENT_STRIDE=0x342720
NATIVE_ACTOR_OFFSET=0x2F84E0
INVENTORY_SHA256='304d8ac6cb83fb7dee69efeb6a6609dc9c0d0170298012d623337f126ec3fcdd'


@dataclass(frozen=True)
class ClientActors:
    native_base: int
    base: int
    shape: ActorShape

    def __post_init__(self) -> None:
        native_end=self.native_base+self.total_bytes
        external_end=self.base+self.total_bytes
        if (self.native_base<=0 or self.native_base&15 or native_end>0x800000000000
                or self.base<=0 or self.base&4095 or external_end>0x800000000000
                or self.native_base<external_end and self.base<native_end
                or not -(1<<31)<=self.actor_offset<=((1<<31)-1)-0xB00
                or self.shape.secondary_actor_bytes>self.client_stride):
            raise ValueError('Client actor relocation requires complete separate banks and a signed native displacement.')

    @property
    def client_stride(self) -> int:return NATIVE_CLIENT_STRIDE

    @property
    def total_bytes(self) -> int:return 2*self.client_stride

    @property
    def actor_offset(self) -> int:return self.base-self.native_base


def prepare_client_actors(code: CapturedCode,layout: ClientActors) -> tuple[Rewrite,...]:
    """Use the same bank stride as native clients, so every member needs only its original operand changed."""
    inventory=json.loads((Path(__file__).with_name('client_actor_inventory.json')).read_text())
    digest=hashlib.sha256(json.dumps(inventory,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=INVENTORY_SHA256 or inventory['executableSha256']!=code.executable_sha256:
        raise ValueError('The exact client actor operand inventory differs.')
    for guard in inventory['guards']:code.guarded(CodeGuard(**guard))
    if layout.base<code.base+code.meta['imageSize'] and code.base<layout.base+layout.total_bytes:
        raise ValueError('The complete client actor allocation aliases the native image.')
    edits=[]
    for item in inventory['members']:
        original=bytes.fromhex(item['original']);rva=item['rva'];offset=item['operandOffset']
        if code.read(rva,len(original))!=original:
            raise ValueError('A native client actor member instruction differs.')
        replacement=original[:offset]+struct.pack('<i',layout.actor_offset+item['memberOffset'])+original[offset+4:]
        edits.append(Rewrite(f'client_actor_member_{rva:x}',code.guard(rva,len(original)),replacement))
    for item in inventory['resourceCounts']:
        rva=item['rva'];original=bytes.fromhex(item['original'])
        if code.read(rva,5)!=original:
            raise ValueError('The native client actor resource count differs.')
        edits.append(Rewrite(f'client_actor_resource_count_{rva:x}',code.guard(rva,5),original[:1]+struct.pack('<I',layout.shape.actors)))
    return tuple(edits)
