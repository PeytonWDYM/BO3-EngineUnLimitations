#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include "../../launch/startup_gate/GateContract.h"
#include "StackEvidence.h"
namespace {
DWORD proof{};
StackEvidence stack{};
}
extern "C" __declspec(dllexport) DWORD ConsumerProof() { return proof; }
extern "C" __declspec(dllexport) const StackEvidence* ConsumerStack() { return &stack; }
BOOL WINAPI DllMain(HINSTANCE,DWORD reason,LPVOID) {
    if(reason!=DLL_PROCESS_ATTACH) return TRUE;
    const auto image=GetModuleHandleW(nullptr);
    const auto helper=GetModuleHandleW(L"Bo3StartupGate.dll");
    auto* state=reinterpret_cast<bo3::startup_gate::State*>(GetProcAddress(helper,"Bo3StartupGateState"));
    using Caller=int(*)();
    const auto caller=reinterpret_cast<Caller>(GetProcAddress(image,"OwnedCrtCaller"));
    using Query=BOOLEAN(NTAPI*)();
    const auto query=reinterpret_cast<Query>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"RtlIsThreadWithinLoaderCallout"));
    const bool loader=query()!=FALSE;
    stack=CaptureEntryStack();
    SetLastError(0x13579); caller();
    proof=loader && GetLastError()==0x13579 && state->phase==static_cast<LONG>(bo3::startup_gate::Phase::Armed)
        && state->generation==0 ? 1u : 0u;
    return TRUE;
}
