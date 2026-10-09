#include "Coordinator.h"
#include "../job_startup/PrimaryAdmission.h"
#include "../preentry/Identity.h"
#include <exception>

namespace bo3::job_control {
namespace {
void NoDebugger(HANDLE process) {
    BOOL attached=TRUE;
    Require(CheckRemoteDebuggerPresent(process,&attached)!=FALSE && !attached,"The job control child has a debugger.");
}
void Budget(ULONGLONG deadline){Require(GetTickCount64()<deadline,"The stock job control exceeded its absolute gate budget.");}
void RecordPhase(Receipt& receipt,const char* name){receipt.phases.push_back({name,GetTickCount64()});receipt.native.stage=name;}
#ifdef BO3_JOB_OWNED_TEST
Failure failure{};
std::function<std::uintptr_t(HANDLE,std::uintptr_t)> setup;
#endif
}
#ifdef BO3_JOB_OWNED_TEST
void SetOwnedFailure(Failure value){failure=value;}
void SetOwnedSetup(std::function<std::uintptr_t(HANDLE,std::uintptr_t)> value){setup=std::move(value);}
#endif
Admitted Coordinate(late_startup::OwnedChild& child,job_startup::OwnedJob& job,late_startup::MappedGate& gate,
    enhanced::MappedHelper& helper,const std::filesystem::path& helperFile,Receipt& receipt) {
    auto& row=receipt.native;const auto deadline=GetTickCount64()+child.payload.deadlineMs;
    row.processId=child.process.dwProcessId;row.primaryThreadId=child.process.dwThreadId;
    row.created=child.payload.processCreatedFileTime;row.image=job.Identity().image;row.jobAssigned=true;
    try {
        job.Verify(child.process.hProcess);RecordPhase(receipt,"resume");child.Resume();child.WaitReady(deadline);RecordPhase(receipt,"gate-ready");
        gate.Admit(child.process.hProcess);row.generation=gate.Read(child.process.hProcess).generation;row.gateBase=gate.Base();
        gate.VerifyWaiting(child.process.hProcess,child.payload,row.generation);NoDebugger(child.process.hProcess);Budget(deadline);
        RecordPhase(receipt,"freeze-start");row.freezeAttempted=true;row.freezeStatus=job.Freeze(child.process.hProcess,true);
        Require(row.freezeStatus==0,"The job control freeze did not return STATUS_SUCCESS.");row.frozen=true;RecordPhase(receipt,"freeze-end");
        job.Verify(child.process.hProcess);row.membershipVerified=true;NoDebugger(child.process.hProcess);gate.Admit(child.process.hProcess);
        gate.VerifyWaiting(child.process.hProcess,child.payload,row.generation);row.patch.imageBase=job_startup::ImageBase(child.process.hProcess);
        auto image=row.patch.imageBase;
#ifdef BO3_JOB_OWNED_TEST
        if(setup)image=setup(child.process.hProcess,image);
#endif
        RecordPhase(receipt,"primary-start");job_startup::AdmitPrimary(child,gate,row);RecordPhase(receipt,"primary-end");Budget(deadline);
        RecordPhase(receipt,"stock-start");late_startup::ControlReceipt stock;
        late_startup::AdmitStockControl(child.process.hProcess,image,helper,helperFile,stock);row.helperBase=helper.image.base;
        auto originals=StockOriginals(image,helper);VerifyOriginals(child.process.hProcess,originals);
        std::vector<vm_startup::AddressEdit> spans;
        for(const auto& original:originals)spans.push_back({original.address,original.bytes,{}});
        job_startup::AdmitEditFrames(row,spans);
        receipt.originalsObserved=static_cast<DWORD>(originals.size());receipt.originalsVerified=true;
        receipt.bindingsUnchanged=true;receipt.stockAdmitted=true;
        auto frozen=Capture(child.process.hProcess,image,originals,"frozen");RecordPhase(receipt,"stock-end");Budget(deadline);
        job.Verify(child.process.hProcess);gate.VerifyWaiting(child.process.hProcess,child.payload,row.generation);NoDebugger(child.process.hProcess);
        RecordPhase(receipt,"thaw-start");row.thawAttempted=true;
#ifdef BO3_JOB_OWNED_TEST
        Require(failure!=Failure::Thaw,"Owned stock thaw refusal.");
#endif
        row.thawStatus=job.Freeze(child.process.hProcess,false);
        Require(row.thawStatus==0,"The job control thaw did not return STATUS_SUCCESS.");row.thawed=true;RecordPhase(receipt,"thaw-end");
        job.Verify(child.process.hProcess);NoDebugger(child.process.hProcess);row.debuggerAbsent=true;
        gate.VerifyWaiting(child.process.hProcess,child.payload,row.generation);Budget(deadline);
#ifdef BO3_JOB_OWNED_TEST
        Require(failure!=Failure::Release,"Owned stock release refusal.");
#endif
        child.Release();row.released=true;RecordPhase(receipt,"released");return {std::move(originals),std::move(frozen),image};
    }catch(...) {
        const auto original=std::current_exception();
        try {std::rethrow_exception(original);}catch(const std::exception& error){row.refusalReason=std::string(error.what()).substr(0,512);}
        catch(...){row.refusalReason="Unknown stock job control exception.";}
        if(WaitForSingleObject(child.process.hProcess,0)!=WAIT_OBJECT_0) {
            try {job.Kill();row.terminated=true;}catch(...){row.cleanupFailed=true;}
        }
        if(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0 && GetExitCodeProcess(child.process.hProcess,&receipt.exitCode))
            receipt.exited=true;
        else row.cleanupFailed=true;
        std::rethrow_exception(original);
    }
}
}

