#include "ClientfieldStorage.h"
#include "PendingManifest.h"
#include "CounterManifest.h"
#include "GameManifest.h"
#include "../../launch/preentry/Identity.h"
#include "../vm_startup/PausedPatch.h"
#include <algorithm>

namespace bo3::clientfields {
ClientfieldStorage::ClientfieldStorage(HANDLE process,std::uintptr_t image):process_(process) {
    Require(image<=UINTPTR_MAX-enhanced::ExactGameManifest.imageSize,"Invalid clientfield image.");
    SYSTEM_INFO system{};GetSystemInfo(&system);
    const auto granularity=static_cast<std::uintptr_t>(system.dwAllocationGranularity);
    const auto rounded=(kClientfieldStorageBytes+system.dwPageSize-1)&~(system.dwPageSize-1);
    std::uintptr_t low=0x10000,high=UINTPTR_MAX-rounded;
    const auto constrain=[&](std::uint32_t endRva,std::uint32_t offset) {
        const auto next=image+endRva;
        const auto targetLow=next>=0x80000000ull ? next-0x80000000ull : 0;
        const auto targetHigh=next<=UINTPTR_MAX-0x7FFFFFFFull ? next+0x7FFFFFFFull : UINTPTR_MAX;
        Require(targetHigh>=offset,"Clientfield reach interval is empty.");
        low=std::max(low,targetLow>=offset ? targetLow-offset : 0);
        high=std::min(high,targetHigh-offset);
    };
    for(const auto& row:PendingInstructions)
        if(row.operand==PendingOperand::Pool)constrain(row.rva+row.size,0);
    for(const auto& row:CounterInstructions)
        if(row.operand!=CounterOperand::Capacity && row.operand!=CounterOperand::Bytes)
            constrain(row.rva+row.size,kCounterStorageOffset+CounterOffset(row.operand));
    Require(low<=UINTPTR_MAX-granularity,"Clientfield allocation interval overflows.");
    auto candidate=(low+granularity-1)&~(granularity-1);
    while(candidate<=high) {
        MEMORY_BASIC_INFORMATION memory{};
        if(VirtualQueryEx(process_,reinterpret_cast<void*>(candidate),&memory,sizeof(memory))!=sizeof(memory))break;
        const auto begin=reinterpret_cast<std::uintptr_t>(memory.BaseAddress);
        if(memory.RegionSize>UINTPTR_MAX-begin)break;
        const auto end=begin+memory.RegionSize;
        if(memory.State==MEM_FREE && end>=candidate && end-candidate>=rounded) {
            const auto allocation=VirtualAllocEx(process_,reinterpret_cast<void*>(candidate),kClientfieldStorageBytes,
                MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
            if(allocation) {address_=reinterpret_cast<std::uintptr_t>(allocation);break;}
        }
        if(end<=candidate || end>UINTPTR_MAX-granularity)break;
        candidate=(end+granularity-1)&~(granularity-1);
    }
    Require(address_!=0,"No complete reachable clientfield allocation exists.");
    try {
        MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process_,reinterpret_cast<void*>(address_),&memory,sizeof(memory))==sizeof(memory)
            && memory.State==MEM_COMMIT && memory.Protect==PAGE_READWRITE
            && reinterpret_cast<std::uintptr_t>(memory.AllocationBase)==address_
            && reinterpret_cast<std::uintptr_t>(memory.BaseAddress)==address_ && memory.RegionSize>=rounded,
            "The clientfield backing allocation is incomplete.");
        const auto bytes=vm_startup::ReadStopped(process_,address_,kClientfieldStorageBytes);
        Require(std::all_of(bytes.begin(),bytes.end(),[](unsigned char value){return value==0;}),
            "The clientfield backing was not fully initialized.");
    }catch(...) {VirtualFreeEx(process_,reinterpret_cast<void*>(address_),0,MEM_RELEASE);address_=0;throw;}
}
ClientfieldStorage::~ClientfieldStorage() {
    if(address_ && !committed_)VirtualFreeEx(process_,reinterpret_cast<void*>(address_),0,MEM_RELEASE);
}
}
