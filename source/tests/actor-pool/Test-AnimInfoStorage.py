"""Verify emitted shared animation-node storage through native lifecycle and archive paths."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

PATCHES=Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0,str(PATCHES))
from captured_code import CapturedCode


def run(module: Path, executable: Path, native_replay: Path, output: Path) -> dict:
    lab=(Path.home()/'.codex/labs/bo3-engine').resolve()
    if output.exists() or lab not in output.resolve().parents or lab not in native_replay.resolve().parents:
        raise ValueError('Use private native inputs and a new result folder in the BO3 lab.')
    from anim_info_storage import prepare_anim_info_storage, OWNER_GUARDS, BANK_OFFSET, BANK_BYTES, ARENA_END, PREALLOCATION_GLOBALS
    code=CapturedCode(module,executable)
    bank=code.base+0x30000000
    edits=prepare_anim_info_storage(code,bank)
    assert len(edits)==73 and all(not e.stub and e.stub_address is None for e in edits)
    assert BANK_OFFSET==0xC000000 and BANK_BYTES==0x580000 and ARENA_END==0xC580000
    assert PREALLOCATION_GLOBALS==((0x17DF81E0,528000),)
    assert edits[-1].guard.rva==0x22C9BD0 and edits[-1].guard.size==150
    assert len(edits[-1].replacement)==150
    sys.path.insert(0,str(native_replay.parent))
    replay=importlib.import_module(native_replay.stem)
    assert replay.code.executable_sha256==code.executable_sha256 and replay.code.base==code.base
    proved=replay.edits()
    assert [(e.guard.rva,e.replacement) for e in edits]==proved
    replay.SOURCE_FACTORY=prepare_anim_info_storage
    lifecycle=replay.run()
    archives=importlib.import_module('replay_archive')
    archive_cases=[archives.run_case(index,context) for index,context in ((5999,-1),(6000,0),(32767,1),(32768,-1),(65535,0))]
    snapshots=importlib.import_module('replay_clone_snapshot')
    clone_cases=[snapshots.run_case(context) for context in (-1,0,1)]
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
            prepare_anim_info_storage(changed,bank)
        except ValueError:
            refusals.append(hex(changed.mutation))
        else:
            raise AssertionError('A changed native animation-node contract escaped refusal.')
    identity=object.__new__(CapturedCode)
    identity.__dict__.update(code.__dict__)
    identity.executable_sha256='unknown'
    invalids=(bank+1,code.base,code.base+0x7FFF0000,code.base+0x80000000)
    for invalid in (identity,*invalids):
        try:
            prepare_anim_info_storage(invalid if isinstance(invalid,CapturedCode) else code,bank if isinstance(invalid,CapturedCode) else invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('An invalid animation-node identity or bank escaped refusal.')
    output.mkdir(parents=True)
    result={'passed':True,'lifecycle':lifecycle,'archiveCases':archive_cases,'cloneSnapshotCases':clone_cases,'sourceGuardRefusals':refusals,'invalidIdentityAndBankRefusals':1+len(invalids),'sourceEdits':len(edits),'sourceGuards':len(OWNER_GUARDS),'coldZeroSpans':PREALLOCATION_GLOBALS,'gameWrites':0,'runtimeIntegrated':False,'files':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__),PATCHES/'anim_info_storage.py',PATCHES/'anim_info_inventory.json',native_replay)},'limit':'Private native execution. The critical-section leave and native error sink are substituted. Full-domain allocation, release, reset, native root-and-leaf saves, clone, and compact snapshots execute emitted source bytes. Whole-game fanout, dynamic notifications, compressed archive refill, migration, matching peers, and sustained performance remain unverified.'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'sourceEdits':len(edits),'sourceGuardRefusals':len(refusals),'output':str(output)},indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('module','executable','native-replay','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    run(args.module,args.executable,args.native_replay,args.output)
