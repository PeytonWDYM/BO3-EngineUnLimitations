"""Replay the guarded native skeletal reset, reservation, reuse, replacement, and refusal paths."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

PATCHES = Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode


def run(module: Path, executable: Path, native_replay: Path, output: Path) -> dict:
    lab=(Path.home()/'.codex/labs/bo3-engine').resolve()
    if output.exists() or lab not in output.resolve().parents or lab not in native_replay.resolve().parents:
        raise ValueError('Use private native inputs and a new result folder in the BO3 lab.')
    from skeletal_storage import prepare_skeletal_storage, OWNER_GUARDS, BANK_BYTES, TOTAL_BYTES, PREALLOCATION_GLOBALS, LEAF_UNWIND
    code=CapturedCode(module,executable)
    bank=code.base+0x24000000
    address=code.base+0x23010000
    edits=prepare_skeletal_storage(code,bank,address)
    assert len(edits)==2 and edits[0].guard.rva==0x135C82C and edits[1].guard.rva==0x13C84BF
    assert edits[0].replacement[5:]==bytes.fromhex('4883e0f09090')
    assert edits[1].replacement==bytes.fromhex('81ff')+(BANK_BYTES-16).to_bytes(4,'little')
    assert BANK_BYTES==0x4800000 and TOTAL_BYTES==2*BANK_BYTES
    assert PREALLOCATION_GLOBALS==((0x535D188,8),) and LEAF_UNWIND==bytes.fromhex('01000000')
    refusals=[]
    class ChangedCode(CapturedCode):
        def read(self,rva,size):
            raw=bytearray(super().read(rva,size))
            if rva<=self.mutation<rva+size:
                raw[self.mutation-rva]^=1
            return bytes(raw)
    changed=object.__new__(ChangedCode)
    changed.__dict__.update(code.__dict__)
    for guard in OWNER_GUARDS:
        changed.mutation=guard.rva+guard.size//2
        try:
            prepare_skeletal_storage(changed,bank,address)
        except ValueError:
            refusals.append(hex(changed.mutation))
        else:
            raise AssertionError('A changed native skeletal contract escaped refusal.')
    invalids=((bank+1,address),(code.base,address),(code.base+0x7FFF0000,address),(bank,bank),(bank,address+1),(bank,code.base+0x80000000))
    for bad_bank,bad_address in invalids:
        try:
            prepare_skeletal_storage(code,bad_bank,bad_address)
        except ValueError:
            pass
        else:
            raise AssertionError('An invalid skeletal allocation escaped refusal.')
    sys.path.insert(0,str(native_replay.parent))
    replay=runpy.run_path(str(native_replay))
    assert replay['code'].executable_sha256==code.executable_sha256 and replay['code'].base==code.base
    replay['run'].__globals__['RECIPE_FACTORY']=prepare_skeletal_storage
    lifecycle,machine,last=replay['run']()
    executed=machine.executed|last.executed
    substituted={0x2242380,0x2242730}
    uncovered=[hex(rva) for rva in sorted(executed-substituted) if not address-code.base<=rva<address-code.base+len(edits[0].stub) and not any(g.rva<=rva<g.rva+g.size for g in OWNER_GUARDS)]
    assert not uncovered,uncovered
    output.mkdir(parents=True)
    result={'passed':True,'lifecycle':lifecycle,'sourceGuardRefusals':refusals,'invalidStorageRefusals':len(invalids),'executedAddresses':len(executed),'gameWrites':0,'runtimeIntegrated':False,
            'edits':[{'name':e.name,'rva':hex(e.guard.rva),'replacement':e.replacement.hex(),'stub':e.stub.hex(),'stubAddress':hex(e.stub_address) if e.stub_address else None} for e in edits],
            'files':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__),PATCHES/'skeletal_storage.py',native_replay)},
            'limit':'Private native execution. Profiling endpoints are substituted. Constructor cache-clear prefix executes. Full model construction, live gameplay, concurrent contention, and exception dispatch remain outside this replay.'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'sourceGuardRefusals':len(refusals),'output':str(output)},indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','native-replay','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    run(args.module,args.executable,args.native_replay,args.output)
