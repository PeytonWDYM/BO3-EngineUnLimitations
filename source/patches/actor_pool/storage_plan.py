"""Prepare storage relocation and fixed native counts; codec admission is unresolved."""

from dataclasses import dataclass
import json
from pathlib import Path
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite
from table_layout import TableLayout
from x64_table import Emitter, count_stub, rel32


@dataclass(frozen=True)
class StorageLayout:
    actors: int
    secondary_actors: int
    sentient_heads: int
    indexed_words: int

    def regions(self, table: TableLayout) -> tuple[tuple[int,int], ...]:
        regions = ((self.actors,200*0x2110),(self.secondary_actors,200*0xB00),
                   (self.sentient_heads,240*2),(self.indexed_words,240*240*2),(int(table.native_pool),240*0x3088),
                   (int(table.external_table),table.table_bytes))
        if any(start <= 0 or start % 16 or start+size > 1 << 64 for start,size in regions):
            raise ValueError('Each native storage region needs sixteen-byte alignment and valid addresses.')
        ordered = sorted(regions)
        if any(start+size > next_start for (start,size),(next_start,_) in zip(ordered,ordered[1:])):
            raise ValueError('Expanded native storage regions overlap.')
        return regions


def prepare_storage(code: CapturedCode, table: TableLayout, storage: StorageLayout,
                    stub_base: int) -> tuple[Rewrite, ...]:
    storage.regions(table)
    folder = Path(__file__).resolve().parent
    consumers = json.loads((folder/'consumer_inventory.json').read_text())
    sites = json.loads((folder/'storage_inventory.json').read_text())['sites']
    edits: list[Rewrite] = []
    cursor = stub_base

    def relative(name: str, item: dict, destination: int) -> None:
        guard = CodeGuard(int(item['rva'],0),item['size'],item['sha256'])
        original = code.guarded(guard)
        edits.append(Rewrite(name,guard,original[:3]+rel32(code.base+guard.rva+7,destination)))

    def immediate(name: str, item: dict, value: int, width: int = 4) -> None:
        guard = CodeGuard(int(item['rva'],0),item['size'],item['sha256'])
        original = code.guarded(guard)
        edits.append(Rewrite(name,guard,original[:-width]+value.to_bytes(width,'little')))

    for item in consumers['directStorageReferences']:
        destination = table.native_pool if int(item['targetRva'],0) == 0xA037CD0 else storage.secondary_actors
        relative('sentient_static_storage' if destination == table.native_pool else 'secondary_actor_storage',item,destination)
    heads = consumers['sentientHandleHeads']
    for key in ('initialization','release','assignment'):
        relative('sentient_handle_heads',heads[key],storage.sentient_heads)
    immediate('sentient_handle_heads_clear_extent',heads['clearSize'],240*2)
    for item in consumers['secondaryActorLoopCounts']:
        immediate('secondary_actor_codec_count',item,200)
    immediate('secondary_actor_clear_extent',consumers['secondaryActorResetSize'],200*0xB00)

    for item in sites:
        role = item['role']
        if role == 'actor_pool_binding':
            relative(role,item,storage.actors)
        elif role == 'signed_count_branch':
            guard = CodeGuard(int(item['rva'],0),item['size'],item['sha256'])
            code.guarded(guard)
            body = count_stub(cursor,item['value'],code.base+int(item['targetRva'],0),
                              code.base+guard.rva+guard.size,item['register'],item['condition'])
            edits.append(Rewrite(role,guard,b'\xe9'+rel32(code.base+guard.rva+5,cursor)+b'\x90',cursor,body))
            cursor += 0x1000
        elif role == 'sentient_eligibility_count':
            guard = CodeGuard(int(item['rva'],0),item['size'],item['sha256'])
            original = code.guarded(guard)
            # Start before MOV r10d,ecx. The back-edge targets the following flag check.
            e = Emitter(cursor)
            e.put(original[:3]+b'\x45\x8d\x88'+struct.pack('<I',240))
            e.rip(b'\xe9',code.base+guard.rva+guard.size)
            edits.append(Rewrite(role,guard,b'\xe9'+rel32(code.base+guard.rva+5,cursor)+b'\x90'*(guard.size-5),cursor,bytes(e.code)))
            cursor += 0x1000
        else:
            immediate(role,item,item['value'],1 if role == 'actor_four_record_groups' else 4)
    return tuple(edits)
