#include "source/patches/clientfields/PendingProfile.h"
#include "source/patches/clientfields/ClientfieldStorage.h"
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
    throw std::runtime_error("A callback admission mutation was accepted.");
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
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==2,"Use PendingNativeFixture <exact-spans.bin>.");
        OwnedImage owned;Require(owned.base!=nullptr,"Cannot reserve the owned inert image.");
        const auto image=reinterpret_cast<std::uintptr_t>(owned.base);
        std::ifstream input(argv[1],std::ios::binary);
        std::uint32_t count{};input.read(reinterpret_cast<char*>(&count),sizeof(count));
        Require(count==7,"The callback fixture requires seven complete owner guards.");
        std::vector<std::pair<std::uint32_t,std::vector<unsigned char>>> spans;
        std::set<std::uint32_t> pages{0};
        for(std::uint32_t index=0;index<count;++index) {
            std::uint32_t rva{},size{};input.read(reinterpret_cast<char*>(&rva),4);input.read(reinterpret_cast<char*>(&size),4);
            Require(rva==PendingGuards[index].rva && size==PendingGuards[index].size,"The span inventory differs.");
            std::vector<unsigned char> bytes(size);input.read(reinterpret_cast<char*>(bytes.data()),size);
            for(auto page=rva&~4095u;page<rva+size;page+=4096)pages.insert(page);
            spans.emplace_back(rva,std::move(bytes));
        }
        Require(input.good() && input.peek()==EOF,"The native spans are incomplete or have trailing data.");
        for(auto page=0x4992000u;page<0x49B3000u;page+=4096)pages.insert(page);
        pages.insert(0x5124000);
        for(const auto page:pages)
            Require(VirtualAlloc(owned.base+page,4096,MEM_COMMIT,PAGE_READWRITE)!=nullptr,"Cannot commit an owned fixture page.");
        for(const auto& [rva,bytes]:spans)std::memcpy(owned.base+rva,bytes.data(),bytes.size());
        auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(owned.base);
        dos->e_magic=IMAGE_DOS_SIGNATURE;dos->e_lfanew=128;
        auto* pe=reinterpret_cast<IMAGE_NT_HEADERS64*>(owned.base+128);
        pe->Signature=IMAGE_NT_SIGNATURE;pe->FileHeader.Machine=IMAGE_FILE_MACHINE_AMD64;
        pe->FileHeader.TimeDateStamp=1765634846;pe->OptionalHeader.Magic=IMAGE_NT_OPTIONAL_HDR64_MAGIC;
        pe->OptionalHeader.SizeOfImage=494186496;
        auto* pointer=reinterpret_cast<std::uintptr_t*>(owned.base+kPendingPointerRva);
        const auto stock=image+kStockPendingPoolRva;
        std::memset(reinterpret_cast<void*>(stock),0xA5,0x20008);
        auto* counts=reinterpret_cast<std::uint32_t*>(stock+0x20000);counts[0]=counts[1]=0;
        const auto admit=[&]{return AdmitPendingCallbacks(GetCurrentProcess(),image);};
        Require(admit()==0,"The unpublished callback pointer was not admitted.");
        *pointer=stock;Require(admit()==stock,"The original callback backing was not admitted.");
        for(const auto& guard:PendingGuards) {
            auto& byte=owned.base[guard.rva+guard.size-1];byte^=1;Refuse([&]{admit();});byte^=1;
        }
        for(const auto& instruction:PendingInstructions) {
            auto& byte=owned.base[instruction.rva];byte^=1;Refuse([&]{admit();});byte^=1;
        }
        *pointer=stock+32;Refuse([&]{admit();});*pointer=stock;
        for(unsigned int bank=0;bank<2;++bank){counts[bank]=1;Refuse([&]{admit();});counts[bank]=0;}
        for(const auto rva:{0x5124580u,0x5124500u,0x5124680u,0x5124600u}) {
            owned.base[rva]=1;Refuse([&]{admit();});owned.base[rva]=0;
        }
        ++pe->FileHeader.TimeDateStamp;Refuse([&]{admit();});--pe->FileHeader.TimeDateStamp;
        const auto originalStock=vm_startup::ReadStopped(GetCurrentProcess(),stock,0x20008);
        std::uintptr_t rolledBack{};
        {
            ClientfieldStorage storage(GetCurrentProcess(),image);rolledBack=storage.Address();
            Require(storage.Size()==kClientfieldStorageBytes,"The complete clientfield allocation size differs.");
            MEMORY_BASIC_INFORMATION memory{};
            Require(VirtualQuery(reinterpret_cast<void*>(storage.Address()),&memory,sizeof(memory))==sizeof(memory)
                && memory.State==MEM_COMMIT && memory.Protect==PAGE_READWRITE
                && reinterpret_cast<std::uintptr_t>(memory.AllocationBase)==storage.Address()
                && memory.RegionSize>=storage.Size(),"Incomplete callback allocation.");
            const auto zero=vm_startup::ReadStopped(GetCurrentProcess(),storage.Address(),storage.Size());
            Require(std::all_of(zero.begin(),zero.end(),[](unsigned char value){return value==0;}),"Callback storage was not initialized.");
            auto edits=BuildPendingPlan(image,storage.Address(),admit());Require(edits.size()==18,"The callback plan is incomplete.");
            const auto saved=edits;
            vm_startup::Receipt receipt;
            {
                vm_startup::PausedPatch patch(GetCurrentProcess(),edits,receipt);patch.Apply();
                for(const auto& edit:saved)Require(vm_startup::ReadStopped(GetCurrentProcess(),edit.address,edit.replacement.size())==edit.replacement,"Callback publication readback differs.");
                Require(*pointer==storage.Address(),"The expanded callback backing was not published.");
            }
            Require(receipt.rollbackCompleted && receipt.editsWritten==18,"The complete callback rollback failed.");
            for(const auto& edit:saved)Require(vm_startup::ReadStopped(GetCurrentProcess(),edit.address,edit.original.size())==edit.original,"Callback rollback readback differs.");
        }
        Require(Freed(rolledBack),"Uncommitted callback storage leaked.");
        Require(*pointer==stock && vm_startup::ReadStopped(GetCurrentProcess(),stock,0x20008)==originalStock,"The original callback backing changed.");
        std::uintptr_t committed{};
        {
            ClientfieldStorage storage(GetCurrentProcess(),image);committed=storage.Address();
            auto edits=BuildPendingPlan(image,committed,admit());vm_startup::Receipt receipt;
            vm_startup::PausedPatch patch(GetCurrentProcess(),edits,receipt);patch.Apply();patch.Commit();storage.Commit();
        }
        Require(!Freed(committed) && *pointer==committed,"Committed callback storage was released.");
        Require(VirtualFree(reinterpret_cast<void*>(committed),0,MEM_RELEASE)!=FALSE,"Cannot clean up the owned committed fixture.");
        std::cout<<"{\"passed\":true,\"capacityPerLocalClient\":8192,\"bytes\":524296,\"nativeEdits\":18,\"refusals\":"<<refusals
            <<",\"completeRollback\":true,\"commitRetained\":true,\"scope\":\"Owned inert memory and real Windows allocation/publication APIs. No game or peer execution.\"}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
