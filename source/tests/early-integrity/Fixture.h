#pragma once
#include "../../patches/early_integrity/Plan.h"
#include "EarlyIntegrityProfile.h"
#include <cstdint>
#include <algorithm>
#include <stdexcept>
struct FixtureState {std::uintptr_t imageBase;};
// Windows initially maps writable image sections with copy-on-write protection.
// The owned fixture adopts the captured RWX protection before planner admission.
inline void SeedFixtureProtection(HANDLE process,std::uintptr_t imageBase) {
    for(const auto& region:bo3::early_integrity::kRegions) {
        DWORD prior{};
        if(!VirtualProtectEx(process,reinterpret_cast<void*>(imageBase+region.rva),region.size,PAGE_EXECUTE_READWRITE,&prior))
            throw std::runtime_error("Cannot set owned fixture image protection.");
    }
    std::vector<std::uintptr_t> pages;
    auto add=[&](std::uintptr_t rva){pages.push_back((imageBase+rva)&~static_cast<std::uintptr_t>(4095));};
    for(const auto& guard:bo3::early_integrity::kGuards){add(guard.rva);add(guard.rva+guard.size-1);}
    for(const auto& site:bo3::early_integrity::kSites){add(site.expectedRva);add(site.expectedRva+3);add(site.chainDestinationRva);add(site.chainDestinationRva+3);}
    std::sort(pages.begin(),pages.end());pages.erase(std::unique(pages.begin(),pages.end()),pages.end());
    // An unchanged-byte write makes each owned page adopt RWX after copy-on-write.
    for(const auto page:pages) {
        unsigned char byte{};SIZE_T count{};
        if(!ReadProcessMemory(process,reinterpret_cast<void*>(page),&byte,1,&count) || count!=1
            || !WriteProcessMemory(process,reinterpret_cast<void*>(page),&byte,1,&count) || count!=1)
            throw std::runtime_error("Cannot prepare owned copy-on-write image pages.");
    }
}
void ProveRelays();
