"""Replay the new actor storage omissions in owned x64 memory."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode
from table_plan import prepare
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from storage_plan import StorageLayout
from omissions import omission_inventory


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0,str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64

    output = output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    code = CapturedCode(module,executable)
    base = code.base
    layout = TableLayout(NativeSentientAddress(base+0x21000000),ExternalTableAddress(base+0x22000000))
    storage = StorageLayout(base+0x23000000,base+0x24000000,base+0x25000000,base+0x26000000,base+0x27000000)
    plan = prepare(code,layout,base+0x20000000,storage)
    shape = layout.shape
    results = []

    def reg(name: str) -> int:
        return getattr(x64,'UC_X86_REG_'+name.upper())

    def program(start: int, end: int) -> list[tuple[int,bytes]]:
        body = bytearray(code.read(start,end-start))
        fragments = []
        for edit in plan.rewrites:
            if start <= edit.guard.rva and edit.guard.rva+edit.guard.size <= end:
                body[edit.guard.rva-start:edit.guard.rva-start+edit.guard.size] = edit.replacement
                if edit.stub:
                    fragments.append((edit.stub_address,edit.stub))
        return [(base+start,bytes(body)),*fragments]

    def machine(fragments: list[tuple[int,bytes]], regions: list[tuple[int,int]] = ()):
        uc = Uc(UC_ARCH_X86,UC_MODE_64)
        pages = set()
        for address,size in [(address,len(raw)) for address,raw in fragments]+list(regions)+[(0x300000,0x4000),(0x400000,4096),(base+0xA1B0000,4096)]:
            pages.update(range(address & ~4095,(address+size+4095) & ~4095,4096))
        for page in sorted(pages):
            uc.mem_map(page,4096)
        for address,raw in fragments:
            uc.mem_write(address,raw)
        uc.reg_write(reg('rsp'),0x302000)
        uc.mem_write(0x302000,struct.pack('<Q',0x400000))
        uc.mem_write(base+0xA1B0798,struct.pack('<Q',storage.actors))
        return uc

    # Execute the actual DObj index quotient and lookup through actor299.
    for start,end,input_register,output_register in [(0x24B5EB0,0x24B5EE0,'rcx','rax'),
                                                    (0x24AE611,0x24AE645,'rsi','rcx')]:
        fragments = program(start,end)
        uc = machine(fragments,[(storage.dobj,shape.dobj_bytes+8)])
        for index in (0,63,64,199,299):
            token = 0x70000000+index
            uc.mem_write(storage.dobj+index*8,struct.pack('<Q',token))
            uc.reg_write(reg(input_register),storage.actors+index*0x2110)
            uc.reg_write(reg('rsp'),0x302000)
            uc.emu_start(base+start,0x400000 if start==0x24B5EB0 else base+end,count=100)
            assert uc.reg_read(reg(output_register)) == token
        results.append({'case':'native_dobj_lookup','rva':hex(start),'indices':[0,63,64,199,299]})

    # Replay native setup. Only the allocation callback uses an owned RET stand-in.
    allocation = base+0x22C7FE0
    uc = machine(program(0x19E131D,0x19E1349)+[(allocation,b'\xc3')],[(storage.dobj,shape.dobj_bytes+8)])
    uc.mem_write(storage.dobj,bytes([0xA5])*(shape.dobj_bytes+8))
    allocated = []

    def allocate(uc,address,size,data):
        if address == allocation:
            allocated.append(0x70000000+len(allocated))
            uc.reg_write(reg('rax'),allocated[-1])

    uc.hook_add(UC_HOOK_CODE,allocate)
    uc.emu_start(base+0x19E131D,base+0x19E1349,count=10000)
    assert len(allocated) == shape.actors
    assert bytes(uc.mem_read(storage.dobj,shape.dobj_bytes)) == struct.pack('<'+'Q'*shape.actors,*allocated)
    assert bytes(uc.mem_read(storage.dobj+shape.dobj_bytes,8)) == bytes([0xA5])*8
    results.append({'case':'native_dobj_setup','entries':shape.actors,'nextEntryUnchanged':True,
                    'limit':'The allocation callback is an owned RET stand-in.'})

    # Restore the unrelated static boundary after relocated DObj setup.
    boundary = code.read(0x19E13EE,7)
    static_start = base+0x19E13F5+struct.unpack('<i',boundary[3:])[0]
    static_end = base+0xA588868
    uc = machine(program(0x19E13EE,0x19E1413)+[(allocation,b'\xc3')],[(static_start,static_end-static_start+8)])
    uc.mem_write(static_start,bytes([0xA5])*(static_end-static_start+8))
    uc.reg_write(reg('r14'),storage.dobj)
    allocated.clear()
    uc.hook_add(UC_HOOK_CODE,allocate)
    uc.emu_start(base+0x19E13EE,base+0x19E1413,count=200)
    assert len(allocated)==6 and uc.reg_read(reg('rdi'))==static_end and uc.reg_read(reg('r14'))==static_end
    expected = bytearray(bytes([0xA5])*(static_end-static_start+8))
    for index,value in enumerate(allocated):
        struct.pack_into('<Q',expected,index*0xEE8,value)
    assert bytes(uc.mem_read(static_start,len(expected)))==bytes(expected)
    results.append({'case':'adjacent_static_setup_boundary','entries':6,'nativeDobjEntryUnchanged':True})

    release = base+0x22C8B50
    uc = machine(program(0x19C39B0,0x19C39DB)+[(release,b'\xc3')],[(storage.dobj,shape.dobj_bytes+8)])
    values = list(range(0x70000000,0x70000000+shape.actors))
    uc.mem_write(storage.dobj,struct.pack('<'+'Q'*shape.actors,*values)+bytes([0xA5])*8)
    uc.reg_write(reg('rsi'),0)
    released=[]

    def record_release(uc,address,size,data):
        if address==release:
            released.append(uc.reg_read(reg('rcx')))
            assert uc.reg_read(reg('rdx'))==0

    uc.hook_add(UC_HOOK_CODE,record_release)
    uc.emu_start(base+0x19C39B0,base+0x19C39DB,count=10000)
    assert released==values and bytes(uc.mem_read(storage.dobj,shape.dobj_bytes))==bytes(shape.dobj_bytes)
    assert bytes(uc.mem_read(storage.dobj+shape.dobj_bytes,8))==bytes([0xA5])*8
    results.append({'case':'native_dobj_cleanup','entries':shape.actors,'nextEntryUnchanged':True,
                    'limit':'The release callback is an owned RET stand-in.'})

    # Exercise each widened signed branch at the actual native compare site.
    edits = [item for item in plan.rewrites if item.name=='actor_iterator']
    for edit in edits:
        site = next(item for item in omission_inventory() if int(item['rva'],0)==edit.guard.rva)
        target = base+int(site['branchTargetRva'],0)
        continuation = base+edit.guard.rva+edit.guard.size
        for index in (-1,0,63,64,299,300,339):
            uc = machine([(base+edit.guard.rva,edit.replacement),(edit.stub_address,edit.stub)],[(target,1),(continuation,1)])
            uc.reg_write(reg('r8'),index & ((1 << 64)-1))
            stops=[]
            def stop(uc,address,size,data):
                if address in (target,continuation):
                    stops.append(address)
                    uc.emu_stop()
            uc.hook_add(UC_HOOK_CODE,stop)
            uc.emu_start(base+edit.guard.rva,0,count=20)
            taken = index>=shape.actors if site['condition']==0x8D else index<shape.actors
            assert stops==[target if taken else continuation]
            assert uc.reg_read(reg('r8'))==index & ((1 << 64)-1)
        results.append({'case':'native_signed_iterator_branch','rva':hex(edit.guard.rva),'states':7})

    uc = machine(program(0x24AC970,0x24AC9B6),[(storage.actors,shape.actor_bytes)])
    uc.mem_write(storage.actors+(shape.actors-1)*0x2110,b'\x01')
    uc.mem_write(storage.actors+(shape.actors-1)*0x2110+8,struct.pack('<Q',0x400100))
    uc.mem_write(0x400100+0x1A4,struct.pack('<I',1))
    uc.emu_start(base+0x24AC970,base+0x24AC9B6,count=10000)
    assert uc.reg_read(reg('r9'))==shape.actors-1
    results.append({'case':'native_actor_lifecycle_scan','lastActorSelected':shape.actors-1,
                    'limit':'Stops before native destruction calls.'})

    # Keep the stock corpse scan and policy comparison while expanding the actor scan.
    corpse = base+0x28000000
    policy_instruction = code.read(0x1B75DC0,7)
    policy = base+0x1B75DC7+struct.unpack('<i',policy_instruction[3:])[0]
    for occupied,limit in [(299,300),(300,300),(300,301)]:
        uc = machine(program(0x1B75DC0,0x1B75E59),[(storage.actors,shape.actor_bytes),(corpse,64*0x21A0),(policy,4)])
        uc.mem_write(base+0xA1B0770,struct.pack('<Q',corpse))
        uc.mem_write(policy,struct.pack('<I',limit))
        for index in range(occupied):
            uc.mem_write(storage.actors+index*0x2110,b'\x01')
        uc.emu_start(base+0x1B75DC0,0x400000,count=10000)
        assert uc.reg_read(reg('rax'))==int(occupied>=limit)
        assert uc.reg_read(reg('rcx'))==occupied
    results.append({'case':'native_live_admission_scan','actorCases':3,'corpseEntries':64,'policyUnchanged':True})

    blocked = [site for site in omission_inventory() if site['status']=='blocked']
    assert {int(site['rva'],0) for site in blocked}=={0x24AE77F,0x1BF9A98}
    assert all(not any(edit.guard.rva<=int(site['rva'],0)<edit.guard.rva+edit.guard.size for edit in plan.rewrites) for site in blocked)
    try:
        plan.require_activation()
    except RuntimeError:
        results.append({'case':'sentinel_and_actor_state_remain_gated','sites':blocked})
    else:
        raise AssertionError('The incomplete actor plan admitted activation.')

    report = {'status':'actor_storage_omissions_owned_replay_passed','cases':results,'rewrites':len(plan.rewrites),
              'shape':{'actors':shape.actors,'sentients':shape.sentients},'gameLaunched':False,'deploymentAllowed':False,
              'executableSha256':code.executable_sha256,'moduleManifestSha256':hashlib.sha256(module.read_bytes()).hexdigest(),
              'sourceFiles':{str(path.relative_to(PATCHES.parents[2])):hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in [*PATCHES.glob('*.py'),*PATCHES.glob('*.json'),Path(__file__)]},
              'limit':'Owned x64 instruction replay only. Native callback behavior, Windows unwind, saves, startup, and peers remain unverified.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return {'status':report['status'],'cases':len(results),'output':str(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--dependencies',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.module,args.executable,args.dependencies,args.output),indent=2))
