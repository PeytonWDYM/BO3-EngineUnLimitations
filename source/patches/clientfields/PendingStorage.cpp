#include "PendingStorage.h"
#include "PendingManifest.h"
#include "GameManifest.h"
#include "../../launch/preentry/Identity.h"
#include "../vm_startup/PausedPatch.h"
#include <algorithm>

namespace bo3::clientfields {
PendingStorage::PendingStorage(HANDLE process,std::uintptr_t image):process_(process) {
    Require(image<=UINTPTR_MAX-enhanced::ExactGameManifest.imageSize,"Invalid callback image.");
    SYSTEM_INFO system{};GetSystemInfo(&system);
    const auto granularity=static_cast<std::uintptr_t>(system.dwAllocationGranularity);
    const auto rounded=(kPendingStorageBytes+system.dwPageSize-1)&~(system.dwPageSize-1);
    std::uintptr_t low=0x10000,high=UINTPTR_MAX-rounded;
    for(const auto& row:PendingInstructions) {
        if(row.operand!=PendingOperand::Pool)continue;
        const auto next=image+row.rva+row.size;
        low=std::max(low,next>=0x80000000ull ? next-0x80000000ull : 0);
        high=std::min(high,next<=UINTPTR_MAX-0x7FFFFFFFull ? next+0x7FFFFFFFull : UINTPTR_MAX-rounded);
    }
    Require(low<=UINTPTR_MAX-granularity,"Callback allocation interval overflows.");
    auto candidate=(low+granularity-1)&~(granularity-1);
    while(candidate<=high) {
        MEMORY_BASIC_INFORMATION memory{};
        if(VirtualQueryEx(process_,reinterpret_cast<void*>(candidate),&memory,sizeof(memory))!=sizeof(memory))break;
        const auto begin=reinterpret_cast<std::uintptr_t>(memory.BaseAddress);
        if(memory.RegionSize>UINTPTR_MAX-begin)break;
        const auto end=begin+memory.RegionSize;
        if(memory.State==MEM_FREE && end>=candidate && end-candidate>=rounded) {
            const auto allocation=VirtualAllocEx(process_,reinterpret_cast<void*>(candidate),kPendingStorageBytes,
                MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
            if(allocation) {address_=reinterpret_cast<std::uintptr_t>(allocation);break;}
        }
        if(end<=candidate || end>UINTPTR_MAX-granularity)break;
        candidate=(end+granularity-1)&~(granularity-1);
    }
    Require(address_!=0,"No complete reachable callback allocation exists.");
    try {
        MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process_,reinterpret_cast<void*>(address_),&memory,sizeof(memory))==sizeof(memory)
            && memory.State==MEM_COMMIT && memory.Protect==PAGE_READWRITE
            && reinterpret_cast<std::uintptr_t>(memory.AllocationBase)==address_
            && reinterpret_cast<std::uintptr_t>(memory.BaseAddress)==address_ && memory.RegionSize>=rounded,
            "The callback backing allocation is incomplete.");
        const auto bytes=vm_startup::ReadStopped(process_,address_,kPendingStorageBytes);
        Require(std::all_of(bytes.begin(),bytes.end(),[](unsigned char value){return value==0;}),
            "The callback backing was not fully initialized.");
    }catch(...) {VirtualFreeEx(process_,reinterpret_cast<void*>(address_),0,MEM_RELEASE);address_=0;throw;}
}
PendingStorage::~PendingStorage() {
    if(address_ && !committed_)VirtualFreeEx(process_,reinterpret_cast<void*>(address_),0,MEM_RELEASE);
}
}
