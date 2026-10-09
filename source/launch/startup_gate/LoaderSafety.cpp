#include "LoaderSafety.h"
#include "GateProfile.h"
#include <winternl.h>

namespace bo3::startup_gate {
namespace {
using Query=BOOLEAN(NTAPI*)();
constinit Query query{};
using Owned=BOOL(NTAPI*)(RTL_CRITICAL_SECTION*);
constinit Owned owned{};
constinit RTL_CRITICAL_SECTION* loaderLock{};
constinit bool admitted{};
// Valve Wine's x64 PEB ABI. Read it only after identifying Wine, and prove ownership
// during DllMain before using it. Unknown layouts or unreadable memory refuse admission.
constexpr std::size_t kWineLoaderLockOffset=0x110;
bool ReadLock(RTL_CRITICAL_SECTION*& lock) {
    const auto peb=NtCurrentTeb()->ProcessEnvironmentBlock;
    SIZE_T count{};
    return peb && ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<const unsigned char*>(peb)
        +kWineLoaderLockOffset,&lock,sizeof(lock),&count) && count==sizeof(lock) && lock;
}
bool WineOwned() {
    RTL_CRITICAL_SECTION* current{};RTL_CRITICAL_SECTION observed{};SIZE_T count{};
    if(!owned || !loaderLock || !ReadLock(current) || current!=loaderLock
        || !ReadProcessMemory(GetCurrentProcess(),loaderLock,&observed,sizeof(observed),&count)
        || count!=sizeof(observed))return true;
    return observed.OwningThread==reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(GetCurrentThreadId()))
        && observed.RecursionCount>0;
}
}
bool AdmitLoaderSafety() {
    admitted=false;
    const auto ntdll=GetModuleHandleW(L"ntdll.dll");
    query=reinterpret_cast<Query>(GetProcAddress(ntdll,kLoaderQueryName));
    if(query) {admitted=true;return true;}
    if(sizeof(void*)!=8 || !GetProcAddress(ntdll,"wine_get_version"))return false;
    owned=reinterpret_cast<Owned>(GetProcAddress(ntdll,"RtlIsCriticalSectionLockedByThread"));
    if(!owned || !ReadLock(loaderLock))return false;
    RTL_CRITICAL_SECTION observed{};SIZE_T count{};
    admitted=ReadProcessMemory(GetCurrentProcess(),loaderLock,&observed,sizeof(observed),&count)
        && count==sizeof(observed) && observed.RecursionCount>0
        && observed.OwningThread==reinterpret_cast<HANDLE>(static_cast<ULONG_PTR>(GetCurrentThreadId()))
        && owned(loaderLock)!=FALSE;
    return admitted;
}
bool WithinLoaderCallout() {return !admitted || (query ? query()!=FALSE : WineOwned());}
}
