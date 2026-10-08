#include "Originals.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../preentry/Identity.h"
#include "GameManifest.h"
#include <array>

namespace bo3::job_control {
std::vector<Original> StockOriginals(std::uintptr_t image,const enhanced::MappedHelper& helper) {
    std::vector<Original> rows;
    const auto add=[&](const char* name,std::uintptr_t address,std::vector<unsigned char> bytes) {
        rows.push_back({name,address,std::move(bytes)});
    };
    for(const auto& count:enhanced::ExactGameManifest.counts)
        add("server-count",image+count.rva+count.immediateOffset,
            {count.bytes.begin()+count.immediateOffset,count.bytes.begin()+count.immediateOffset+4});
    for(const auto& entry:enhanced::ExactGameManifest.entries)add("vm-entry",image+entry.rva,{entry.original.begin(),entry.original.end()});
    const std::array<std::pair<DWORD,std::vector<unsigned char>>,10> native{{
        {0x13619e0,{0x48,0x89,0x74,0x24,0x10}}, {0x13617f0,{0x40,0x53,0x55,0x41,0x56}},
        {0x21f9aa0,{0x3b,0x0d,0x02,0xd5,0x55,0x15,0x75,0x21}}, {0x21fa750,{0x48,0x89,0x5c,0x24,0x10}},
        {0x12e1c0,{0x48,0x89,0x5c,0x24,0x08}}, {0x2277a60,{0x40,0x57,0x48,0x83,0xec,0x20}},
        {0x1361a50,{0xe8,0xdb,0x08,0,0}}, {0x12e226,{0x83,0xf8,0x03,0x74,0x1f}},
        {0xb253f,{0xbf,0,0,0x28,0}}, {0x21fa7ae,{0xc7,0x44,0x24,0x5c,3,0,0,0}}}};
    for(const auto& [rva,bytes]:native)add("migration-original",image+rva,bytes);
    const std::array<std::pair<DWORD,std::size_t>,7> records{{
        {helper.state.stateBindings,48},{helper.state.errorBindings,32},{helper.migration.bindings,64},
        {helper.migration.versionBranches,16},{helper.migration.loadBindings,16},
        {helper.migration.reentries,56},{helper.migration.flushBindings,16}}};
    for(const auto& [rva,size]:records)add("helper-binding",helper.image.base+rva,std::vector<unsigned char>(size,0));
    Require(rows.size()==40,"The complete forty existing stock spans are required.");return rows;
}
void VerifyOriginals(HANDLE process,const std::vector<Original>& rows) {
    for(const auto& row:rows) {
        Require(vm_startup::ReadStopped(process,row.address,row.bytes.size())==row.bytes,
            "An existing stock transaction original differs.");
        MEMORY_BASIC_INFORMATION page{};
        Require(VirtualQueryEx(process,reinterpret_cast<void*>(row.address),&page,sizeof(page))==sizeof(page)
            && page.State==MEM_COMMIT && row.address>=reinterpret_cast<std::uintptr_t>(page.BaseAddress)
            && row.address-reinterpret_cast<std::uintptr_t>(page.BaseAddress)<=page.RegionSize
            && row.bytes.size()<=page.RegionSize-(row.address-reinterpret_cast<std::uintptr_t>(page.BaseAddress)),"Cannot inspect a stock original protection.");
    }
}
}
