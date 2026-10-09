"""Prepare exact guarded table rewrites for owned replay. Activation is incomplete."""

from dataclasses import dataclass, replace
import json
from pathlib import Path
import struct

from table_layout import TableLayout, ExternalTableAddress
from captured_code import CapturedCode, CodeGuard, Rewrite
from storage_plan import StorageLayout, prepare_storage
from x64_table import MemberInstruction, REGISTERS, accessor_stub, member_stub, clear_stub, load_entry_stub, count_stub, rel32


def normalize_register(register: str) -> str:
    aliases = {'eax':'rax','ax':'rax','al':'rax','ecx':'rcx','cx':'rcx','cl':'rcx',
               'edx':'rdx','dx':'rdx','dl':'rdx','ebx':'rbx','bx':'rbx','bl':'rbx',
               'esi':'rsi','si':'rsi','sil':'rsi','edi':'rdi','di':'rdi','dil':'rdi',
               'ebp':'rbp','bp':'rbp','esp':'rsp','sp':'rsp'}
    if register in aliases:
        return aliases[register]
    if register.startswith('r') and register[-1] in 'dwb' and register[1:-1].isdigit():
        return register[:-1]
    return register


def decode_member(code: bytes, address: int, owner_override: str | None = None) -> MemberInstruction:
    import capstone
    decoder = capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    decoder.detail = True
    instruction = next(decoder.disasm(code,address))
    memory = next(op for op in instruction.operands if op.type == capstone.x86.X86_OP_MEM)
    base = instruction.reg_name(memory.mem.base)
    index = instruction.reg_name(memory.mem.index) if memory.mem.index else None
    used = frozenset(normalize_register(instruction.reg_name(r)) for group in instruction.regs_access() for r in group)
    if used & {'ah','bh','ch','dh'}:
        raise ValueError('Legacy high-byte registers have no admitted REX rewrite contract.')
    if instruction.size != len(code) or base == 'rip' or memory.mem.segment:
        raise ValueError('The guarded member instruction has an unsupported address contract.')
    owner = owner_override or base
    mode = code[instruction.modrm_offset] >> 6
    # Operand-size prefixes do not shorten a ModRM disp32 address.
    displacement_size = 4 if mode == 2 else 1 if mode == 1 else instruction.disp_size
    return MemberInstruction(code,owner,base,index,memory.mem.scale,memory.mem.disp,
                             instruction.modrm_offset,instruction.disp_offset,displacement_size,
                             instruction.rex,used | {owner})


@dataclass(frozen=True)
class PreparedTablePlan:
    layout: TableLayout
    rewrites: tuple[Rewrite, ...]
    member_bindings: tuple[tuple[int, MemberInstruction], ...]
    actor_array: int
    storage: StorageLayout
    word_table: TableLayout
    coverage_complete: bool = False

    def require_activation(self) -> None:
        raise RuntimeError('Activation is blocked: complete consumer, lifecycle, unwind, serialization, and startup admission remain unresolved.')


def prepare(code: CapturedCode, layout: TableLayout, stub_base: int, storage: StorageLayout) -> PreparedTablePlan:
    storage.regions(layout)
    actor_array = storage.actors
    if actor_array % 16:
        raise ValueError('Native actor construction requires sixteen-byte record alignment.')
    folder = Path(__file__).resolve().parent
    inventory = json.loads((folder/'consumer_inventory.json').read_text())
    pool_pointer = code.base+0xA1B0790
    word_table = TableLayout(layout.native_pool,ExternalTableAddress(storage.indexed_words),240,2,0x112C)
    rewrites: list[Rewrite] = []
    bindings: list[tuple[int,MemberInstruction]] = []
    cursor = stub_base
    for rva,size,digest in [
        (0x2505B20,59,'0853f607f70957f4d03ea0987c2d0072a02bff3d68d66482944e1fa1555770df'),
        (0x2505D4A,7,'598c8f9772fb2930b2455658dfb9b2bdca05fb3d1aa79e82032082528d1f0943'),
        (0xC45B0,27,'c69e57565fd01824b6e5a1979e9d354c1a364a337765f9c5c494a2b8abe71308'),
        (0xC45D0,6,'02cd0daf207d7918f7f81931c09634b15ae9be904f7ea9d8abdcc3e2235f62ef'),
        (0xC45F1,7,'be65eeb5e45ee1b31bdd670d2baab2b2d9ee8965983567c564001f279baa99f2'),
        (0x25062F3,6,'3662001f68a056ebdd0cbd0b86914bcfdac655e98290745801bd8f9ee06192f9'),
        (0x250635D,6,'71ed78e829af8ea0b8e6e09c6d7e0925645ebb315ae1cf6a48f1c7ec58ea6fe8'),
        (0x25063B2,6,'bb4bb98b7f2d980fc3f69511b12058be28bf870b95f3262dbf3eb13f821973e2')]:
        code.guarded(CodeGuard(rva,size,digest))

    def hook(name: str, start: int, size: int, body: bytes, owner: str | None = None) -> None:
        nonlocal cursor
        if size < 5 or len(body) > 0x1000:
            raise ValueError('The guarded hook extent or stub size is invalid.')
        replacement = b'\xe9'+rel32(code.base+start+5,cursor)+b'\x90'*(size-5)
        rewrites.append(Rewrite(name,code.guard(start,size),replacement,cursor,body,owner))
        cursor += 0x1000

    accessor_guard = CodeGuard(0x2505BB0,50,'84017a8b6ab33728725a6ee964c068cc9b5f38b7046f01ca3b126f18ada70a18')
    original_accessor = code.guarded(accessor_guard)
    hook('external_table_accessor',0x2505BB0,7,accessor_stub(original_accessor[:34],cursor,pool_pointer,layout),'rcx')

    overrides = {0x164B407:'r10',0x164B40F:'r10',0x24B0F9A:'rdx',0x24B1040:'rdx',0x24B1053:'rdx',0x24B105C:'rdx'}
    for group in inventory['classifiedTableScan']['roots']:
        if group['classification'] != 'sentient_table':
            continue
        for site in group['sites']:
            guard = CodeGuard(int(site['rva'],0),site['size'],site['sha256'])
            raw = code.guarded(guard)
            member = decode_member(raw,code.base+guard.rva,overrides.get(guard.rva))
            body = member_stub(member,cursor,pool_pointer,layout,code.base+guard.rva+guard.size)
            hook('external_table_member',guard.rva,guard.size,body,member.owner_register)
            bindings.append((guard.rva,member))
    if len(bindings) != 55:
        raise ValueError('The admitted direct-consumer inventory must contain exactly fifty-five sites.')

    # Redirect folded producers before native code overwrites their owner register.
    omitted = json.loads((folder/'omitted_consumers.json').read_text())
    for site in omitted['sites']:
        guard = CodeGuard(int(site['rva'],0),site['size'],site['sha256'])
        raw = code.guarded(guard)
        extent = site['instructionSize']
        member = replace(decode_member(raw[:extent],code.base+guard.rva,site['ownerRegister']),
                         index_bias=site['indexBias'],trailing_original=raw[extent:])
        body = member_stub(member,cursor,pool_pointer,layout,code.base+guard.rva+guard.size)
        hook('external_table_member',guard.rva,guard.size,body,member.owner_register)
        bindings.append((guard.rva,member))

    words = json.loads((folder/'indexed_words.json').read_text())
    for site in words['sites']:
        guard = CodeGuard(int(site['rva'],0),site['size'],site['sha256'])
        raw = code.guarded(guard)
        member = replace(decode_member(raw,code.base+guard.rva,site['ownerRegister']),native_offset=0x112C)
        hook('external_table_member',guard.rva,guard.size,
             member_stub(member,cursor,pool_pointer,word_table,code.base+guard.rva+guard.size),member.owner_register)
        bindings.append((guard.rva,member))
    for site in words['resets']:
        guard = CodeGuard(int(site['rva'],0),site['size'],site['sha256'])
        original = code.guarded(guard)
        hook('indexed_word_owner_clear',guard.rva,guard.size,
             clear_stub(cursor,pool_pointer,word_table,code.base+guard.rva+guard.size,site['ownerRegister'],original),site['ownerRegister'])

    # Reset the full matrix before map initialization, preserving the native XOR/NOP prefix.
    original = code.read(0x2505B24,12)
    word_clear = clear_stub(cursor,pool_pointer,word_table,cursor,None,b'')[:-5]
    # Each clear restores its registers and flags before the next clear starts.
    hook('map_table_clear',0x2505B24,12,word_clear+clear_stub(cursor+len(word_clear),pool_pointer,layout,code.base+0x2505B30,None,original))
    # Native memset has completed, but the new sentient has not entered its entity record yet.
    original = code.read(0x2505D4A,7)
    word_clear = clear_stub(cursor,pool_pointer,word_table,cursor,'rdi',b'')[:-5]
    hook('allocation_owner_row_clear',0x2505D4A,7,word_clear+clear_stub(cursor+len(word_clear),pool_pointer,layout,code.base+0x2505D51,'rdi',original),'rdi')
    native_clear = code.guarded(CodeGuard(0x2505BF0,38,'a7d332904442e730a4a9bf784db48cb2df309559423a9c101461d489c44ba929'))
    hook('load_entry_clear',0xC45B0,27,load_entry_stub(cursor,pool_pointer,layout,code.base+0xC45CB,native_clear[:-1]),'rbp')
    hook('load_row_column_count',0xC45D0,6,count_stub(cursor,layout.capacity,code.base+0xC45B0,code.base+0xC45D6))
    for start,target,condition in [(0x25062F3,0x25062B0,0x8C),(0x250635D,0x25063DB,0x8D),(0x25063B2,0x2506370,0x8C)]:
        hook('sentient_free_owner_count',start,6,count_stub(cursor,layout.capacity,code.base+target,code.base+start+6,'r8',condition))
    for name,start,size,prefix_size in [('sentient_map_record_count',0x2505B45,6,2),
                                        ('sentient_load_record_count',0xC45F1,7,3)]:
        original = code.read(start,size)
        rewrites.append(Rewrite(name,code.guard(start,size),original[:prefix_size]+struct.pack('<I',layout.capacity*0x3088)))

    # These real CRT registrations use imm32 counts, unlike the allocator's imm8 bound.
    code.guarded(CodeGuard(0x2DD10C0,62,'ecc43538c69fdb0c7f49d3fd21e80d2e50099b4eebf795db7e838b606f105ab2'))
    code.guarded(CodeGuard(0x2EFA3D0,30,'5656dd8a2d8e4cb5818dcc4ea2dd85216a2361579e58784b3258dca62e8cc8f5'))
    for start in (0x2DD10D2,0x2EFA3D7):
        original = code.read(start,7)
        rewrites.append(Rewrite('actor_lifetime_array',code.guard(start,7),original[:3]+rel32(code.base+start+7,actor_array)))
    for start in (0x2DD10DE,0x2EFA3E3):
        original = code.read(start,6)
        rewrites.append(Rewrite('actor_lifetime_count_200',code.guard(start,6),original[:2]+struct.pack('<I',200)))
    rewrites.extend(prepare_storage(code,layout,storage,cursor))
    return PreparedTablePlan(layout,tuple(rewrites),tuple(bindings),actor_array,storage,word_table)
