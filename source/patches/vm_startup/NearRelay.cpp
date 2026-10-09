#include "NearRelay.h"
#include <algorithm>
#include <stdexcept>

namespace vm_startup {
NearRelay::NearRelay(HANDLE process,ImageRange image,std::span<const NativeEntry> entries):process_(process) {
    if(entries.empty() || image.base>UINTPTR_MAX-image.size) throw std::runtime_error("Invalid native relay image.");
    std::uintptr_t low=0x10000,high=UINTPTR_MAX-0x10000;
    for(const auto& entry:entries) {
        if(entry.rva>=image.size || image.size-entry.rva<5) throw std::runtime_error("Native relay entry exceeds image.");
        const auto next=image.base+entry.rva+5;
        low=std::max(low,next>=0x80000000ull ? next-0x80000000ull : 0);
        high=std::min(high,next<=UINTPTR_MAX-0x7fffffffull ? next+0x7fffffffull-64 : UINTPTR_MAX-64);
    }
    SYSTEM_INFO system{}; GetSystemInfo(&system);
    const auto granularity=static_cast<std::uintptr_t>(system.dwAllocationGranularity);
    auto candidate=(low+granularity-1)&~(granularity-1);
    while(candidate<=high) {
        MEMORY_BASIC_INFORMATION memory{};
        if(VirtualQueryEx(process_,reinterpret_cast<void*>(candidate),&memory,sizeof(memory))!=sizeof(memory)) break;
        if(memory.State==MEM_FREE && memory.RegionSize>=4096) {
            const auto allocation=VirtualAllocEx(process_,reinterpret_cast<void*>(candidate),4096,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READ);
            if(allocation) { address_=reinterpret_cast<std::uintptr_t>(allocation); return; }
        }
        const auto end=reinterpret_cast<std::uintptr_t>(memory.BaseAddress)+memory.RegionSize;
        if(end<=candidate || end>UINTPTR_MAX-granularity) break;
        candidate=(end+granularity-1)&~(granularity-1);
    }
    throw std::runtime_error("No reachable owned native relay allocation.");
}
NearRelay::~NearRelay() {
    if(address_ && !committed_) VirtualFreeEx(process_,reinterpret_cast<void*>(address_),0,MEM_RELEASE);
}
}
