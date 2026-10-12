// Register the complete prepared actor function table in owned Windows memory.
#include "../../patches/actor_pool/RuntimeBinding.h"
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
void Require(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
std::uint32_t Read32(std::ifstream& file){std::uint32_t value{};file.read(reinterpret_cast<char*>(&value),4);Require(file.good(),"Incomplete actor runtime input.");return value;}
struct Region {
    void* base;
    Region():base(VirtualAlloc(nullptr,0x23000000,MEM_RESERVE,PAGE_NOACCESS)){Require(base!=nullptr,"Cannot reserve owned game and actor ranges.");}
    ~Region(){VirtualFree(base,0,MEM_RELEASE);}
};
}
int main(int argc,char** argv) {
    try {
        Require(argc==3,"Supply the actor frame input and receipt path.");
        using namespace bo3::actors;
        std::ifstream input(argv[1],std::ios::binary);std::array<char,8> magic{};input.read(magic.data(),8);
        Require(magic==std::array<char,8>{'B','O','3','R','T','B','0','1'},"The actor runtime input marker differs.");
        const auto count=Read32(input),phaseCount=Read32(input);Require(count>1900 && count<4096 && phaseCount>0,"The actor runtime count differs.");
        std::vector<bo3::actor_pool::NativeHandlerFrame> phases(phaseCount);
        Region region;const auto game=reinterpret_cast<std::uintptr_t>(region.base),arena=game+0x20000000;
        Require(VirtualAlloc(reinterpret_cast<void*>(arena),0x400000,MEM_COMMIT,PAGE_READWRITE)!=nullptr,"Cannot commit owned code and metadata.");
        auto* table=reinterpret_cast<RUNTIME_FUNCTION*>(arena+0x200000);
        std::vector<std::uint32_t> parents(count);std::uintptr_t metadata=arena+0x210000;
        for(std::uint32_t index=0;index<count;++index) {
            const auto begin=Read32(input),end=Read32(input),bytes=Read32(input);parents[index]=Read32(input);
            Require(begin<end && end<=0x200000 && bytes>=4 && bytes<256,"An actor frame exceeds its owned interval.");
            table[index]={0x20000000+begin,0x20000000+end,static_cast<DWORD>(metadata-game)};
            input.read(reinterpret_cast<char*>(metadata),bytes);Require(input.good(),"Incomplete actor frame metadata.");
            metadata=(metadata+bytes+3)&~std::uintptr_t{3};
        }
        for(std::uint32_t index=0;index<count;++index)if(parents[index]!=UINT32_MAX) {
            Require(parents[index]<count,"An actor frame parent is missing.");
            auto* header=reinterpret_cast<UCHAR*>(game+table[index].UnwindData);
            const auto tail=4+((header[2]+1)&~1u)*2;
            std::memcpy(header+tail,&table[parents[index]],sizeof(RUNTIME_FUNCTION));
        }
        DWORD previous{};
        Require(VirtualProtect(reinterpret_cast<void*>(arena),0x200000,PAGE_EXECUTE_READ,&previous)!=FALSE,"Cannot protect owned actor code.");
        Require(VirtualProtect(reinterpret_cast<void*>(arena+0x200000),0x200000,PAGE_READONLY,&previous)!=FALSE,"Cannot protect owned actor metadata.");
        Require(!ActivateActorRuntime(),"Unpublished actor bindings reached registration.");
        Bo3ActorRuntimeBindings={game,arena,table,count,phaseCount,phases.data()};
        Require(ActivateActorRuntime(),"The complete actor table did not register.");
        Require(!ActivateActorRuntime(),"The actor table registered twice.");
        std::uint32_t lookups{};
        for(std::uint32_t index=0;index<count;++index) {
            for(const auto offset:{table[index].BeginAddress,table[index].EndAddress-1}) {
                DWORD64 base{};const auto* found=RtlLookupFunctionEntry(game+offset,&base,nullptr);
                Require(found==table+index && base==game,"The registered actor lookup differs.");++lookups;
            }
        }
        Require(RtlDeleteFunctionTable(table)!=FALSE,"Cannot delete the owned actor table.");
        DWORD64 base{};Require(RtlLookupFunctionEntry(game+table[0].BeginAddress,&base,nullptr)==nullptr,"The owned actor table remained registered.");
        std::ofstream receipt(argv[2]);Require(receipt.good(),"Cannot write the actor registration receipt.");
        receipt<<"{\"passed\":true,\"runtimeFunctions\":"<<count<<",\"lookups\":"<<lookups<<",\"unpublishedRefused\":true,\"duplicateRefused\":true,\"deleted\":true,\"gameWrites\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
