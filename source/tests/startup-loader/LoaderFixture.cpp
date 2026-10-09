#include "../../launch/startup_gate/LoaderSafety.h"
#include <winternl.h>
#include <initializer_list>
using namespace bo3::startup_gate;
namespace {constinit LONG threadAttach{};}
extern "C" __declspec(dllexport) BOOL Safe() {return !WithinLoaderCallout();}
extern "C" __declspec(dllexport) LONG ThreadAttach() {return threadAttach;}
// Owned fixture only: caller holds the loader lock; restore the PEB before returning.
extern "C" __declspec(dllexport) BOOL BrokenLockRefused() {
    const auto ntdll=GetModuleHandleW(L"ntdll.dll");
    if(!GetProcAddress(ntdll,"wine_get_version")
        || GetProcAddress(ntdll,"RtlIsThreadWithinLoaderCallout"))return TRUE;
    auto* slot=reinterpret_cast<void**>(reinterpret_cast<unsigned char*>(NtCurrentTeb()->ProcessEnvironmentBlock)+0x110);
    const auto saved=*slot;
    bool refused=true;
    for(const auto value : {std::uintptr_t{0},std::uintptr_t{1}}) {
        *slot=reinterpret_cast<void*>(value);
        refused=WithinLoaderCallout() && !AdmitLoaderSafety() && WithinLoaderCallout() && refused;
        *slot=saved;
        refused=AdmitLoaderSafety() && WithinLoaderCallout() && refused;
    }
    return refused;
}
BOOL WINAPI DllMain(HINSTANCE,DWORD reason,LPVOID) {
    if(reason==DLL_PROCESS_ATTACH)
        return WithinLoaderCallout() && AdmitLoaderSafety() && WithinLoaderCallout();
    if(reason==DLL_THREAD_ATTACH)InterlockedExchange(&threadAttach,WithinLoaderCallout()?1:-1);
    return TRUE;
}
