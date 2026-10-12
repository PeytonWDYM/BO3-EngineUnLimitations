"""Export a disabled actor preparation plan into a new private lab directory."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from captured_code import CapturedCode, MANIFEST_SHA256,Rewrite
from table_layout import TableLayout, NativeSentientAddress, ExternalTableAddress
from table_plan import prepare, ACTIVATION_GATES
from storage_plan import StorageLayout
from omissions import omission_inventory
from unwind import requirements
from shape import ActorShape
from actor_wire import prepare_actor_wire
from client_snapshots import ClientSnapshots,prepare_client_snapshots
from client_snapshot_reset import prepare_client_snapshot_resets
from client_reset_frames import emit_client_reset_frames
from client_actors import ClientActors,prepare_client_actors,ACTOR_BANK_OFFSET
from client_allocator import prepare_client_allocation
from client_actor_ring import prepare_client_actor_ring,RING_RECORDS


def export_rewrites(output: Path,prefix: str,rewrites: tuple[Rewrite,...]) -> list[dict]:
    edits=[]
    for index,edit in enumerate(rewrites):
        item={'name':edit.name,'rva':hex(edit.guard.rva),'size':edit.guard.size,'sha256':edit.guard.sha256,
              'replacement':edit.replacement.hex(),'ownerRegister':edit.owner_register}
        if edit.stub:
            filename=f'{prefix}-{index:03d}.bin'
            (output/filename).write_bytes(edit.stub)
            item.update(stubAddress=hex(edit.stub_address),stubFile=filename,stubSha256=hashlib.sha256(edit.stub).hexdigest())
        edits.append(item)
    return edits


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
    snapshots = ClientSnapshots(code.base+0x2E000000,layout.shape)
    snapshot_edits = prepare_client_snapshots(code,snapshots,code.base+0x201C0000)
    snapshot_unwind = requirements(code,snapshot_edits)
    snapshot_resets = prepare_client_snapshot_resets(code,snapshots,code.base+0x201D0000)
    reset_assembly = emit_client_reset_frames(snapshot_resets)
    # The owned root models the preserved native return. Runtime provider and caller admission remain required.
    client_root=code.base+0x30000000
    client_actors = ClientActors(client_root,client_root+ACTOR_BANK_OFFSET,layout.shape)
    client_actor_edits = prepare_client_actors(code,client_actors)
    client_allocation = (prepare_client_allocation(code,code.base+0x201E0000),)
    allocation_unwind = requirements(code,client_allocation)
    client_ring = prepare_client_actor_ring(code,layout.shape)
    output.mkdir(parents=True)
    edits = export_rewrites(output,'stub',plan.rewrites)
    client_edits = export_rewrites(output,'snapshot-stub',snapshot_edits)
    reset_edits = export_rewrites(output,'snapshot-reset',tuple(frame.rewrite for frame in snapshot_resets))
    client_actor_report = export_rewrites(output,'client-actor',client_actor_edits)
    allocation_report = export_rewrites(output,'client-allocation',client_allocation)
    ring_report = export_rewrites(output,'client-ring',client_ring)
    template_file = output/'ClientResetTemplates.asm'
    template_file.write_text(reset_assembly,encoding='ascii')
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
              'clientSnapshotPreparation':{'deploymentAllowed':False,'storageAddress':hex(snapshots.base),
                  'localClients':2,'snapshotsPerLocalClient':2,'snapshotBytes':snapshots.snapshot_bytes,
                  'actorOffset':snapshots.actor_offset,'actorRecordBytes':80,'storageBytes':snapshots.total_bytes,
                  'rewrites':client_edits,'unwindRequirements':snapshot_unwind,
                  'resetPreparation':{'deploymentAllowed':False,'rewrites':reset_edits,
                      'staticTemplateFile':template_file.name,'staticTemplateSha256':hashlib.sha256(template_file.read_bytes()).hexdigest(),
                      'staticPEFrames':[{'stubAddress':hex(frame.rewrite.stub_address),'codeBytes':len(frame.rewrite.stub),
                                        'unwindInfo':frame.unwind.hex(),'gameBindingVerified':False} for frame in snapshot_resets]}},
              'clientActorPreparation':{'deploymentAllowed':False,'nativeRootVerified':False,
                  'nativeRootKind':'preserved_native_allocation_return','nativeRootAddress':hex(client_actors.native_base),
                  'storageAddress':hex(client_actors.base),'storageBytes':client_actors.total_bytes,
                  'clientStride':client_actors.client_stride,'localClients':2,'actorsPerLocalClient':actors,
                  'actorRecordBytes':0xB00,'nativeActorOffset':client_actors.actor_offset,
                  'rewrites':client_actor_report,
                  'allocationPreparation':{'deploymentAllowed':False,'nativeProviderVerified':False,
                      'localClientCounts':[1,2],'additionalBytes':ACTOR_BANK_OFFSET,
                      'rewrites':allocation_report,'unwindRequirements':allocation_unwind}},
              'clientActorRingPreparation':{'deploymentAllowed':False,'gameBindingVerified':False,
                  'records':RING_RECORDS,'actorRecordBytes':80,'retainedSnapshots':16,
                  'storageBytesPerLocalClient':RING_RECORDS*80,'additionalBytesPerLocalClient':(RING_RECORDS-1024)*80,
                  'storageProvider':'native_two_pass_hunk','adjacentCapacity':1024,'rewrites':ring_report},
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
