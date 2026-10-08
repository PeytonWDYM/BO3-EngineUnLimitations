#include "PassiveControl.h"
#include "../preentry/Identity.h"
#include <exception>

namespace bo3::late_startup {
namespace {
#ifdef BO3_LATE_OWNED_TEST
std::function<void(HANDLE)> ownedObserver;
#endif
void VerifyNoDebugger(HANDLE process) {
    BOOL debugger=TRUE;
    Require(CheckRemoteDebuggerPresent(process,&debugger)!=FALSE && !debugger,
        "The passive owned child has a debugger.");
}
}
#ifdef BO3_LATE_OWNED_TEST
void SetPassiveOwnedObserver(std::function<void(HANDLE)> observer){ownedObserver=std::move(observer);}
#endif
void CoordinatePassiveControl(OwnedChild& child,MappedGate& gate,enhanced::MappedHelper& helper,
    const std::filesystem::path& helperFile,const PassiveImage& image,ControlReceipt& receipt) {
    const auto deadline=GetTickCount64()+child.payload.deadlineMs;
    receipt.processId=child.process.dwProcessId;receipt.primaryThreadId=child.process.dwThreadId;
    receipt.created=child.payload.processCreatedFileTime;receipt.gateDeadlineMs=child.payload.deadlineMs;
    try {
        child.Resume();child.WaitReady(deadline);gate.Admit(child.process.hProcess);
        const auto state=gate.Read(child.process.hProcess);receipt.generation=state.generation;receipt.gateBase=gate.Base();
        gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
        VerifyNoDebugger(child.process.hProcess);
        receipt.patch.imageBase=image(child.process.hProcess);
        receipt.preAttachCallBytes=vm_startup::ReadStopped(child.process.hProcess,receipt.patch.imageBase+0x22b1559u,5);
        receipt.preAttachTargetBytes=vm_startup::ReadStopped(child.process.hProcess,receipt.patch.imageBase+0x227a3a0u,64);
        AdmitStockControl(child.process.hProcess,receipt.patch.imageBase,helper,helperFile,receipt);
        receipt.admitted=true;
        gate.VerifyWaiting(child.process.hProcess,child.payload,receipt.generation);
        VerifyControlBindings(child.process.hProcess,helper);receipt.bindingsUnchanged=true;
        VerifyNoDebugger(child.process.hProcess);receipt.debuggerAbsent=true;
        Require(!child.Exited(),"The owned passive child exited before gate release.");
        Require(GetTickCount64()<deadline,"The sequential passive checks exceeded the gate deadline.");
#ifdef BO3_LATE_OWNED_TEST
        ownedObserver(child.process.hProcess);
#endif
        child.Release();receipt.released=true;
    }catch(...) {
        const auto original=std::current_exception();
#ifdef BO3_LATE_OWNED_TEST
        if(receipt.patch.imageBase)ownedObserver(child.process.hProcess);
#endif
        if(!child.Exited())receipt.terminated=TerminateProcess(child.process.hProcess,97)!=FALSE;
        WaitForSingleObject(child.process.hProcess,5000);
        if(child.Exited() && GetExitCodeProcess(child.process.hProcess,&receipt.observedExitCode))receipt.observedExited=true;
        std::rethrow_exception(original);
    }
}
}
