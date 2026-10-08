#include "Gate.h"
#include "Admission.h"
#include "NativeEntry.h"
#include "../startup_probe/Observation.h"
#include "ProbeProfile.h"
#include <cstring>
#include <intrin.h>

namespace bo3::startup_gate {
extern "C" { __declspec(dllexport) constinit State Bo3StartupGateState{}; }
namespace {
[[noreturn]] void Fail(DWORD reason,DWORD error) {
    auto& state=Bo3StartupGateState;
    state.refusal=reason; state.lastError=error;
    InterlockedExchange(&state.phase,static_cast<LONG>(Phase::Refused));
    TerminateProcess(GetCurrentProcess(),0xe0427600u|reason);
    __fastfail(FAST_FAIL_FATAL_APP_EXIT);
}
}
// The API already returned normally. Only the pinned primary-thread CRT call may wait.
void Enter(std::uintptr_t returnSite,std::uintptr_t apiReturnSlot) {
    auto& state=Bo3StartupGateState;
    const auto base=startup_probe::Bo3StartupProbeCounters.imageBase;
    if(state.phase!=static_cast<LONG>(Phase::Armed) || returnSite!=base+kReturnRva
        || GetCurrentThreadId()!=configuration.primaryThreadId) return;
    unsigned char caller[44]{}; SIZE_T count{};
    if(!ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(base+kCallerRva),caller,sizeof(caller),&count)
        || count!=sizeof(caller) || std::memcmp(caller,kCallerBytes,sizeof(caller))) return;
    ULONG_PTR low{},high{}; GetCurrentThreadStackLimits(&low,&high);
    if(apiReturnSlot>UINTPTR_MAX-kWrapperCallerDelta) return;
    const auto slot=apiReturnSlot+kWrapperCallerDelta;
    std::uintptr_t outer{};
    if(slot<low || high<sizeof(outer) || slot>high-sizeof(outer)
        || !ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(slot),&outer,sizeof(outer),&count)
        || count!=sizeof(outer) || outer!=base+kCrtReturnRva) return;
    if(loaderCallout()) return;
    if(!HasNativeEntry(state)) return;
    if(InterlockedCompareExchange(&state.phase,static_cast<LONG>(Phase::Cold),static_cast<LONG>(Phase::Armed))
        !=static_cast<LONG>(Phase::Armed)) return;
    const auto parent=reinterpret_cast<HANDLE>(configuration.parentProcess);
    const auto release=reinterpret_cast<HANDLE>(configuration.releaseEvent);
    // Release cannot be pre-signaled. Parent loss never allows this callback to return.
    if(WaitForSingleObject(parent,0)!=WAIT_TIMEOUT) Fail(1,GetLastError());
    if(WaitForSingleObject(release,0)!=WAIT_TIMEOUT) Fail(2,GetLastError());
    startup_probe::Observe(returnSite,apiReturnSlot);
    state.generation=1; state.returnSite=returnSite; state.wrapperCallerReturn=outer;
    state.callbackThreadId=GetCurrentThreadId(); state.loaderCallout=0;
    state.observationCount=startup_probe::Bo3StartupProbeObservation.count;
    InterlockedExchange(&state.phase,static_cast<LONG>(Phase::Waiting));
    if(!SetEvent(reinterpret_cast<HANDLE>(configuration.readyEvent))) Fail(3,GetLastError());
    const HANDLE handles[]{parent,release};
    state.waitResult=WaitForMultipleObjects(2,handles,FALSE,configuration.deadlineMs);
    if(state.waitResult!=WAIT_OBJECT_0+1) Fail(4,state.waitResult==WAIT_FAILED ? GetLastError() : state.waitResult);
    if(WaitForSingleObject(parent,0)!=WAIT_TIMEOUT) Fail(5,GetLastError());
    InterlockedExchange(&state.phase,static_cast<LONG>(Phase::Released));
    InterlockedExchange(&state.phase,static_cast<LONG>(Phase::Returned));
}
}
