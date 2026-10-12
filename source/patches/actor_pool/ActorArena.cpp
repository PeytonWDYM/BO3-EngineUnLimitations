#include "ActorArena.h"
#include <stdexcept>

namespace bo3::actors {
ActorArena::ActorArena(HANDLE process,std::uintptr_t game,std::uint32_t imageBytes) {
    if(imageBytes!=494186496 || game>UINTPTR_MAX-0x7FFFFFFF)throw std::runtime_error("The actor image range is invalid.");
    if(!DuplicateHandle(GetCurrentProcess(),process,GetCurrentProcess(),&process_,0,FALSE,DUPLICATE_SAME_ACCESS))
        throw std::runtime_error("The actor process handle duplication failed.");
    const auto end=game+0x7FFFFFFF-Bytes;
    auto cursor=(game+imageBytes+0xFFFF)&~std::uintptr_t{0xFFFF};
    while(cursor<=end) {
        MEMORY_BASIC_INFORMATION region{};
        if(VirtualQueryEx(process_,reinterpret_cast<void*>(cursor),&region,sizeof region)!=sizeof region)break;
        const auto regionEnd=reinterpret_cast<std::uintptr_t>(region.BaseAddress)+region.RegionSize;
        if(region.State==MEM_FREE && regionEnd>=cursor && regionEnd-cursor>=Bytes) {
            if(auto* allocation=VirtualAllocEx(process_,reinterpret_cast<void*>(cursor),Bytes,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)) {
                base_=reinterpret_cast<std::uintptr_t>(allocation);return;
            }
        }
        if(regionEnd<=cursor || regionEnd>UINTPTR_MAX-0xFFFF)break;
        cursor=(regionEnd+0xFFFF)&~std::uintptr_t{0xFFFF};
    }
    CloseHandle(process_);process_=nullptr;
    throw std::runtime_error("A complete actor arena within relative reach is unavailable.");
}
ActorArena::~ActorArena() {
    if(base_&&!committed_)VirtualFreeEx(process_,reinterpret_cast<void*>(base_),0,MEM_RELEASE);
    if(process_)CloseHandle(process_);
}
void ActorArena::Write(std::size_t offset,const void* bytes,std::size_t count) {
    if(!count || offset>Bytes || count>Bytes-offset)throw std::runtime_error("The actor arena write exceeds its reservation.");
    SIZE_T written{};
    if(!WriteProcessMemory(process_,reinterpret_cast<void*>(base_+offset),bytes,count,&written)||written!=count)
        throw std::runtime_error("The actor arena write failed.");
}
void ActorArena::Protect() {
    DWORD old{};
    if(!VirtualProtectEx(process_,reinterpret_cast<void*>(base_),0x200000,PAGE_EXECUTE_READ,&old)||
       !VirtualProtectEx(process_,reinterpret_cast<void*>(base_+0x200000),0x200000,PAGE_READONLY,&old)||
       !FlushInstructionCache(process_,reinterpret_cast<void*>(base_),0x200000))
        throw std::runtime_error("The actor arena protection failed.");
}
}
