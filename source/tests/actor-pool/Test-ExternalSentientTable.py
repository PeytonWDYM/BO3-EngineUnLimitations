"""Replay guarded native table edits and actor lifetimes in owned memory."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress, NATIVE_SENTIENT_BYTES
from table_plan import CapturedCode, CodeGuard, prepare, normalize_register
from storage_plan import StorageLayout
from x64_table import REGISTERS


def run(module: Path, dependencies: Path, output: Path):
    sys.path.insert(0,str(dependencies))
    import capstone
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x86

    output = output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    source = CapturedCode(module)
    layout = TableLayout(NativeSentientAddress(source.base+0x21000000),ExternalTableAddress(source.base+0x22000000))
    plan = prepare(source,layout,source.base+0x20000000,StorageLayout(source.base+0x23000000,source.base+0x24000000,source.base+0x25000000,source.base+0x26000000))
    pointer = source.base+0xA1B0790
    gprs = {r:getattr(x86,'UC_X86_REG_'+r.upper()) for r in REGISTERS}
    xmms = [getattr(x86,'UC_X86_REG_XMM'+str(n)) for n in range(16)]
    decoder = capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    decoder.detail = True
    native_bytes = bytes([0xA5])*(240*NATIVE_SENTIENT_BYTES+0x8000)
    table_bytes = bytes([0xA5])*layout.table_bytes
    word_bytes = bytes([0xA5])*plan.word_table.table_bytes
    results = []

    def machine(fragments):
        uc = Uc(UC_ARCH_X86,UC_MODE_64)
        pages = {page for address,raw in fragments for page in range(address & ~4095,(address+len(raw)+4095) & ~4095,4096)}
        for page in sorted(pages):
            uc.mem_map(page,4096)
        for address,raw in fragments:
            uc.mem_write(address,raw)
        uc.mem_map(0x300000,0x4000)
        uc.mem_map(0x400000,4096)
        uc.mem_map(layout.native_pool,(len(native_bytes)+4095) & ~4095)
        uc.mem_write(layout.native_pool,native_bytes)
        uc.mem_map(layout.external_table,(layout.table_bytes+4095) & ~4095)
        uc.mem_write(layout.external_table,table_bytes)
        uc.mem_map(plan.word_table.external_table,(len(word_bytes)+4095) & ~4095)
        uc.mem_write(plan.word_table.external_table,word_bytes)
        uc.mem_map(pointer & ~4095,4096)
        uc.mem_write(pointer,struct.pack('<Q',layout.native_pool))
        for index,(name,number) in enumerate(gprs.items()):
            uc.reg_write(number,0x11110000+index*0x101)
        for index,number in enumerate(xmms):
            uc.reg_write(number,int.from_bytes(struct.pack('<ffff',1.25+index,2.5,3.75,4.5),'little'))
        uc.reg_write(x86.UC_X86_REG_RSP,0x302000)
        uc.mem_write(0x302000,struct.pack('<Q',0x400000))
        uc.reg_write(x86.UC_X86_REG_EFLAGS,0x202)
        return uc

    def snapshot(uc):
        return {r:uc.reg_read(n) for r,n in gprs.items()} | {'flags':uc.reg_read(x86.UC_X86_REG_EFLAGS)} | {
            'xmm'+str(i):uc.reg_read(n) for i,n in enumerate(xmms)}

    # Execute each original memory operation, then its emitted replacement, from identical state.
    member_edits = {e.guard.rva:e for e in plan.rewrites if e.name == 'external_table_member'}
    for rva,binding in plan.member_bindings:
        active_table = plan.word_table if binding.native_offset == 0x112C else layout
        active_bytes = word_bytes if binding.native_offset == 0x112C else table_bytes
        edit = member_edits[rva]
        instruction = next(decoder.disasm(binding.original,source.base+rva))
        mem = next(op for op in instruction.operands if op.type == capstone.x86.X86_OP_MEM)
        for owner_index,target_index in [(0,0),(0,104),(103,103),(199,199),(239,239)]:
            owner = NativeSentientAddress(layout.native_pool+owner_index*NATIVE_SENTIENT_BYTES)
            if binding.index_register is None and binding.base_register == binding.owner_register:
                target_index = 0
            register_values = {binding.owner_register:int(owner)}
            if binding.base_register != binding.owner_register:
                register_values[binding.base_register] = (target_index*active_table.entry_bytes if binding.index_register == binding.owner_register
                                                         else int(owner)+target_index*active_table.entry_bytes)
            if binding.index_register is not None and binding.index_register != binding.owner_register:
                register_values[binding.index_register] = target_index*active_table.entry_bytes//binding.scale+binding.index_bias
            baseline = machine([(source.base+rva,binding.original+binding.trailing_original)])
            changed = machine([(source.base+rva,edit.replacement),(edit.stub_address,edit.stub)])
            for uc in (baseline,changed):
                if binding.trailing_original:
                    uc.reg_write(gprs['rdi'],0x400100)
                    uc.reg_write(gprs['rbx'],0x400200)
                for register,value in register_values.items():
                    uc.reg_write(gprs[register],value)
            old_address = register_values[binding.base_register]+binding.displacement
            if binding.index_register:
                old_address += register_values[binding.index_register]*binding.scale
            external = (active_table.row(owner)[0]+old_address-int(owner)-active_table.native_offset if instruction.mnemonic == 'lea'
                        else active_table.mapped_member(owner,old_address,mem.size))
            returns = binding.trailing_original == b'\xc3'
            stop = 0x400000 if returns else source.base+rva+edit.guard.size
            baseline.emu_start(source.base+rva,source.base+rva+len(binding.original),count=1)
            if instruction.mnemonic == 'lea':
                destination = normalize_register(instruction.reg_name(instruction.operands[0].reg))
                baseline.reg_write(gprs[destination],external)
            if binding.trailing_original:
                baseline.emu_start(source.base+rva+len(binding.original),stop,count=1)
            try:
                changed.emu_start(source.base+rva,stop,count=100)
            except Exception as error:
                raise AssertionError(f'Native rewrite replay failed at {rva:#x}, owner {owner_index}, target {target_index}.') from error
            expected = snapshot(baseline)
            observed = snapshot(changed)
            assert observed == expected, (hex(rva),owner_index,target_index,{k:(observed[k],expected[k]) for k in observed if observed[k]!=expected[k]})
            expected_table = bytearray(active_bytes)
            if instruction.mnemonic != 'lea':
                offset = external-active_table.external_table
                expected_table[offset:offset+mem.size] = baseline.mem_read(old_address,mem.size)
            assert bytes(changed.mem_read(active_table.external_table,active_table.table_bytes)) == bytes(expected_table), hex(rva)
            other_table = layout if binding.native_offset == 0x112C else plan.word_table
            other_bytes = table_bytes if binding.native_offset == 0x112C else word_bytes
            assert bytes(changed.mem_read(other_table.external_table,other_table.table_bytes)) == other_bytes, hex(rva)
            assert bytes(changed.mem_read(layout.native_pool,len(native_bytes))) == native_bytes, hex(rva)
        results.append({'case':'direct_member_native_differential','rva':hex(rva),'states':5,
                        'registersFlagsAndXmmMatch':True,'nativeRecordsUnchanged':True})

    accessor = next(e for e in plan.rewrites if e.name == 'external_table_accessor')
    uc = machine([(source.base+accessor.guard.rva,accessor.replacement),(accessor.stub_address,accessor.stub)])
    for owner_index in (0,103,104,199,239):
        for target_index in (0,103,104,199,239):
            owner = NativeSentientAddress(layout.native_pool+owner_index*NATIVE_SENTIENT_BYTES)
            target = NativeSentientAddress(layout.native_pool+target_index*NATIVE_SENTIENT_BYTES)
            uc.reg_write(x86.UC_X86_REG_RSP,0x302000)
            uc.reg_write(x86.UC_X86_REG_RCX,owner)
            uc.reg_write(x86.UC_X86_REG_RDX,target)
            before = snapshot(uc)
            uc.emu_start(source.base+accessor.guard.rva,0x400000,count=100)
            after = snapshot(uc)
            assert after['rax'] == layout.entry(owner,target)
            assert after['rdx'] == target_index and after['rsp'] == 0x302008
            assert all(after[k] == before[k] for k in before if k not in ('rax','rdx','rsp','flags'))
    results.append({'case':'external_accessor_native_index_prefix','pairs':25,'preservedRegisters':True})

    # Replay allocation and iteration boundaries with the coordinated relocated storage plan.
    def native_program(start, size):
        original = bytearray(source.read(start,size))
        fragments = []
        for edit in plan.rewrites:
            if start <= edit.guard.rva and edit.guard.rva+edit.guard.size <= start+size:
                original[edit.guard.rva-start:edit.guard.rva-start+edit.guard.size] = edit.replacement
                if edit.stub:
                    fragments.append((edit.stub_address,edit.stub))
        return [(source.base+start,bytes(original)),*fragments]

    for name,start,selected,pool_pointer,capacity,stride,flag,register in [
        ('actor',0x24AB010,0x24AB047,source.base+0xA1B0798,200,0x2110,0,'rbx'),
        ('sentient',0x2505CF0,0x2505D3A,source.base+0xA1B0790,240,0x3088,0xA0,'rdi')]:
        for occupied in ((64,199,200) if name == 'actor' else (104,239,240)):
            uc = machine(native_program(start,selected-start))
            pool = plan.actor_array if name == 'actor' else layout.native_pool
            pool_bytes = bytearray(capacity*stride)
            for index in range(occupied):
                pool_bytes[index*stride+flag] = 1
            if name == 'actor':
                uc.mem_map(pool,(len(pool_bytes)+4095) & ~4095)
            uc.mem_write(pool,bytes(pool_bytes))
            uc.mem_write(pool_pointer,struct.pack('<Q',pool))
            selection = []
            def selected_slot(machine,address,size,data):
                if address == source.base+selected:
                    selection.append((machine.reg_read(gprs[register])-pool)//stride)
                    machine.emu_stop()
            uc.hook_add(UC_HOOK_CODE,selected_slot)
            uc.emu_start(source.base+start,0x400000,count=4000)
            assert selection == ([occupied] if occupied < capacity else []), (name,occupied,selection)
            if occupied == capacity:
                assert uc.reg_read(gprs['rax']) == 0
            assert bytes(uc.mem_read(pool,len(pool_bytes))) == bytes(pool_bytes)
        results.append({'case':'expanded_native_allocator_boundary','allocator':name,'capacity':capacity,
                        'lastSlotSelected':True,'fullPoolRejected':True,'initializationNotExecuted':True})

    uc = machine(native_program(0x24B15E0,0x49))
    uc.mem_map(plan.actor_array,(200*0x2110+4095) & ~4095)
    uc.mem_write(plan.actor_array,bytes(200*0x2110))
    uc.mem_write(source.base+0xA1B0798,struct.pack('<Q',plan.actor_array))
    uc.emu_start(source.base+0x24B15E0,0x400000,count=2000)
    assert uc.reg_read(gprs['rax']) == 200
    results.append({'case':'native_actor_free_counter','freeCount':200,'fourRecordGroups':50})

    for start,size,next_actor in [(0x24AE590,0x4C,False),(0x24B1500,0x80,True)]:
        uc = machine(native_program(start,size))
        uc.mem_map(plan.actor_array,(200*0x2110+4095) & ~4095)
        uc.mem_write(plan.actor_array,bytes(200*0x2110))
        uc.mem_write(plan.actor_array+199*0x2110,b'\x01')
        uc.mem_write(plan.actor_array+199*0x2110+8,struct.pack('<Q',0x400100))
        uc.mem_write(0x400100+0x1A4,struct.pack('<I',1))
        uc.mem_write(source.base+0xA1B0798,struct.pack('<Q',plan.actor_array))
        uc.reg_write(gprs['rcx'],plan.actor_array+63*0x2110 if next_actor else 2)
        uc.reg_write(gprs['rdx'],2)
        uc.emu_start(source.base+start,0x400000,count=4000)
        assert uc.reg_read(gprs['rax']) == plan.actor_array+199*0x2110
    results.append({'case':'native_actor_iterators','lastActorSelected':199,'firstAndNextIterators':True})

    uc = machine(native_program(0x24B1580,0x54))
    uc.mem_write(layout.native_pool,bytes(240*0x3088))
    uc.emu_start(source.base+0x24B1580,0x400000,count=2000)
    assert uc.reg_read(gprs['rax']) == 0 and uc.reg_read(gprs['rdx']) == layout.native_pool+240*0x3088
    results.append({'case':'native_sentient_eligibility_scan','recordsVisited':240,'emptyCount':0})

    uc = machine(native_program(0x19DD4AE,28))
    uc.emu_start(source.base+0x19DD4AE,source.base+0x19DD4CA,count=4)
    assert struct.unpack('<Q',uc.mem_read(pointer,8))[0] == layout.native_pool
    assert struct.unpack('<Q',uc.mem_read(source.base+0xA1B0798,8))[0] == plan.actor_array
    results.append({'case':'native_map_pool_rebinding','bothExpandedPoolsPublished':True})

    edits = {e.name:e for e in plan.rewrites if e.name != 'external_table_member'}
    init = edits['map_table_clear']
    init_count = edits['sentient_map_record_count']
    uc = machine([(source.base+0x2505B20,source.read(0x2505B20,0x3B)),
                  (source.base+init.guard.rva,init.replacement),(init.stub_address,init.stub),
                  (source.base+init_count.guard.rva,init_count.replacement)])
    uc.emu_start(source.base+0x2505B20,source.base+0x2505B4D,count=600000)
    assert bytes(uc.mem_read(layout.external_table,layout.table_bytes)) == bytes(layout.table_bytes)
    assert bytes(uc.mem_read(plan.word_table.external_table,len(word_bytes))) == bytes(len(word_bytes))
    expected_native = bytearray(native_bytes)
    for index in range(240):
        expected_native[index*NATIVE_SENTIENT_BYTES+0xA0] = 0
    assert bytes(uc.mem_read(layout.native_pool,len(native_bytes))) == bytes(expected_native)
    results.append({'case':'native_map_initialization','clearedRows':240,'otherNativeBytesUnchanged':True})

    allocation = edits['allocation_owner_row_clear']
    for index in (0,104,239):
        uc = machine([(source.base+allocation.guard.rva,allocation.replacement),(allocation.stub_address,allocation.stub)])
        entity = 0x303000
        owner = NativeSentientAddress(layout.native_pool+index*NATIVE_SENTIENT_BYTES)
        uc.reg_write(x86.UC_X86_REG_RDI,owner)
        uc.reg_write(x86.UC_X86_REG_RSI,entity)
        before = snapshot(uc)
        uc.emu_start(source.base+allocation.guard.rva,source.base+allocation.guard.rva+7,count=10000)
        assert snapshot(uc) == before
        assert struct.unpack('<Q',uc.mem_read(entity+0x260,8))[0] == owner
        expected_table = bytearray(table_bytes)
        start,length = layout.row(owner)
        expected_table[start-layout.external_table:start-layout.external_table+length] = bytes(length)
        assert bytes(uc.mem_read(layout.external_table,layout.table_bytes)) == bytes(expected_table)
        expected_words = bytearray(word_bytes)
        start,length = plan.word_table.row(owner)
        expected_words[start-plan.word_table.external_table:start-plan.word_table.external_table+length] = bytes(length)
        assert bytes(uc.mem_read(plan.word_table.external_table,len(word_bytes))) == bytes(expected_words)
        assert bytes(uc.mem_read(layout.native_pool,len(native_bytes))) == native_bytes
    results.append({'case':'native_allocation_publish_after_row_clear','owners':[0,104,239]})

    for word_reset in (e for e in plan.rewrites if e.name == 'indexed_word_owner_clear'):
        uc = machine([(source.base+word_reset.guard.rva,word_reset.replacement),(word_reset.stub_address,word_reset.stub)])
        owner = NativeSentientAddress(layout.native_pool+239*NATIVE_SENTIENT_BYTES)
        uc.reg_write(gprs[word_reset.owner_register],owner)
        uc.emu_start(source.base+word_reset.guard.rva,source.base+word_reset.guard.rva+word_reset.guard.size,count=1000)
        expected_words = bytearray(word_bytes)
        start,length = plan.word_table.row(owner)
        expected_words[start-plan.word_table.external_table:start-plan.word_table.external_table+length] = bytes(length)
        assert bytes(uc.mem_read(plan.word_table.external_table,len(word_bytes))) == bytes(expected_words)
        assert bytes(uc.mem_read(layout.native_pool,len(native_bytes))) == native_bytes
        assert uc.reg_read(gprs['rcx']) == owner+0x112C
    results.append({'case':'native_indexed_word_load_and_initialization_reset','owner':239,'columns':240,
                    'nativeEmbeddedResetAddressPreserved':True})

    reset = [e for e in plan.rewrites if e.name == 'external_table_member' and 0x2506437 <= e.guard.rva < 0x250647F]
    for owner_index,target_index in [(0,104),(103,199),(239,239)]:
        fragments = [(source.base+0x25063F0,source.guarded(CodeGuard(0x25063F0,0x8F,'d3bddaa583d531e12d75db2687c921bbf25313c969e543bb0e49c67f227c6743')))]
        for edit in reset:
            fragments.extend([(source.base+edit.guard.rva,edit.replacement),(edit.stub_address,edit.stub)])
        uc = machine(fragments)
        owner = NativeSentientAddress(layout.native_pool+owner_index*NATIVE_SENTIENT_BYTES)
        target = NativeSentientAddress(layout.native_pool+target_index*NATIVE_SENTIENT_BYTES)
        uc.reg_write(x86.UC_X86_REG_RCX,owner)
        uc.reg_write(x86.UC_X86_REG_RDX,target)
        uc.emu_start(source.base+0x25063F0,source.base+0x250647F,count=1200)
        expected_table = bytearray(table_bytes)
        entry = layout.entry(owner,target)-layout.external_table
        expected_table[entry:entry+0x48] = bytes(0x48)
        assert bytes(uc.mem_read(layout.external_table,layout.table_bytes)) == bytes(expected_table)
        assert bytes(uc.mem_read(layout.native_pool,len(native_bytes))) == native_bytes
        assert uc.reg_read(x86.UC_X86_REG_RDI) == owner and uc.reg_read(x86.UC_X86_REG_RBX) == target
    results.append({'case':'native_target_entry_reset','pairs':3,'ordinaryOwnerFieldsPreserved':True})

    load,load_count = edits['load_entry_clear'],edits['load_row_column_count']
    for owner_index in (0,104,239):
        fragments = [(source.base+0xC45A9,source.read(0xC45A9,0x2D)),
                     (source.base+load.guard.rva,load.replacement),(load.stub_address,load.stub),
                     (source.base+load_count.guard.rva,load_count.replacement),(load_count.stub_address,load_count.stub)]
        uc = machine(fragments)
        owner = NativeSentientAddress(layout.native_pool+owner_index*NATIVE_SENTIENT_BYTES)
        uc.reg_write(x86.UC_X86_REG_RBP,owner)
        uc.reg_write(x86.UC_X86_REG_RBX,0)
        uc.emu_start(source.base+0xC45A9,source.base+0xC45D6,count=24000)
        expected_table = bytearray(table_bytes)
        start,length = layout.row(owner)
        expected_table[start-layout.external_table:start-layout.external_table+length] = bytes(length)
        assert bytes(uc.mem_read(layout.external_table,layout.table_bytes)) == bytes(expected_table)
        assert bytes(uc.mem_read(layout.native_pool,len(native_bytes))) == native_bytes
        assert uc.reg_read(x86.UC_X86_REG_RBX) == 240
    results.append({'case':'native_load_clear_loop','owners':[0,104,239],'columns':240})

    # Preserve the native owner-selection loop. Record its reset arguments at the call boundary.
    # Unrelated relationship routines and the downstream reset body use owned RET stand-ins here.
    for victim_index in (104,239):
        fragments = [(source.base+0x2506270,source.read(0x2506270,0x17B)),
                     (source.base+0x25074F0,b'\xc3'),(source.base+0x25063F0,b'\xc3')]
        for edit in plan.rewrites:
            if edit.name == 'sentient_free_owner_count':
                fragments.extend([(source.base+edit.guard.rva,edit.replacement),(edit.stub_address,edit.stub)])
        uc = machine(fragments)
        entities = source.base+0x25000000
        uc.mem_map(entities,240*0x400)
        for index in range(240):
            uc.mem_write(layout.native_pool+index*NATIVE_SENTIENT_BYTES,struct.pack('<Q',entities+index*0x400))
            uc.mem_write(layout.native_pool+index*NATIVE_SENTIENT_BYTES+0x78,bytes(8))
            uc.mem_write(layout.native_pool+index*NATIVE_SENTIENT_BYTES+0xA0,b'\x01')
        victim = layout.native_pool+victim_index*NATIVE_SENTIENT_BYTES
        selected = []

        def record_reset(uc,address,size,user_data):
            if address == source.base+0x25063F0:
                selected.append((uc.reg_read(x86.UC_X86_REG_RCX)-layout.native_pool)//NATIVE_SENTIENT_BYTES)
                assert uc.reg_read(x86.UC_X86_REG_RDX) == victim

        uc.hook_add(UC_HOOK_CODE,record_reset)
        uc.reg_write(x86.UC_X86_REG_RCX,victim)
        uc.emu_start(source.base+0x2506270,0x400000,count=20000)
        assert selected == [index for index in range(240) if index != victim_index]
    results.append({'case':'native_free_owner_selection','victims':[104,239],'ownersPerVictim':239,
                    'limit':'Reset arguments only. Unrelated routines and reset body use RET stand-ins in this selection replay.'})

    # Execute the real CRT registration, iterator, constructor and cleanup callback.
    guards = [CodeGuard(0x2DD10C0,62,'ecc43538c69fdb0c7f49d3fd21e80d2e50099b4eebf795db7e838b606f105ab2'),
              CodeGuard(0x2EFA3D0,30,'5656dd8a2d8e4cb5818dcc4ea2dd85216a2361579e58784b3258dca62e8cc8f5'),
              CodeGuard(0x2BC9E94,100,'a3986907c6ac9512e1f9bf07cb2bbe4902929ca00b8231ade06d51c8eb4e9e65'),
              CodeGuard(0x2BC9EF8,93,'4f2a69592c3976a72fd72bacc989b1d383cb8835e64e88bda4baa14390a6a6be'),
              CodeGuard(0x19C00B0,146,'9b843882ef196d717e6a4076a4b39ca94f5dd0393ec92b1d54308bf8541477f9'),
              CodeGuard(0x19C0160,15,'98515196f94346f90d1e2b7b7e8c0fdf0215f2e0934edaa58422cd61fe9fc563')]
    fragments = [(source.base+g.rva,source.guarded(g)) for g in guards]
    for edit in plan.rewrites:
        if edit.name.startswith('actor_lifetime'):
            fragments.append((source.base+edit.guard.rva,edit.replacement))
    uc = machine(fragments)
    actor_bytes = bytes([0xA5])*(201*0x2110)
    uc.mem_map(plan.actor_array,(len(actor_bytes)+4095) & ~4095)
    uc.mem_write(plan.actor_array,actor_bytes)
    construction,cleanup = [],[]

    def record_actor(uc,address,size,user_data):
        if address == source.base+0x19C00B0:
            construction.append((uc.reg_read(x86.UC_X86_REG_RCX)-plan.actor_array)//0x2110)
        if address == source.base+0x19C0160:
            cleanup.append((uc.reg_read(x86.UC_X86_REG_RCX)-plan.actor_array)//0x2110)

    uc.hook_add(UC_HOOK_CODE,record_actor)
    uc.emu_start(source.base+0x2DD10C0,source.base+0x2DD10EE,count=10000)
    assert construction == list(range(200))
    constructor_row = bytes(uc.mem_read(plan.actor_array,0x2110))
    expected_row = bytearray(actor_bytes[:0x2110])
    expected_row[0x8B0:0x910] = bytes(0x60)
    struct.pack_into('<Q',expected_row,0x8A0,source.base+0x2F1BB88)
    struct.pack_into('<I',expected_row,0x920,0)
    expected_row[0x924] = 0
    for field in (0x8B0,0x8B4,0x8B8):
        struct.pack_into('<I',expected_row,field,0x7E967699)
    for field in (0x8C0,0x8C4,0x8C8):
        struct.pack_into('<I',expected_row,field,0xFE967699)
    assert constructor_row == bytes(expected_row)
    for index in range(200):
        assert bytes(uc.mem_read(plan.actor_array+index*0x2110,0x2110)) == constructor_row
    assert bytes(uc.mem_read(plan.actor_array+200*0x2110,0x2110)) == actor_bytes[-0x2110:]
    uc.reg_write(x86.UC_X86_REG_RSP,0x302000)
    uc.mem_write(0x302000,struct.pack('<Q',0x400000))
    uc.emu_start(source.base+0x2EFA3D0,0x400000,count=10000)
    assert cleanup == list(reversed(range(200)))
    struct.pack_into('<Q',expected_row,0x8A0,source.base+0x2F1BB40)
    for index in range(200):
        assert bytes(uc.mem_read(plan.actor_array+index*0x2110,0x2110)) == bytes(expected_row)
    assert bytes(uc.mem_read(plan.actor_array+200*0x2110,0x2110)) == actor_bytes[-0x2110:]
    results.append({'case':'native_actor_construction_and_cleanup','constructed':200,'cleaned':200,
                    'reverseCleanupOrder':True,'nextRecordUnchanged':True})

    for bad in (layout.native_pool-0x3088,layout.native_pool+1,layout.native_pool+240*0x3088):
        try:
            layout.owner_index(NativeSentientAddress(bad))
        except ValueError:
            continue
        raise AssertionError('The address mapper admitted an invalid native owner.')
    for native,external,capacity in [(int(layout.native_pool),int(layout.external_table),104),
                                     (int(layout.native_pool),int(layout.native_pool)+8,240),
                                     (int(layout.native_pool),(1 << 64)-8,240)]:
        try:
            TableLayout(NativeSentientAddress(native),ExternalTableAddress(external),capacity)
        except ValueError:
            continue
        raise AssertionError('The address mapper admitted an invalid layout.')
    try:
        source.guarded(CodeGuard(0x2505BB0,50,'0'*64))
    except ValueError:
        results.append({'case':'layout_and_changed_guard_refusal','invalidLayoutsRejected':3,'changedGuardRejected':True})
    else:
        raise AssertionError('A changed native code guard entered the plan.')
    try:
        plan.require_activation()
    except RuntimeError:
        results.append({'case':'incomplete_plan_activation_refused','invalidOwnerAddressesRejected':3})
    else:
        raise AssertionError('An incomplete table plan allowed activation.')
    report = {'status':'guarded_external_table_owned_native_replay_passed','cases':results,
              'directInstructionStates':len(plan.member_bindings)*5,'rewrites':len(plan.rewrites),'gameLaunched':False,
              'capacity200Implemented':False,'coverageComplete':False,
              'implementationVersion':'owned-table-prototype-2',
              'supportedExecutableSha256':'0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0',
              'moduleManifestSha256':hashlib.sha256(module.read_bytes()).hexdigest(),
              'sourceFiles':{str(p.relative_to(PATCHES.parents[2])):hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [PATCHES/'table_layout.py',PATCHES/'x64_table.py',PATCHES/'table_plan.py',
                                       PATCHES/'captured_code.py',PATCHES/'storage_plan.py',PATCHES/'storage_inventory.json',
                                       PATCHES/'omitted_consumers.json',PATCHES/'indexed_words.json',Path(__file__).resolve()]},
              'rewriteGuards':[{'rva':hex(e.guard.rva),'size':e.guard.size,'sha256':e.guard.sha256,
                                'replacementSha256':hashlib.sha256(e.replacement).hexdigest(),
                                'stubSha256':hashlib.sha256(e.stub).hexdigest() if e.stub else None} for e in plan.rewrites],
              'tableBytes':layout.table_bytes,'nativeRecordBytes':NATIVE_SENTIENT_BYTES,
              'indexedWordTableBytes':plan.word_table.table_bytes,
              'limit':'Owned native instruction replay. Additional consumers, native unwind, serialization, activation, AAE and live compatibility remain unverified.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return {'status':report['status'],'cases':len(results),'directInstructionStates':report['directInstructionStates'],'output':str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--dependencies',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module,args.dependencies,args.output),indent=2))
