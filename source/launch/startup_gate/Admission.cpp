#include "Admission.h"
#include "GateProfile.h"
#include <detours.h>
#include <winternl.h>
#include <cstring>

namespace bo3::startup_gate {
constinit Payload configuration{};
constinit LoaderCallout loaderCallout{};
namespace {
using QueryObject=NTSTATUS(NTAPI*)(HANDLE,OBJECT_INFORMATION_CLASS,PVOID,ULONG,PULONG);
bool TypedHandle(QueryObject query,std::uint64_t value,const wchar_t* expected,USHORT characters,ACCESS_MASK rights) {
    const auto handle=reinterpret_cast<HANDLE>(value);
    PUBLIC_OBJECT_BASIC_INFORMATION basic{};
    if(query(handle,ObjectBasicInformation,&basic,sizeof(basic),nullptr)<0 || (basic.GrantedAccess&rights)!=rights) return false;
    alignas(void*) unsigned char storage[1024]{};
    ULONG count{};
    if(query(handle,ObjectTypeInformation,storage,sizeof(storage),&count)<0 || count>sizeof(storage)) return false;
    const auto& name=*reinterpret_cast<const UNICODE_STRING*>(storage);
    const auto start=reinterpret_cast<std::uintptr_t>(storage);
    const auto text=reinterpret_cast<std::uintptr_t>(name.Buffer);
    const auto size=static_cast<USHORT>(characters*sizeof(wchar_t));
    return name.Length==size && text>=start && text<=start+sizeof(storage)-size
        && std::memcmp(name.Buffer,expected,size)==0;
}
}
// Enumerate the same Detours payload modules, rejecting duplicate authority records.
bool AdmitPayload() {
    const void* payload{}; DWORD size{};
    for(HMODULE module=nullptr;(module=DetourEnumerateModules(module))!=nullptr;) {
        DWORD foundSize{};
        const auto* found=DetourFindPayload(module,PayloadGuid,&foundSize);
        if(found) { if(payload) return false; payload=found; size=foundSize; }
    }
    if(!payload || size!=sizeof(Payload)) return false;
    std::memcpy(&configuration,payload,sizeof(configuration));
    const auto& p=configuration;
    if(p.abi!=Abi || p.bytes!=sizeof(Payload) || p.processId!=GetCurrentProcessId()
        || p.primaryThreadId!=GetCurrentThreadId() || !p.parentProcessId || p.parentProcessId==p.processId
        || !(p.nonce[0]|p.nonce[1]) || p.deadlineMs!=kGateDeadlineMs
        || !p.readyEvent || !p.releaseEvent || !p.parentProcess || p.readyEvent==p.releaseEvent
        || p.parentProcess==p.readyEvent || p.parentProcess==p.releaseEvent) return false;
    FILETIME created{},exited{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user)
        || ((std::uint64_t(created.dwHighDateTime)<<32)|created.dwLowDateTime)!=p.processCreatedFileTime) return false;
    const auto ntdll=GetModuleHandleW(L"ntdll.dll");
    loaderCallout=reinterpret_cast<LoaderCallout>(GetProcAddress(ntdll,kLoaderQueryName));
    const auto query=reinterpret_cast<QueryObject>(GetProcAddress(ntdll,"NtQueryObject"));
    if(!loaderCallout || !query) return false;
    if(!TypedHandle(query,p.readyEvent,L"Event",5,EVENT_MODIFY_STATE|SYNCHRONIZE)
        || !TypedHandle(query,p.releaseEvent,L"Event",5,SYNCHRONIZE)
        || !TypedHandle(query,p.parentProcess,L"Process",7,SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION)) return false;
    if(CompareObjectHandles(reinterpret_cast<HANDLE>(p.readyEvent),reinterpret_cast<HANDLE>(p.releaseEvent))) return false;
    const auto parent=reinterpret_cast<HANDLE>(p.parentProcess);
    // No synchronization in DllMain. Nonblocking handle queries establish payload identity.
    DWORD parentExit{};
    return GetProcessId(parent)==p.parentProcessId && GetExitCodeProcess(parent,&parentExit) && parentExit==STILL_ACTIVE;
}
}
