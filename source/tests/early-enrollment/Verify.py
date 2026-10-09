"""Read-only early checksum enrollment against a retained authored Windows process."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import pefile

REPO=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('owned_job',REPO/'source/tests/job-enrollment/Verify.py')
job=importlib.util.module_from_spec(spec);spec.loader.exec_module(job)
owned,late=job.owned,job.late
from enhanced_session import resolve_enhanced_session,verify_code_evidence
from profile import validate
from snapshot import sample
from windows_process import ACCESS_MASK,VerifiedProcess

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    assert not output.is_relative_to(REPO)
    output.mkdir(parents=True,exist_ok=False)
    profile,capacity=owned.profile_for(args.fixture)
    pe=pefile.PE(str(args.fixture));exports={e.name.decode():e.address for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    sites=[{'leaRva':exports['earlySites']+i*16,'chainDestinationRva':exports['earlySites']+i*16+8,
            'expectedTableSlot':64,'computedLocalSlot':68} for i in range(1069)]
    inventory=output/'owned-early-profile.json'
    manifest={'executableSha256':profile['sha256'],'timestamp':profile['timestamp'],'imageSize':profile['imageSize'],
              'siteCount':1069,'publicationCount':1079,'arenaSize':36864,'relayStride':32,'sites':sites}
    inventory.write_text(json.dumps(manifest),encoding='utf-8')
    digest=hashlib.sha256(inventory.read_bytes()).hexdigest();profile['earlyChecksumFixtureSha256']=digest
    original=bytes.fromhex('488d15')+struct.pack('<i',1)
    profile['codeEvidence'].append({'startRva':hex(exports['earlySites']),'endRva':hex(exports['earlySites']+7),
                                    'sha256':hashlib.sha256(original).hexdigest()})
    cases=[]
    def refuses(name,operation,process):
        process.read_sizes.clear()
        try:operation()
        except (ValueError,OSError,KeyError,TypeError) as error:
            assert not any(n>=65000*64 for n in process.read_sizes),'Refusal read a pool'
            cases.append({'name':name,'passed':True,'reason':str(error)})
        else:raise AssertionError('Missing refusal: '+name)
    for mode in ('stock','enhanced'):
        with owned.child(args.fixture,mode) as (native,ready),VerifiedProcess(native.pid,profile) as verified:
            process=late.Tracked(verified);directory=output/mode;directory.mkdir()
            path=directory/f'{process.started_ticks}-{process.pid}-job.json'
            enroll=lambda:resolve_enhanced_session(process,profile,directory,capacity_sites=capacity,early_checksum_profile=inventory)
            assert enroll() is None and validate(profile)[0].capacity==130000
            receipt=job.job_receipt(process,ready)|{'startupMethod':'late-crt-job-freeze-early-checksum','editsWritten':1121,
                'helperSha256':profile['enhancedHelper']['sha256'],
                'earlyChecksumProfile':digest,'checksumAdmitted':True,'checksumSitesRequired':1069,'checksumEditsPrepared':1079,
                'checksumArena':ready['arena'],'checksumArenaBytes':36864,'nativeEditsRequired':42,'combinedEditsRequired':1121,
                'checksumReapplication':False,'aaeStoreSitesPreserved':True,'jobParentOnly':True,'killOnJobClose':True,
                'freezeAttempted':True,'thawAttempted':True,'cleanupFailed':False,'relayFreed':False,'runtimeMetadataMask':3,
                'runtimeMetadataReads':4,'stage':'released','refusalReason':'','unwindReason':'','executableSha256':process.sha256,
                'imagePath':str(process.path),'primaryPc':process.module.baseaddress+1,'relay':ready['arena'],
                'frames':[process.module.baseaddress+1],'threadObservations':[{'threadId':late.primary_thread(process.pid),
                'pc':process.module.baseaddress+1,'start':process.module.baseaddress+1}]}
            path.write_text(json.dumps(receipt))
            if mode=='stock':refuses('stock-forged-receipt',enroll,process);continue
            for name,changed in [('committed',False),('editsWritten',1120),('startupMethod','late-crt-job-freeze'),
                ('processCreatedFileTime',process.started_ticks+1),('checksumSitesRequired',1068),('checksumArenaBytes',36863)]:
                bad=copy.deepcopy(receipt);bad[name]=changed;path.write_text(json.dumps(bad));refuses('receipt-'+name,enroll,process)
            path.write_text(json.dumps(receipt));enrollment=enroll();assert enrollment is not None
            verify_code_evidence(process,profile,enrollment)
            instances=validate(profile,enhanced_session=enrollment);assert [i.capacity for i in instances]==[500001,65000]
            reports,error,_=sample(process,profile,instances,2,enhanced_session=enrollment)
            assert not error and reports[0]['usableCapacity']==500000 and reports[0]['free']==499997
            (output/'accepted-pools.json').write_text(json.dumps(reports,indent=2))
            cases.append({'name':'early-native-enrollment-and-500k-reuse-chain','passed':True})
            bad=copy.deepcopy(receipt);bad['checksumArena']+=32;path.write_text(json.dumps(bad))
            refuses('changed-receipt-after-enrollment',lambda:enrollment.authorize(profile,process),process)
            path.write_text(json.dumps(receipt))
            duplicate=directory/f'{process.started_ticks}-{process.pid}-late.json';duplicate.write_text(json.dumps(receipt))
            refuses('ambiguous-route',enroll,process);assert process.read_sizes==[];duplicate.unlink()
    for command in ('source','relay','padding','partial','binding','boot','unreadable'):
        with owned.child(args.fixture,'enhanced') as (native,ready),VerifiedProcess(native.pid,profile) as verified:
            process=late.Tracked(verified);directory=output/command;directory.mkdir()
            current=copy.deepcopy(receipt);current.update(processId=process.pid,processCreatedFileTime=process.started_ticks,
                imageBase=process.module.baseaddress,helperBase=ready['helperBase'],checksumArena=ready['arena'],relay=ready['arena'],
                primaryThreadId=late.primary_thread(process.pid),primaryPc=process.module.baseaddress+1,frames=[process.module.baseaddress+1],
                threadObservations=[{'threadId':late.primary_thread(process.pid),'pc':process.module.baseaddress+1,'start':process.module.baseaddress+1}])
            path=directory/f'{process.started_ticks}-{process.pid}-job.json';path.write_text(json.dumps(current))
            enroll=lambda:resolve_enhanced_session(process,profile,directory,capacity_sites=capacity,early_checksum_profile=inventory)
            enrollment=enroll();native.stdin.write(command+'\n');native.stdin.flush();assert native.stdout.readline().strip()=='changed'
            refuses(command+'-enrollment',enroll,process)
            refuses(command+'-after-enrollment',lambda:enrollment.authorize(profile,process),process)
    result={'passed':True,'cases':cases,'accessMask':hex(ACCESS_MASK),'gameExecuted':False,
        'scope':'Authored native success fields and data-only hook bytes; read-only enrollment, not a BO3 startup proof.',
        'sources':{str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__),REPO/'source/live/vm/early_checksum_evidence.py',REPO/'source/live/vm/enhanced_session.py']}}
    (output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({'passed':True,'cases':len(cases)}))
if __name__=='__main__':main()
