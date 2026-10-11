#include "source/patches/clientfields/CounterProfile.h"
#include "source/patches/clientfields/PendingProfile.h"
#include "source/patches/clientfields/ClientfieldStorage.h"
#include "CounterManifest.h"
#include "PendingManifest.h"
#include "source/patches/vm_startup/PausedPatch.h"
#include "source/launch/preentry/Identity.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <functional>
#include <iostream>
#include <set>

namespace {
using namespace bo3::clientfields;
unsigned int refusals{};
void Refuse(const std::function<void()>& action) {
    try {action();}catch(const std::exception&){++refusals;return;}
    throw std::runtime_error("A counter admission mutation was accepted.");
}
struct OwnedImage {
    unsigned char* base=static_cast<unsigned char*>(VirtualAlloc(nullptr,494186496,MEM_RESERVE,PAGE_NOACCESS));
    ~OwnedImage(){if(base)VirtualFree(base,0,MEM_RELEASE);}
};
bool Freed(std::uintptr_t address) {
    MEMORY_BASIC_INFORMATION memory{};
    Require(VirtualQuery(reinterpret_cast<void*>(address),&memory,sizeof(memory))==sizeof(memory),"Cannot inspect owned allocation.");
    return memory.State==MEM_FREE;
}
void LoadSpans(const wchar_t* path,std::span<const bo3::enhanced::CodeGuard> guards,
    std::vector<std::pair<std::uint32_t,std::vector<unsigned char>>>& spans,std::set<std::uint32_t>& pages) {
    std::ifstream input(path,std::ios::binary);std::uint32_t count{};
    input.read(reinterpret_cast<char*>(&count),4);
    Require(count==guards.size(),"The complete span inventory is required.");
    for(const auto& guard:guards) {
        std::uint32_t rva{},size{};input.read(reinterpret_cast<char*>(&rva),4);input.read(reinterpret_cast<char*>(&size),4);
        Require(rva==guard.rva && size==guard.size,"A native span differs from its manifest.");
        std::vector<unsigned char> bytes(size);input.read(reinterpret_cast<char*>(bytes.data()),size);
        for(auto page=rva&~4095u;page<rva+size;page+=4096)pages.insert(page);
        spans.emplace_back(rva,std::move(bytes));
    }
    Require(input.good() && input.peek()==EOF,"Incomplete native spans or trailing data.");
}
}
int wmain(int argc,wchar_t** argv) {
    using namespace bo3;
    try {
        Require(argc==3,"Use CountersNativeFixture <counter-spans.bin> <pending-spans.bin>.");
        OwnedImage owned;Require(owned.base!=nullptr,"Cannot reserve owned inert memory.");
        const auto image=reinterpret_cast<std::uintptr_t>(owned.base);
        std::vector<std::pair<std::uint32_t,std::vector<unsigned char>>> spans;
        std::set<std::uint32_t> pages{0,0x5124000};
        LoadSpans(argv[1],CounterGuards,spans,pages);LoadSpans(argv[2],PendingGuards,spans,pages);
        for(auto page=kStockCounterPoolRva&~4095u;page<kStockCounterPoolRva+49152;page+=4096)pages.insert(page);
        for(auto page=0x4992000u;page<0x49B3000u;page+=4096)pages.insert(page);
        for(const auto page:pages)Require(VirtualAlloc(owned.base+page,4096,MEM_COMMIT,PAGE_READWRITE)!=nullptr,"Cannot commit owned memory.");
        for(const auto& [rva,bytes]:spans)std::memcpy(owned.base+rva,bytes.data(),bytes.size());
        auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(owned.base);dos->e_magic=IMAGE_DOS_SIGNATURE;dos->e_lfanew=128;
        auto* pe=reinterpret_cast<IMAGE_NT_HEADERS64*>(owned.base+128);pe->Signature=IMAGE_NT_SIGNATURE;
        pe->FileHeader.Machine=IMAGE_FILE_MACHINE_AMD64;pe->FileHeader.TimeDateStamp=1765634846;
        pe->OptionalHeader.Magic=IMAGE_NT_OPTIONAL_HDR64_MAGIC;pe->OptionalHeader.SizeOfImage=494186496;
        auto* pointer=reinterpret_cast<std::uintptr_t*>(owned.base+kPendingPointerRva);
        *pointer=image+kStockPendingPoolRva;
        const auto admit=[&]{AdmitCounters(GetCurrentProcess(),image);};admit();
        for(const auto& guard:CounterGuards) {
            auto& byte=owned.base[guard.rva+guard.size-1];byte^=1;Refuse(admit);byte^=1;
        }
        for(const auto& row:CounterInstructions) {
            auto& byte=owned.base[row.rva];byte^=1;Refuse(admit);byte^=1;
        }
        for(const auto offset:{0u,24576u,49151u}) {
            auto& byte=owned.base[kStockCounterPoolRva+offset];byte=1;Refuse(admit);byte=0;
        }
        for(const auto rva:{0x5124580u,0x5124500u,0x5124680u,0x5124600u}) {
            owned.base[rva]=1;Refuse(admit);owned.base[rva]=0;
        }
        ++pe->FileHeader.TimeDateStamp;Refuse(admit);--pe->FileHeader.TimeDateStamp;
        for(const auto bad:{std::uintptr_t{0},image+kStockCounterPoolRva,UINTPTR_MAX-16,image+0x100000000ull})
            Refuse([&]{BuildCounterPlan(image,bad);});
        const auto originalCounter=vm_startup::ReadStopped(GetCurrentProcess(),image+kStockCounterPoolRva,49152);
        std::uintptr_t rolledBack{};
        {
            ClientfieldStorage storage(GetCurrentProcess(),image);rolledBack=storage.Address();
            Require(storage.Size()==720912 && storage.CounterAddress()==storage.Address()+524304,"The complete storage layout differs.");
            const auto zero=vm_startup::ReadStopped(GetCurrentProcess(),storage.Address(),storage.Size());
            Require(std::all_of(zero.begin(),zero.end(),[](unsigned char value){return value==0;}),"Incomplete zeroed storage.");
            auto edits=BuildPendingPlan(image,storage.Address(),*pointer);
            auto counters=BuildCounterPlan(image,storage.CounterAddress());
            edits.insert(edits.end(),counters.begin(),counters.end());Require(edits.size()==29,"The combined plan is incomplete.");
            vm_startup::Receipt receipt;
            {
                vm_startup::PausedPatch patch(GetCurrentProcess(),edits,receipt);patch.Apply();
                for(const auto& edit:edits)Require(vm_startup::ReadStopped(GetCurrentProcess(),edit.address,edit.replacement.size())==edit.replacement,"Combined publication differs.");
                Require(*pointer==storage.Address(),"The callback pointer differs.");
            }
            Require(receipt.rollbackCompleted && receipt.editsWritten==29,"Complete rollback failed.");
            for(const auto& edit:edits)Require(vm_startup::ReadStopped(GetCurrentProcess(),edit.address,edit.original.size())==edit.original,"Combined rollback differs.");
        }
        Require(Freed(rolledBack),"Uncommitted combined storage leaked.");
        Require(vm_startup::ReadStopped(GetCurrentProcess(),image+kStockCounterPoolRva,49152)==originalCounter,"The original counter table changed.");
        std::uintptr_t committed{};
        {
            ClientfieldStorage storage(GetCurrentProcess(),image);committed=storage.Address();
            auto edits=BuildPendingPlan(image,committed,*pointer);auto counters=BuildCounterPlan(image,storage.CounterAddress());
            edits.insert(edits.end(),counters.begin(),counters.end());vm_startup::Receipt receipt;
            vm_startup::PausedPatch patch(GetCurrentProcess(),edits,receipt);patch.Apply();patch.Commit();storage.Commit();
        }
        Require(!Freed(committed) && *pointer==committed,"Committed complete storage was released.");
        Require(VirtualFree(reinterpret_cast<void*>(committed),0,MEM_RELEASE)!=FALSE,"Cannot release owned committed storage.");
        std::cout<<"{\"passed\":true,\"counterCapacity\":8192,\"counterBytes\":196608,\"completeBytes\":720912,\"nativeEdits\":29,\"refusals\":"<<refusals
                 <<",\"completeRollback\":true,\"commitRetained\":true,\"gameLaunches\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
