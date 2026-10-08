"""Replay captured native sprint cancellation with an owned player/input state.

Only the bounded predicate and its actual perk accessor execute. Unrelated
movement-mode and dvar-thread checks use recorded fixture return values.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RIP, UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RSP


def run(manifest: Path, output: Path):
    info=json.loads(manifest.read_text()); base=int(info['baseAddress'],0)
    segments=[]
    for row in info['ranges']:
        raw=(manifest.parent/row['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row['sha256']
        segments.append((int(row['moduleOffset'],0),raw))
    def captured(rva,size):
        for start,raw in segments:
            if start<=rva and rva+size<=start+len(raw): return raw[rva-start:rva-start+size]
        raise ValueError('Requested native range is absent.')
    code_ranges=[(0x2616a90,0x1b0),(0x26523c0,0x3b),(0x2609f70,0x2c),(0x160690,0x26),(0x2671510,0x16)]
    # Native accessor indexes the weapon header table; the test supplies one owned header.
    table=0x2671517+struct.unpack('<i',captured(0x2671513,4))[0]
    dvar=0x2609f80+struct.unpack('<i',captured(0x2609f7c,4))[0]
    stub_rvas={0x169760:0,0x169860:0,0xa7940:0,0x2609560:0,0x2606080:0,0x260ebe0:0,0x2260a70:0}
    report=[]
    for name,perk,attack,forward,weapon_type,expected in [
        ('war_machine_bit_clear',False,True,127,2,True),
        ('war_machine_bit_set',True,True,127,2,False),
        ('death_machine_bit_clear',False,True,127,0,True),
        ('death_machine_bit_set',True,True,127,0,False),
        ('non_sprintable_type_preserved',True,True,127,7,True),
        ('release_forward_preserved',True,True,0,2,True),
        ('without_attack',False,False,127,2,False),
    ]:
        uc=Uc(UC_ARCH_X86,UC_MODE_64); mapped=set()
        def put(addr,raw):
            for page in range(addr&~4095,(addr+len(raw)+4095)&~4095,4096):
                if page not in mapped:uc.mem_map(page,4096);mapped.add(page)
            uc.mem_write(addr,raw)
        for rva,size in code_ranges:put(base+rva,captured(rva,size))
        for rva in stub_rvas:put(base+rva,b'\xc3')
        put(base+dvar,bytes(8));put(base+table+8,struct.pack('<Q',0x10004000))
        ps=0x10000000;pm=0x10002000;settings=0x10006000;stack=0x20000000;stop=0x30000000
        put(ps,bytes(0x1000));put(pm,bytes(0x1000));put(0x10004000,bytes(768));put(settings,bytes(0x2000));put(stack,bytes(0x2000));put(stop,b'\x90')
        put(pm,struct.pack('<Q',ps));put(pm+0x40,struct.pack('<b',forward));put(pm+0xc,struct.pack('<I',0x80000000 if attack else 0))
        put(ps+0x2c0,struct.pack('<Q',1));put(ps+0x10,struct.pack('<Q',0x20));put(ps+0x5c,struct.pack('<I',6));put(ps+0x8c,struct.pack('<I',12))
        put(ps+0xb0c,struct.pack('<I',(1<<21) if perk else 0));put(0x10004000+24,struct.pack('<Q',settings));put(settings+0x6c,struct.pack('<I',weapon_type))
        rsp=stack+0x1000;put(rsp,struct.pack('<Q',stop));uc.reg_write(UC_X86_REG_RSP,rsp);uc.reg_write(UC_X86_REG_RCX,pm)
        trace=[]
        def hook(machine,addr,size,data):
            if addr==stop:machine.emu_stop();return
            if addr-base in stub_rvas:
                trace.append(hex(addr-base));machine.reg_write(UC_X86_REG_RAX,stub_rvas[addr-base])
                sp=machine.reg_read(UC_X86_REG_RSP);ret=struct.unpack('<Q',machine.mem_read(sp,8))[0];machine.reg_write(UC_X86_REG_RSP,sp+8);machine.reg_write(UC_X86_REG_RIP,ret)
        uc.hook_add(UC_HOOK_CODE,hook)
        try: uc.emu_start(base+0x2616a90,stop,count=2000)
        except Exception:
            print(name, hex(uc.reg_read(UC_X86_REG_RIP)), trace); raise
        assert uc.reg_read(UC_X86_REG_RIP) == stop, 'Native replay did not return.'
        cancellation=bool(uc.reg_read(UC_X86_REG_RAX)&255)
        assert cancellation==expected,(name,cancellation,expected)
        report.append({'case':name,'sprintCancellationPredicate':cancellation,'expected':expected,'stubbedCalls':trace})
    result={'status':'captured_native_predicate_replay_passed','cases':report,'ranges':[{'rva':hex(rva),'size':size,'sha256':hashlib.sha256(captured(rva,size)).hexdigest()} for rva,size in code_ranges],'scope':'Owned inputs with actual native predicate, weapon accessor and perk bit check; unrelated fixture-return dependencies remain explicit. Active game, animations, client prediction and multiplayer unvalidated.'}
    output=output.resolve();lab=(Path.home()/'.codex/labs/bo3-engine').resolve()
    if lab not in output.parents or output.exists():raise ValueError('Use a new private lab artifact path.')
    output.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native-manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.native_manifest,a.output),indent=2))
