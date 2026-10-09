#include "Coordinator.h"
#include "PrimaryAdmission.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <iomanip>
#include <exception>

namespace bo3::job_startup {
namespace {
#ifdef BO3_JOB_OWNED_TEST
Failure failure{};
std::function<void(HANDLE,bool)> observer;
std::function<void(HANDLE,std::uintptr_t)> primarySetup;
std::function<void(HANDLE)> beforeApply;
#endif
void DebuggerAbsent(HANDLE process) {
    BOOL debugger=TRUE;
    Require(CheckRemoteDebuggerPresent(process,&debugger)!=FALSE && !debugger,"The owned child has a debugger.");
}
void Budget(ULONGLONG deadline){Require(GetTickCount64()<deadline,"The startup transaction exceeded its absolute gate budget.");}
void JsonPath(std::ostream& out,std::wstring_view path) {
    out<<'"';
    for(const auto c:path) {
        if(c==L'\\' || c==L'"')out<<'\\';
        if(c>=32 && c<127)out<<static_cast<char>(c);
        else out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<static_cast<unsigned int>(c)<<std::dec;
    }
    out<<'"';
}
}
#ifdef BO3_JOB_OWNED_TEST
void SetOwnedFailure(Failure value){failure=value;}
void SetOwnedObserver(std::function<void(HANDLE,bool)> value){observer=std::move(value);}
void SetOwnedPrimarySetup(std::function<void(HANDLE,std::uintptr_t)> value){primarySetup=std::move(value);}
void SetOwnedBeforeApply(std::function<void(HANDLE)> value){beforeApply=std::move(value);}
#endif
void Coordinate(late_startup::OwnedChild& child,OwnedJob& job,late_startup::MappedGate& gate,
    const late_startup::PreparePlan& prepare,Receipt& receipt,std::size_t expectedEdits) {
    const auto deadline=GetTickCount64()+child.payload.deadlineMs;
    receipt.processId=child.process.dwProcessId;receipt.primaryThreadId=child.process.dwThreadId;
    receipt.created=child.payload.processCreatedFileTime;receipt.image=job.Identity().image;receipt.jobAssigned=true;
    try {
        receipt.stage="gate-ready";
        job.Verify(child.process.hProcess);child.Resume();child.WaitReady(deadline);
        gate.Admit(child.process.hProcess);receipt.generation=gate.Read(child.process.hProcess).generation;
        receipt.gateBase=gate.Base();gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
        DebuggerAbsent(child.process.hProcess);Budget(deadline);
        receipt.stage="job-freeze";
        receipt.freezeAttempted=true;receipt.freezeStatus=job.Freeze(child.process.hProcess,true);
        Require(receipt.freezeStatus==0,"The job freeze did not return STATUS_SUCCESS.");receipt.frozen=true;
        job.Verify(child.process.hProcess);receipt.membershipVerified=true;
        DebuggerAbsent(child.process.hProcess);gate.Admit(child.process.hProcess);
        gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
        receipt.stage="primary-admission";receipt.patch.imageBase=ImageBase(child.process.hProcess);
#ifdef BO3_JOB_OWNED_TEST
        if(primarySetup)primarySetup(child.process.hProcess,receipt.patch.imageBase);
#endif
        AdmitPrimary(child,gate,receipt);Budget(deadline);
        receipt.patch.stoppedThread=child.process.dwThreadId;
        {
            receipt.stage="plan-preparation";
            auto plan=prepare(child.process.hProcess,receipt.patch.imageBase,receipt.patch);
            Require(plan.edits.size()==expectedEdits && plan.relay,"The complete fixed transaction is required.");
            receipt.helperBase=plan.helperBase;receipt.relay=plan.relay->Address();
            AdmitEditFrames(receipt,plan.edits);job.Verify(child.process.hProcess);
            gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);Budget(deadline);
            try {
                receipt.stage="patch-publication";
                vm_startup::PausedPatch patch(child.process.hProcess,std::move(plan.edits),receipt.patch);
#ifdef BO3_JOB_OWNED_TEST
                if(beforeApply)beforeApply(child.process.hProcess);
#endif
                patch.Apply();
#ifdef BO3_JOB_OWNED_TEST
                if(observer)observer(child.process.hProcess,false);
                Require(failure!=Failure::AfterApply,"Owned rollback request.");
#endif
                gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
                job.Verify(child.process.hProcess);DebuggerAbsent(child.process.hProcess);Budget(deadline);
                patch.Commit();plan.relay->Commit();
                if(plan.commitResources)plan.commitResources();
                receipt.committed=true;
            }catch(...) {
#ifdef BO3_JOB_OWNED_TEST
                if((receipt.patch.rollbackCompleted || beforeApply) && observer)observer(child.process.hProcess,true);
#endif
                throw;
            }
        }
        Budget(deadline);
        receipt.stage="job-thaw";
        receipt.thawAttempted=true;
#ifdef BO3_JOB_OWNED_TEST
        Require(failure!=Failure::Thaw,"Owned thaw refusal.");
#endif
        receipt.thawStatus=job.Freeze(child.process.hProcess,false);
        Require(receipt.thawStatus==0,"The job thaw did not return STATUS_SUCCESS.");receipt.thawed=true;
        job.Verify(child.process.hProcess);DebuggerAbsent(child.process.hProcess);receipt.debuggerAbsent=true;
        receipt.stage="gate-release";
        gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);Budget(deadline);
#ifdef BO3_JOB_OWNED_TEST
        Require(failure!=Failure::Release,"Owned release refusal.");
#endif
        child.Release();receipt.released=true;receipt.stage="released";
    }catch(...) {
        const auto initiating=std::current_exception();
        try {std::rethrow_exception(initiating);}
        catch(const std::exception& error){receipt.refusalReason=std::string(error.what()).substr(0,512);}
        catch(...){receipt.refusalReason="Unknown native startup exception.";}
        // Patch rollback and uncommitted relay destruction completed under the freeze above.
        if(receipt.relay && !receipt.committed) {
            MEMORY_BASIC_INFORMATION memory{};
            receipt.relayFreed=VirtualQueryEx(child.process.hProcess,reinterpret_cast<void*>(receipt.relay),&memory,sizeof(memory))
                ==sizeof(memory) && memory.State==MEM_FREE;
        }
        // Never thaw or release a refused transaction. This also contains failed rollback.
        if(WaitForSingleObject(child.process.hProcess,0)!=WAIT_OBJECT_0) {
            try {job.Kill();receipt.terminated=true;}catch(...) {receipt.cleanupFailed=true;}
        }
        const auto wait=WaitForSingleObject(child.process.hProcess,5000);
        if(wait==WAIT_OBJECT_0 && GetExitCodeProcess(child.process.hProcess,&receipt.patch.exitCode))receipt.patch.exited=true;
        else receipt.cleanupFailed=true;
        std::rethrow_exception(initiating);
    }
}
void WriteReceipt(std::ostream& out,const Receipt& r,std::string_view method) {
    const auto yes=[](bool value){return value?"true":"false";};
    out<<"{\"schema\":1,\"candidate\":\"0.1.0-test.3\",\"startupMethod\":";JsonPath(out,std::wstring(method.begin(),method.end()));
    out
       <<",\"serverTotal\":500001,\"serverUsable\":500000,\"clientTotal\":65000,\"clientRoots\":18,\"stockClientRoots\":8,\"migrationBufferBytes\":33554432"
       <<",\"processId\":"<<r.processId<<",\"processCreatedFileTime\":"<<r.created<<",\"primaryThreadId\":"<<r.primaryThreadId
       <<",\"imagePath\":";JsonPath(out,r.image);
    out<<",\"executableSha256\":\""<<r.gameSha256<<"\",\"helperSha256\":\""<<kHelperHash<<"\",\"gateSha256\":\""<<kGateHash<<'"'
       <<",\"generation\":"<<r.generation<<",\"imageBase\":"<<r.patch.imageBase<<",\"helperBase\":"<<r.helperBase<<",\"gateBase\":"<<r.gateBase
       <<",\"jobOwned\":"<<yes(r.jobAssigned)<<",\"jobParentOnly\":true,\"killOnJobClose\":true"
       <<",\"freezeAttempted\":"<<yes(r.freezeAttempted)<<",\"freezeStatus\":"<<r.freezeStatus<<",\"frozenForTransaction\":"<<yes(r.frozen)
       <<",\"jobMembershipVerified\":"<<yes(r.membershipVerified)<<",\"threadsObserved\":"<<r.threadsObserved<<",\"primaryPc\":"<<r.primaryPc
       <<",\"primaryOnlyAdmitted\":"<<yes(r.primaryAdmitted)<<",\"thawAttempted\":"<<yes(r.thawAttempted)<<",\"thawStatus\":"<<r.thawStatus
       <<",\"thawed\":"<<yes(r.thawed)<<",\"editsWritten\":"<<r.patch.editsWritten<<",\"rollbackCompleted\":"<<yes(r.patch.rollbackCompleted)
       <<",\"relay\":"<<r.relay<<",\"relayFreed\":"<<yes(r.relayFreed)<<",\"committed\":"<<yes(r.committed)
       <<",\"debuggerAbsent\":"<<yes(r.debuggerAbsent)<<",\"released\":"<<yes(r.released)<<",\"terminated\":"<<yes(r.terminated)
       <<",\"cleanupFailed\":"<<yes(r.cleanupFailed)<<",\"exited\":"<<yes(r.patch.exited)<<",\"exitCode\":"<<r.patch.exitCode
       <<",\"stage\":";JsonPath(out,std::wstring(r.stage.begin(),r.stage.end()));
    out<<",\"refusalReason\":";JsonPath(out,std::wstring(r.refusalReason.begin(),r.refusalReason.end()));
    out<<",\"unwindReason\":";JsonPath(out,std::wstring(r.unwindReason.begin(),r.unwindReason.end()));
    out<<",\"unwindLookupPc\":"<<r.unwindLookupPc<<",\"runtimeMetadataReads\":"<<r.runtimeMetadataReads
       <<",\"runtimeMetadataMask\":"<<r.runtimeMetadataMask
       <<",\"attached\":false,\"detached\":false,\"liveAllocationValidated\":false,\"debugRegisterWrites\":0,\"frames\":[";
    bool first=true;for(const auto pc:r.frames){if(!first)out<<',';first=false;out<<pc;}
    out<<"],\"threadObservations\":[";first=true;
    for(const auto& row:r.threads){if(!first)out<<',';first=false;
        out<<"{\"threadId\":"<<row.id<<",\"pc\":"<<row.pc<<",\"start\":"<<row.start<<'}';}
    out<<"]}";Require(out.good(),"Cannot write the job startup receipt.");
}
}
