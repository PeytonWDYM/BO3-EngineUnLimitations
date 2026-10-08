"""Export exact table rewrites into a new private evidence directory. No deployment."""

import argparse
import hashlib
import json
from pathlib import Path

from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from table_plan import CapturedCode, prepare
from storage_plan import StorageLayout


def export(module: Path, output: Path):
    output = output.resolve()
    lab = (Path.home()/'.codex/labs/bo3-engine').resolve()
    if lab not in output.parents or output.exists():
        raise ValueError('Use a new output directory inside the private BO3 lab.')
    code = CapturedCode(module)
    layout = TableLayout(NativeSentientAddress(code.base+0x21000000),ExternalTableAddress(code.base+0x22000000))
    plan = prepare(code,layout,code.base+0x20000000,StorageLayout(code.base+0x23000000,code.base+0x24000000,code.base+0x25000000,code.base+0x26000000))
    output.mkdir(parents=True)
    rewrites = []
    for index,edit in enumerate(plan.rewrites):
        item = {'name':edit.name,'rva':hex(edit.guard.rva),'size':edit.guard.size,
                'sha256':edit.guard.sha256,'replacement':edit.replacement.hex(),'ownerRegister':edit.owner_register}
        if edit.stub_address is not None:
            filename = f'stub-{index:03d}.bin'
            (output/filename).write_bytes(edit.stub)
            item.update({'stubAddress':hex(edit.stub_address),'stubFile':filename,
                         'stubSha256':hashlib.sha256(edit.stub).hexdigest()})
        rewrites.append(item)
    report = {'status':'guarded_owned_replay_plan_not_deployable','coverageComplete':False,
              'capacity200Implemented':False,'addressSpace':'captured_unpacked_module_va',
              'nativePool':hex(layout.native_pool),'externalTable':hex(layout.external_table),
              'capacity':layout.capacity,'nativeRecordBytes':0x3088,'tableEntryBytes':0x48,
              'tableBytes':layout.table_bytes,'directConsumerStubs':len(plan.member_bindings),
              'indexedWordTable':{'address':hex(plan.word_table.external_table),'entryBytes':2,'bytes':plan.word_table.table_bytes},
              'storageRegions':[{'address':hex(start),'bytes':size} for start,size in plan.storage.regions(layout)],
              'rewrites':rewrites,
              'unwindRequirements':{'accessor':'Register ALLOC_SMALL 16 for its four-byte prolog.',
                                    'memberAndLifecycleStubs':'Register stack operations and chain the exact native owner unwind record. Native-frame continuation cannot use a leaf unwind record.'},
              'activationGates':['Exclude remaining unclassified folded/leaf consumers and actor-indexed arrays/fields.',
                                 'Admit stock-save framing and host migration before expanded load counts.',
                                 'Verify AAE consumers, retained references and pre-constructor activation.',
                                 'Implement and verify native unwind registration and atomic rollback.']}
    (output/'plan.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'output':str(output),'directConsumerStubs':len(plan.member_bindings),'rewrites':len(rewrites),'deploymentAllowed':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.module,args.output),indent=2))
