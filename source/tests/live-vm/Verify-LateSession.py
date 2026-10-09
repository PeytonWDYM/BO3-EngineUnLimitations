"""Native E2E for exact-process late receipts using the unchanged owned pool fixture."""
import argparse
import copy
import ctypes
from ctypes import wintypes
import hashlib
import importlib.util
import json
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
source=REPO/'source/tests/vm/Verify-EnhancedSession.py'
spec=importlib.util.spec_from_file_location('owned_enhanced_e2e',source)
owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
from enhanced_session import resolve_enhanced_session,verify_code_evidence
from profile import validate
from snapshot import sample
from windows_process import VerifiedProcess,kernel,require

class Tracked(owned.ReadTracking):
    def __init__(self,verified):
        super().__init__(verified);self.on_read=None
    def read(self,address,size):
        data=super().read(address,size)
        if self.on_read:
            callback=self.on_read;self.on_read=None;callback()
        return data

def primary_thread(pid):
    class Entry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('id',wintypes.DWORD),('owner',wintypes.DWORD),
                  ('basePriority',wintypes.LONG),('deltaPriority',wintypes.LONG),('flags',wintypes.DWORD)]
    for name in ('Thread32First','Thread32Next'):
        call=getattr(kernel,name);call.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];call.restype=wintypes.BOOL
    handle=kernel.CreateToolhelp32Snapshot(4,0);require(handle not in (None,wintypes.HANDLE(-1).value),'CreateToolhelp32Snapshot')
    try:
        entry=Entry();entry.size=ctypes.sizeof(entry);require(kernel.Thread32First(handle,ctypes.byref(entry)),'Thread32First')
        while True:
            if entry.owner==pid:return entry.id
            if not kernel.Thread32Next(handle,ctypes.byref(entry)):raise AssertionError('Owned primary thread absent')
    finally:kernel.CloseHandle(handle)

def late_receipt(process,ready):
    legacy=owned.receipt_for(process,ready)
    for name in ('status','activated','exited'):legacy.pop(name)
    # The fixture receipt tests schema only. It does not claim an actual late attach transaction.
    thread=primary_thread(process.pid)
    return legacy|{'startupMethod':'late-crt-gate','attached':True,'committed':True,'detached':True,
                  'debuggerAbsent':True,'released':True,'terminated':False,'debugRegisterWrites':0,
                  'liveAllocationValidated':False,'generation':1,'primaryThreadId':thread,'attachThread':thread,
                  'writeEventThread':thread,'threadsObserved':2,'gateBase':ready['helperBase'],
                  'attachBreakpoint':ready['helperBase']+1,'attachThreadEntry':ready['helperBase']+2}

def main():
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve();assert not output.is_relative_to(REPO)
    profile,sites=owned.profile_for(a.fixture);cases=[]
    def refuses(name,operation,process):
        process.read_sizes.clear()
        try:operation()
        except (ValueError,OSError,KeyError,TypeError) as error:
            assert not any(n>=65000*64 for n in process.read_sizes),'Refusal read an expanded pool'
            cases.append({'name':name,'passed':True,'refused':str(error),'readSizes':process.read_sizes.copy()})
        else:raise AssertionError('Missing refusal: '+name)
    for mode in ('stock','enhanced'):
        with owned.child(a.fixture,mode) as (native,ready),VerifiedProcess(native.pid,profile) as verified:
            process=Tracked(verified);directory=output/mode/'sessions';directory.mkdir(parents=True)
            stem=f'{process.started_ticks}-{process.pid}';legacy_path=directory/(stem+'.json');path=directory/(stem+'-late.json')
            receipt=late_receipt(process,ready)
            enroll=lambda:resolve_enhanced_session(process,profile,directory,capacity_sites=sites)
            assert enroll() is None and validate(profile)[0].capacity==130000
            cases.append({'name':mode+'-missing-receipts','passed':True})
            stale=directory/(f'{process.started_ticks+1}-{process.pid}-late.json');stale.write_text(json.dumps(receipt))
            assert enroll() is None;cases.append({'name':mode+'-stale-late-name','passed':True});stale.unlink()
            path.write_text(json.dumps(receipt))
            if mode=='stock':
                refuses('stock-forged-late-receipt',enroll,process);continue
            changes=(('schema-bool',{'schema':True}),('candidate',{'candidate':'wrong'}),('method',{'startupMethod':'wrong'}),
                ('pid',{'processId':process.pid+1}),('filetime',{'processCreatedFileTime':process.started_ticks+1}),
                ('image',{'imageBase':process.module.baseaddress+4096}),('helper',{'helperBase':ready['helperBase']+4096}),
                ('server',{'serverTotal':1000001}),('client',{'clientTotal':500001}),('roots',{'clientRoots':8}),
                ('stock-roots',{'stockClientRoots':18}),('migration',{'migrationBufferBytes':1}),('edits',{'editsWritten':41}),
                ('attached',{'attached':False}),('committed',{'committed':False}),('detached',{'detached':False}),
                ('debugger-present',{'debuggerAbsent':False}),('released',{'released':False}),('terminated',{'terminated':True}),
                ('rollback',{'rollbackCompleted':True}),('dr-written',{'debugRegisterWrites':1}),('dr-bool',{'debugRegisterWrites':False}),
                ('committed-int',{'committed':1}),('live-allocation-claimed',{'liveAllocationValidated':True}),
                ('generation',{'generation':2}),('generation-bool',{'generation':True}),('primary-thread-zero',{'primaryThreadId':0}),
                ('attach-thread-overflow',{'attachThread':1<<32}),('write-thread-mismatch',{'writeEventThread':receipt['attachThread']+1}),
                ('gate-zero',{'gateBase':0}),('breakpoint-bool',{'attachBreakpoint':True}),('entry-overflow',{'attachThreadEntry':1<<64}),
                ('thread-count-one',{'threadsObserved':1}),('thread-count-overflow',{'threadsObserved':1<<32}))
            for name,change in changes:
                path.write_text(json.dumps(receipt|change));refuses('late-'+name,enroll,process)
            for missing in ('released','debugRegisterWrites','liveAllocationValidated','generation','attachThreadEntry'):
                changed=receipt.copy();changed.pop(missing);path.write_text(json.dumps(changed));refuses('late-missing-'+missing,enroll,process)
            for name,data in (('truncated',b'{'),('non-object',b'[]'),('oversize',b' '*16385)):
                path.write_bytes(data);refuses('late-'+name,enroll,process)
            path.write_text(json.dumps(receipt));legacy_path.write_text(json.dumps(owned.receipt_for(process,ready)))
            refuses('both-valid-routes',enroll,process)
            path.write_text('{');refuses('invalid-late-with-valid-legacy',enroll,process)
            path.unlink()
            legacy=resolve_enhanced_session(process,profile,directory,capacity_sites=sites)
            verify_code_evidence(process,profile,legacy);assert validate(profile,enhanced_session=legacy)[0].capacity==500001
            cases.append({'name':'legacy-route-preserved','passed':True});legacy_path.unlink()
            path.write_text(json.dumps(receipt))
            wrong=copy.deepcopy(profile);wrong['enhancedHelper']['sha256']='0'*64
            refuses('late-wrong-helper-hash',lambda:resolve_enhanced_session(process,wrong,directory,capacity_sites=sites),process)
            process.on_read=lambda:path.write_text(json.dumps(receipt|{'committed':False}))
            refuses('receipt-changes-during-enrollment',enroll,process);path.write_text(json.dumps(receipt))
            process.on_read=lambda:legacy_path.write_text(json.dumps(owned.receipt_for(process,ready)))
            refuses('second-route-during-enrollment',enroll,process);legacy_path.unlink()
            enrollment=enroll();verify_code_evidence(process,profile,enrollment)
            instances=validate(profile,enhanced_session=enrollment);process.read_sizes.clear()
            reports,error,attempts=sample(process,profile,instances,1)
            assert error is None and reports[0]['capacity']==500001 and reports[0]['usableCapacity']==500000
            assert reports[0]['allocated']==3 and reports[0]['free']==499997 and reports[1]['capacity']==65000
            cases.append({'name':'late-real-sample','passed':True,'pid':process.pid,'filetime':process.started_ticks,
                          'liveAllocationValidated':False,'attempts':attempts,'instances':reports,'readSizes':process.read_sizes.copy()})
            (output/'profile.json').write_text(json.dumps(profile,indent=2));(output/'session.json').write_text(json.dumps(receipt,indent=2))
            legacy_path.write_text(json.dumps(owned.receipt_for(process,ready)))
            refuses('second-route-before-verification',lambda:verify_code_evidence(process,profile,enrollment),process);legacy_path.unlink()
            process.on_read=lambda:legacy_path.write_text(json.dumps(owned.receipt_for(process,ready)))
            refuses('second-route-during-verification',lambda:verify_code_evidence(process,profile,enrollment),process);legacy_path.unlink()
            path.rename(legacy_path)
            refuses('enrolled-route-replaced',lambda:verify_code_evidence(process,profile,enrollment),process);legacy_path.rename(path)
            refuses('receipt-not-enrollment',lambda:validate(profile,enhanced_session=receipt),process)
            edited=copy.deepcopy(profile);edited['instances'][0]['capacity']=500001
            refuses('profile-only-expansion',lambda:validate(edited),process)
            native.stdin.write('stop\n');native.stdin.flush();native.wait(timeout=10)
            refuses('exited-enrollment',lambda:validate(profile,enhanced_session=enrollment),process)
    for mutation in ('partial','opcode','binding','unreadable'):
        with owned.child(a.fixture,'enhanced') as (native,ready),VerifiedProcess(native.pid,profile) as verified:
            process=Tracked(verified);directory=output/mutation/'sessions';directory.mkdir(parents=True)
            (directory/f'{process.started_ticks}-{process.pid}-late.json').write_text(json.dumps(late_receipt(process,ready)))
            owned.mutate(native,mutation)
            refuses('late-runtime-'+mutation,lambda:resolve_enhanced_session(process,profile,directory,capacity_sites=sites),process)
    files=[REPO/'source/live/vm/enhanced_session.py',REPO/'source/live/vm/profile.py',REPO/'source/live/vm/snapshot.py',
           REPO/'source/live/windows_process.py',source]+list(Path(__file__).parent.glob('*'))
    report={'scope':'Owned late receipt enrollment E2E only. No BO3 launch. Refusals perform no expanded pool reads.',
            'caseCount':len(cases),'cases':cases,'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()},
            'fixtureSha256':hashlib.sha256(a.fixture.read_bytes()).hexdigest(),'helperSha256':profile['enhancedHelper']['sha256']}
    (output/'result.json').write_text(json.dumps(report,indent=2));print(f'{len(cases)} late enrollment native cases passed.')

if __name__=='__main__':main()
