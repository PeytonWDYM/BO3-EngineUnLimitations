#include "Coordinator.h"
#include "../job_startup/PrimaryAdmission.h"
#include "../late_startup/ControlAdmission.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include <iomanip>
#include <exception>

namespace bo3::bindings_control {
namespace {
#ifdef BO3_JOB_OWNED_TEST
Failure failure{};
std::function<void(HANDLE,const Selected&,Phase)> observer;
std::function<std::uintptr_t(HANDLE,std::uintptr_t)> setup;
#endif
void DebuggerAbsent(HANDLE process) {
    BOOL debugger=TRUE;
    Require(CheckRemoteDebuggerPresent(process,&debugger)!=FALSE && !debugger,"The owned child has a debugger.");
}
void Budget(ULONGLONG deadline){Require(GetTickCount64()<deadline,"The startup transaction exceeded its absolute gate budget.");}

}
#ifdef BO3_JOB_OWNED_TEST
void SetOwnedFailure(Failure value){failure=value;}
void SetOwnedObserver(std::function<void(HANDLE,const Selected&,Phase)> value){observer=std::move(value);}
void SetOwnedSetup(std::function<std::uintptr_t(HANDLE,std::uintptr_t)> value){setup=std::move(value);}
#endif
void Coordinate(late_startup::OwnedChild& child,job_startup::OwnedJob& job,late_startup::MappedGate& gate,
    enhanced::MappedHelper& helper,const std::filesystem::path& helperFile,Receipt& result) {
    auto& receipt=result.native;const auto deadline=GetTickCount64()+child.payload.deadlineMs;
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
        receipt.stage="primary-admission";receipt.patch.imageBase=job_startup::ImageBase(child.process.hProcess);
        auto image=receipt.patch.imageBase;
#ifdef BO3_JOB_OWNED_TEST
        if(setup)image=setup(child.process.hProcess,image);
#endif
        job_startup::AdmitPrimary(child,gate,receipt);Budget(deadline);
        receipt.patch.stoppedThread=child.process.dwThreadId;
        {
            receipt.stage="plan-preparation";
            late_startup::ControlReceipt stock;
            late_startup::AdmitStockControl(child.process.hProcess,image,helper,helperFile,stock);result.stockAdmitted=true;
            auto plan=late_startup::PrepareFixedPlan(child.process.hProcess,image,helper,helperFile);
            Require(plan.edits.size()==42 && plan.relay,"The complete fixed transaction is required.");
            receipt.helperBase=plan.helperBase;receipt.relay=plan.relay->Address();
            job_startup::AdmitEditFrames(receipt,plan.edits);
            const auto selected=Select(plan,image,helper);
            Capture(child.process.hProcess,selected,helper,result.proof,false);job.Verify(child.process.hProcess);
            gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);Budget(deadline);
#ifdef BO3_JOB_OWNED_TEST
            if(observer)observer(child.process.hProcess,selected,Phase::Prepared);
#endif
            try {
                receipt.stage="patch-publication";
                vm_startup::PausedPatch patch(child.process.hProcess,selected.publications,receipt.patch);
                patch.Apply();
                Capture(child.process.hProcess,selected,helper,result.proof,true);result.stockVerified=true;
#ifdef BO3_JOB_OWNED_TEST
                if(observer)observer(child.process.hProcess,selected,Phase::Published);
                Require(failure!=Failure::AfterApply,"Owned rollback request.");
#endif
                gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
                job.Verify(child.process.hProcess);DebuggerAbsent(child.process.hProcess);Budget(deadline);
                patch.Commit();plan.relay->Commit();receipt.committed=true;
            }catch(...) {
#ifdef BO3_JOB_OWNED_TEST
                if(receipt.patch.rollbackCompleted && observer)observer(child.process.hProcess,selected,Phase::RolledBack);
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
        child.Release();receipt.released=true;receipt.stage="released";result.releasedTick=GetTickCount64();
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
}
