"""Export a disabled actor preparation plan into a new private lab directory."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from captured_code import CapturedCode, MANIFEST_SHA256
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from table_plan import prepare, ACTIVATION_GATES
from storage_plan import StorageLayout
from omissions import omission_inventory
from unwind import requirements
from shape import ActorShape
from actor_wire import prepare_actor_wire


def export(module: Path, executable: Path, output: Path, actors: int = 500) -> dict:
    output = output.resolve()
    if (Path.home()/'.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code = CapturedCode(module,executable)
    layout = TableLayout(NativeSentientAddress(code.base+0x21000000),ExternalTableAddress(code.base+0x22000000),ActorShape(actors))
    storage = StorageLayout(*(code.base+offset for offset in (0x24000000,0x26000000,0x28000000,0x2A000000,0x2C000000)))
    plan = prepare(code,layout,code.base+0x20000000,storage)
    unwind = requirements(code,plan.rewrites)
    wire = prepare_actor_wire(code,layout.shape)
    output.mkdir(parents=True)
    edits = []
    for index,edit in enumerate(plan.rewrites):
        item = {'name':edit.name,'rva':hex(edit.guard.rva),'size':edit.guard.size,'sha256':edit.guard.sha256,
                'replacement':edit.replacement.hex(),'ownerRegister':edit.owner_register}
        if edit.stub:
            filename = f'stub-{index:03d}.bin'
            (output/filename).write_bytes(edit.stub)
            item.update(stubAddress=hex(edit.stub_address),stubFile=filename,stubSha256=hashlib.sha256(edit.stub).hexdigest())
        edits.append(item)
    report = {'status':f'disabled_actor_{actors}_preparation','deploymentAllowed':False,'coverageComplete':False,
              'executableSha256':code.executable_sha256,'moduleManifestSha256':MANIFEST_SHA256,
              'shape':asdict(layout.shape)|{'sentients':layout.capacity},
              'addressSpace':'Owned replay allocations against the pinned unpacked module. These are not admitted runtime addresses.',
              'storageRegions':[{'address':hex(start),'bytes':size} for start,size in storage.regions(layout)],
              'storageBytes':sum(size for _,size in storage.regions(layout)),
              'matrices':{'knowledgeEntryBytes':layout.entry_bytes,'knowledgeRowBytes':layout.row_bytes,'knowledgeBytes':layout.table_bytes,
                          'wordRowBytes':plan.word_table.row_bytes,'wordBytes':plan.word_table.table_bytes},
              'rewrites':edits,'omissions':omission_inventory(),'unwindRequirements':unwind,'activationGates':ACTIVATION_GATES,
              'wirePreparation':{'bits':layout.shape.actors.bit_length(),'deploymentAllowed':False,
                  'rewrites':[{'name':edit.name,'rva':hex(edit.guard.rva),'size':edit.guard.size,
                               'sha256':edit.guard.sha256,'replacement':edit.replacement.hex()} for edit in wire]},
              'sourceFiles':{path.name:hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in Path(__file__).parent.iterdir() if path.suffix in ('.py','.json','.txt')}}
    (output/'plan.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'status':report['status'],'output':str(output),'rewrites':len(edits),'stubs':len(unwind),'storageBytes':report['storageBytes'],'deploymentAllowed':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--actors',type=int,choices=(300,500),default=500)
    args=parser.parse_args()
    print(json.dumps(export(args.module,args.executable,args.output,args.actors),indent=2))
