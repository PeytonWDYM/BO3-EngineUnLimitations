#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
void Require(bool condition,const char* message) {if(!condition)throw std::runtime_error(message);}
template<class T> T Read(std::ifstream& input) {
    T value{};input.read(reinterpret_cast<char*>(&value),sizeof(value));Require(input.good(),"Incomplete static frame input.");return value;
}
std::vector<std::pair<void*,std::size_t>> clears;
void* Clear(void* address,int value,std::size_t bytes) {
    Require(value==0,"Unexpected owned clear value.");clears.emplace_back(address,bytes);return std::memset(address,value,bytes);
}
void Validate(const unsigned char* address,const std::vector<unsigned char>& expected,std::uintptr_t binding) {
    Require(binding!=0 && std::memcmp(address,expected.data(),expected.size())==0,"A static frame template or binding differs.");
}
void Replace(unsigned char* address,const std::vector<unsigned char>& bytes) {
    DWORD previous{},ignored{};Require(VirtualProtect(address,bytes.size(),PAGE_READWRITE,&previous)!=FALSE,"Cannot write owned DLL template.");
    std::memcpy(address,bytes.data(),bytes.size());
    Require(VirtualProtect(address,bytes.size(),previous,&ignored)!=FALSE,"Cannot restore owned DLL protection.");
    Require(FlushInstructionCache(GetCurrentProcess(),address,bytes.size())!=FALSE,"Cannot flush owned DLL code.");
}
struct Module {
    HMODULE value{};
    explicit Module(const wchar_t* path):value(LoadLibraryW(path)) {Require(value!=nullptr,"Cannot load owned static-frame DLL.");}
    ~Module(){if(value)FreeLibrary(value);}
    void release(){Require(FreeLibrary(value)!=FALSE,"Cannot unload owned DLL.");value=nullptr;}
};
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use StaticFrameFixture <template.dll> <template.bin>.");
        std::ifstream input(argv[2],std::ios::binary);
        Require(Read<std::array<char,8>>(input)==std::array<char,8>{'B','O','3','S','F','M','0','1'},"Unknown static frame input.");
        const auto codeSize=Read<std::uint32_t>(input),metadataSize=Read<std::uint32_t>(input),historyBytes=Read<std::uint32_t>(input);
        Require(codeSize==47 && metadataSize==8 && (historyBytes==156080 || historyBytes==260080),"Unsupported reset template layout.");
        std::vector<unsigned char> original(codeSize),metadata(metadataSize);
        input.read(reinterpret_cast<char*>(original.data()),codeSize);input.read(reinterpret_cast<char*>(metadata.data()),metadataSize);
        Require(input.good() && input.peek()==EOF,"Incomplete static template input or trailing data.");
        Module module(argv[1]);
        auto* entry=reinterpret_cast<unsigned char*>(GetProcAddress(module.value,"Bo3HistoryResetTemplate"));
        auto* relay=reinterpret_cast<unsigned char*>(GetProcAddress(module.value,"Bo3OwnedMemsetRelay"));
        auto* clearTarget=reinterpret_cast<std::uintptr_t*>(GetProcAddress(module.value,"Bo3OwnedClearTarget"));
        Require(entry && relay && clearTarget && *clearTarget==0,"The owned module exports differ.");
        const auto moduleBase=reinterpret_cast<DWORD64>(module.value);
        DWORD64 imageBase{};auto* function=RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry),&imageBase,nullptr);
        Require(function && imageBase==moduleBase && function->BeginAddress==entry-reinterpret_cast<unsigned char*>(module.value)
            && function->EndAddress==function->BeginAddress+codeSize,"Static PE function lookup differs.");
        Require(std::memcmp(reinterpret_cast<const void*>(moduleBase+function->UnwindData),metadata.data(),metadata.size())==0,"Static PE metadata differs.");
        std::array<std::uint64_t,64> stack{};auto* returnSlot=stack.data()+32;*returnSlot=0x123456789ABCDEF0ull;
        unsigned int contexts{};
        for(const auto offset:{0u,4u,9u,19u,21u,27u,32u,42u,46u}) {
            CONTEXT context{};context.ContextFlags=CONTEXT_ALL;context.Rip=reinterpret_cast<DWORD64>(entry+offset);
            context.Rsp=reinterpret_cast<DWORD64>(returnSlot)-((offset==0 || offset==46) ? 0 : 40);
            context.Rbx=0x11001100;context.Rsi=0x22002200;context.Rdi=0x33003300;context.Rbp=0x44004400;
            context.R12=0x55005500;context.R13=0x66006600;context.R14=0x77007700;context.R15=0x88008800;
            const auto before=context;PVOID handlerData{};DWORD64 frame{};
            RtlVirtualUnwind(UNW_FLAG_NHANDLER,moduleBase,context.Rip,function,&context,&handlerData,&frame,nullptr);
            Require(context.Rip==*returnSlot && context.Rsp==reinterpret_cast<DWORD64>(returnSlot+1),"Static reset frame unwound incorrectly.");
            Require(context.Rbx==before.Rbx && context.Rsi==before.Rsi && context.Rdi==before.Rdi && context.Rbp==before.Rbp
                && context.R12==before.R12 && context.R13==before.R13 && context.R14==before.R14 && context.R15==before.R15,"Static reset unwind changed nonvolatile registers.");
            ++contexts;
        }
        unsigned int refusals{};
        try {Validate(entry,original,0);}catch(const std::exception&){++refusals;}
        auto bad=original;bad.back()^=1;
        try {Validate(entry,bad,reinterpret_cast<std::uintptr_t>(&Clear));}catch(const std::exception&){++refusals;}
        Require(refusals==2 && std::memcmp(entry,original.data(),original.size())==0,"Template refusal wrote code or admitted a change.");
        Validate(entry,original,reinterpret_cast<std::uintptr_t>(&Clear));
        std::vector<unsigned char> level(0x23A10+32,0xCC),history(historyBytes+32,0xDD);
        auto replacement=original;
        for(const auto offset:{4u,27u}) {
            const auto difference=reinterpret_cast<std::intptr_t>(relay)-reinterpret_cast<std::intptr_t>(entry+offset+5);
            Require(difference>=INT32_MIN && difference<=INT32_MAX,"Owned clear relay is unreachable.");
            const auto relative=static_cast<std::int32_t>(difference);std::memcpy(replacement.data()+offset+1,&relative,4);
        }
        const auto historyAddress=reinterpret_cast<std::uintptr_t>(history.data()+16),levelAddress=reinterpret_cast<std::uintptr_t>(level.data()+16);
        std::memcpy(replacement.data()+11,&historyAddress,8);std::memcpy(replacement.data()+34,&levelAddress,8);
        *clearTarget=reinterpret_cast<std::uintptr_t>(&Clear);Replace(entry,replacement);
        using Reset=void* (*)(void*,int,std::size_t);
        const auto reset=reinterpret_cast<Reset>(entry);
        for(unsigned int iteration=0;iteration<2;++iteration) {
            std::memset(level.data()+16,0xAA,0x23A10);std::memset(history.data()+16,0xBB,historyBytes);clears.clear();
            Require(reset(level.data()+16,0,0x23A10)==level.data()+16,"The reset return address differs.");
            Require(clears==std::vector<std::pair<void*,std::size_t>>{{level.data()+16,0x23A10},{history.data()+16,historyBytes}},"Reset clear order or extent differs.");
            for(std::size_t i=0;i<level.size();++i)Require(level[i]==((i<16 || i>=level.size()-16) ? 0xCC : 0),"Level reset or canary differs.");
            for(std::size_t i=0;i<history.size();++i)Require(history[i]==((i<16 || i>=history.size()-16) ? 0xDD : 0),"History reset or canary differs.");
        }
        const auto address=reinterpret_cast<DWORD64>(entry);module.release();imageBase=0;
        Require(RtlLookupFunctionEntry(address,&imageBase,nullptr)==nullptr,"Static function lookup survived unload.");
        std::cout<<"{\"passed\":true,\"windowsUnwindContexts\":"<<contexts<<",\"refusals\":"<<refusals
                 <<",\"completeResets\":2,\"historyBytes\":"<<historyBytes<<",\"staticModuleLookup\":true,\"lookupRemovedOnUnload\":true,\"dynamicRegistrations\":0,\"gameLaunches\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
