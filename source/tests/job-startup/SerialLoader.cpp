#include "SerialLoader.h"
#include "../../launch/preentry/Identity.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <winternl.h>
#include <Psapi.h>
#include <array>
#include <cstring>

void ConfigureOwnedSerialLoader(const bo3::late_startup::OwnedChild& child) {
    // Mozilla's Windows sandbox uses this field before first resume (bug 1515088, comment 5).
    // Current owned OS26200 ntdll reads LoaderThreads at+0x40c, then calls its loader pool initializer.
    const auto ntdll=GetModuleHandleW(L"ntdll.dll");
    const std::array<unsigned char,11> load{0x8b,0x89,0x0c,0x04,0,0,0xe8,0xe1,0x78,0x05,0};
    Require(std::memcmp(reinterpret_cast<const unsigned char*>(ntdll)+0x8de40,load.data(),load.size())==0,
        "The owned serial-loader field reader differs.");
    std::array<wchar_t,32768> ownImage{};
    Require(GetMappedFileNameW(GetCurrentProcess(),ntdll,ownImage.data(),static_cast<DWORD>(ownImage.size()))!=0,
        "Cannot identify the owned native image.");
    bool admitted=false;
    for(std::uintptr_t address=0x10000;;) {
        MEMORY_BASIC_INFORMATION info{};
        if(VirtualQueryEx(child.process.hProcess,reinterpret_cast<void*>(address),&info,sizeof(info))!=sizeof(info))break;
        if(info.Type==MEM_IMAGE && info.BaseAddress==info.AllocationBase) {
            std::array<wchar_t,32768> path{};
            Require(GetMappedFileNameW(child.process.hProcess,info.AllocationBase,path.data(),static_cast<DWORD>(path.size()))!=0,
                "Cannot identify an owned mapped image.");
            if(CompareStringOrdinal(path.data(),-1,ownImage.data(),-1,TRUE)==CSTR_EQUAL) {
                const auto base=reinterpret_cast<std::uintptr_t>(info.AllocationBase);
                Require(vm_startup::ReadStopped(child.process.hProcess,base+0x8de40,load.size())==std::vector<unsigned char>(load.begin(),load.end()),
                    "The owned native serial-loader bytes differ.");admitted=true;break;
            }
        }
        const auto end=reinterpret_cast<std::uintptr_t>(info.BaseAddress)+info.RegionSize;
        if(end<=address)break;address=end;
    }
    Require(admitted,"The owned native serial-loader image is absent.");
    using Query=NTSTATUS(NTAPI*)(HANDLE,PROCESSINFOCLASS,PVOID,ULONG,PULONG);
    const auto query=reinterpret_cast<Query>(GetProcAddress(ntdll,"NtQueryInformationProcess"));
    PROCESS_BASIC_INFORMATION basic{};
    Require(query && query(child.process.hProcess,ProcessBasicInformation,&basic,sizeof(basic),nullptr)==0,
        "Cannot read owned process parameters.");
    const auto pointer=vm_startup::ReadStopped(child.process.hProcess,reinterpret_cast<std::uintptr_t>(basic.PebBaseAddress)+0x20,8);
    std::uintptr_t parameters{};std::memcpy(&parameters,pointer.data(),8);
    const auto headers=vm_startup::ReadStopped(child.process.hProcess,parameters,8);
    std::array<DWORD,2> sizes{};std::memcpy(sizes.data(),headers.data(),8);
    Require(sizes[1]>=0x410 && sizes[0]>=sizes[1]
        && vm_startup::ReadStopped(child.process.hProcess,parameters+0x40c,4)==std::vector<unsigned char>(4,0),
        "The owned serial-loader parameter shape differs.");
    const DWORD one=1;SIZE_T written{};
    Require(WriteProcessMemory(child.process.hProcess,reinterpret_cast<void*>(parameters+0x40c),&one,4,&written)
        && written==4 && vm_startup::ReadStopped(child.process.hProcess,parameters+0x40c,4)==std::vector<unsigned char>{1,0,0,0},
        "Cannot select the owned serial loader.");
}
