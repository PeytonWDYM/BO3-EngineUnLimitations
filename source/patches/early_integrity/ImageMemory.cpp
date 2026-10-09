#include "ImageMemory.h"
#include <algorithm>
#include <stdexcept>
#include <string>

namespace bo3::early_integrity {
void RequireImageMemory(HANDLE process,std::uintptr_t imageBase,std::uintptr_t address,std::size_t size) {
    if(!size || address>UINTPTR_MAX-size)throw std::runtime_error("Early integrity memory span is invalid.");
    const bool wine=GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"wine_get_version")!=nullptr;
    const auto end=address+size;
    while(address<end) {
        MEMORY_BASIC_INFORMATION memory{};
        if(VirtualQueryEx(process,reinterpret_cast<void*>(address),&memory,sizeof(memory))!=sizeof(memory))
            throw std::runtime_error("Cannot query early integrity image memory.");
        // Wine maps writable executable PE sections as copy-on-write. Keep the exact
        // Windows policy and reject protection modifiers, foreign owners and non-image views.
        const bool protection=memory.Protect==PAGE_EXECUTE_READWRITE
            || (wine && memory.Protect==PAGE_EXECUTE_WRITECOPY);
        if(memory.State!=MEM_COMMIT || memory.Type!=MEM_IMAGE || !protection
            || reinterpret_cast<std::uintptr_t>(memory.AllocationBase)!=imageBase)
            throw std::runtime_error("Early integrity image ownership or protection differs at RVA "
                +std::to_string(address-imageBase)+", protection "+std::to_string(memory.Protect)+".");
        const auto start=reinterpret_cast<std::uintptr_t>(memory.BaseAddress);
        if(start>address || !memory.RegionSize || start>UINTPTR_MAX-memory.RegionSize
            || address>=start+memory.RegionSize)throw std::runtime_error("Early integrity memory region is invalid.");
        address=std::min(end,start+memory.RegionSize);
    }
}
}
