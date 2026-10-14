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
    T value{};input.read(reinterpret_cast<char*>(&value),sizeof(value));Require(input.good(),"Incomplete client frame input.");return value;
}
std::vector<std::pair<void*,std::size_t>> clears;
void* Clear(void* address,int value,std::size_t bytes) {
    Require(value==0,"Unexpected owned clear value.");clears.emplace_back(address,bytes);return std::memset(address,value,bytes);
}
void Validate(const unsigned char* address,const std::vector<unsigned char>& expected,std::uintptr_t binding) {
    Require(binding!=0 && std::memcmp(address,expected.data(),expected.size())==0,"A client reset template or binding differs.");
}
void Replace(unsigned char* address,const std::vector<unsigned char>& bytes) {
    DWORD previous{},ignored{};Require(VirtualProtect(address,bytes.size(),PAGE_READWRITE,&previous)!=FALSE,"Cannot write owned client DLL template.");
    std::memcpy(address,bytes.data(),bytes.size());
    Require(VirtualProtect(address,bytes.size(),previous,&ignored)!=FALSE,"Cannot restore owned DLL protection.");
    Require(FlushInstructionCache(GetCurrentProcess(),address,bytes.size())!=FALSE,"Cannot flush owned DLL code.");
}
struct Module {
    HMODULE value{};
    explicit Module(const wchar_t* path):value(LoadLibraryW(path)) {Require(value!=nullptr,"Cannot load owned client-frame DLL.");}
    ~Module(){if(value)FreeLibrary(value);}
    void release(){Require(FreeLibrary(value)!=FALSE,"Cannot unload owned client DLL.");value=nullptr;}
};
struct Frame {std::vector<unsigned char> body,metadata;unsigned char* entry{};};
constexpr std::array<std::uint64_t,8> nonvolatile{0x11001100,0x44004400,0x22002200,0x33003300,0x55005500,0x66006600,0x77007700,0x88008800};
void CheckBytes(const std::vector<unsigned char>& bytes,std::size_t first,std::size_t count,unsigned char canary) {
    for(std::size_t i=0;i<bytes.size();++i)
        Require(bytes[i]==((i>=first && i<first+count) ? 0 : canary),"A complete client clear or canary differs.");
}
void CheckClientBanks(const std::vector<unsigned char>& bytes,std::uint32_t client) {
    const std::size_t first=16+client*0x342720,bank=first+2*0x342720;
    for(std::size_t i=0;i<bytes.size();++i) {
        const bool cleared=(i>=first && i<first+0x342720) || (i>=bank && i<bank+0x342720);
        Require(bytes[i]==(cleared ? 0 : 0xCC),"A native client or appended actor bank clear differs.");
    }
}
}

int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use ClientResetFrameFixture <templates.dll> <templates.bin>.");
        std::ifstream input(argv[2],std::ios::binary);
        Require(Read<std::array<char,8>>(input)==std::array<char,8>{'B','O','3','C','R','F','0','1'},"Unknown client frame input.");
        const auto clientBytes=Read<std::uint32_t>(input);
        Require(clientBytes==1205184 || clientBytes==1237184,"Unsupported complete snapshot layout.");
        std::array<Frame,2> frames{};
        for(std::size_t index=0;index<frames.size();++index) {
            const auto size=Read<std::uint32_t>(input),metadataSize=Read<std::uint32_t>(input);
            Require(size==(index==0 ? 95u : 97u) && metadataSize==8,"Unsupported client reset frame layout.");
            auto& frame=frames[index];frame.body.resize(size);frame.metadata.resize(metadataSize);
            input.read(reinterpret_cast<char*>(frame.body.data()),size);input.read(reinterpret_cast<char*>(frame.metadata.data()),metadataSize);
            Require(input.good(),"Incomplete client reset frame body.");
        }
        Require(input.peek()==EOF,"Trailing client reset frame data.");
        Module module(argv[1]);
        const auto moduleBase=reinterpret_cast<DWORD64>(module.value);
        auto* relay=reinterpret_cast<unsigned char*>(GetProcAddress(module.value,"Bo3OwnedMemsetRelay"));
        auto* target=reinterpret_cast<std::uintptr_t*>(GetProcAddress(module.value,"Bo3OwnedClearTarget"));
        auto* witness=reinterpret_cast<std::uint64_t*>(GetProcAddress(module.value,"Bo3OwnedNonvolatile"));
        auto* invoke=GetProcAddress(module.value,"Bo3OwnedInvoke");
        std::array<FARPROC,2> bridges{GetProcAddress(module.value,"Bo3StartupClientClear"),GetProcAddress(module.value,"Bo3ShutdownClientClear")};
        Require(relay && target && *target==0 && witness && invoke && bridges[0] && bridges[1],"Owned client exports differ.");
        std::array<const char*,2> names{"Bo3ClientStartupResetTemplate","Bo3ClientShutdownResetTemplate"};
        unsigned int contexts{},refusals{};
        std::array<std::uint64_t,64> stack{};auto* returnSlot=stack.data()+32;*returnSlot=0x123456789ABCDEF0ull;
        for(std::size_t index=0;index<frames.size();++index) {
            auto& frame=frames[index];frame.entry=reinterpret_cast<unsigned char*>(GetProcAddress(module.value,names[index]));
            Require(frame.entry!=nullptr,"Missing client template entry.");
            DWORD64 imageBase{};auto* function=RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(frame.entry),&imageBase,nullptr);
            Require(function && imageBase==moduleBase && function->BeginAddress==frame.entry-reinterpret_cast<unsigned char*>(module.value)
                && function->EndAddress==function->BeginAddress+frame.body.size(),"Static client PE lookup differs.");
            Require(std::memcmp(reinterpret_cast<const void*>(moduleBase+function->UnwindData),frame.metadata.data(),8)==0,"Static client PE metadata differs.");
            const auto prefix=index==0 ? 3u : 5u;
            std::vector<unsigned int> offsets{0};
            for(const auto offset:{0u,4u,9u,14u,19u,24u,31u,41u,44u,46u,52u,57u,62u,69u,71u,77u,82u,87u,91u})offsets.push_back(prefix+offset);
            for(const auto offset:offsets) {
                CONTEXT context{};context.ContextFlags=CONTEXT_ALL;context.Rip=reinterpret_cast<DWORD64>(frame.entry+offset);
                context.Rsp=reinterpret_cast<DWORD64>(returnSlot)-((offset<=prefix || offset==prefix+91) ? 0 : 56);
                context.Rbx=nonvolatile[0];context.Rbp=nonvolatile[1];context.Rsi=nonvolatile[2];context.Rdi=nonvolatile[3];
                context.R12=nonvolatile[4];context.R13=nonvolatile[5];context.R14=nonvolatile[6];context.R15=nonvolatile[7];
                PVOID handlerData{};DWORD64 establishedFrame{};
                RtlVirtualUnwind(UNW_FLAG_NHANDLER,moduleBase,context.Rip,function,&context,&handlerData,&establishedFrame,nullptr);
                Require(context.Rip==*returnSlot && context.Rsp==reinterpret_cast<DWORD64>(returnSlot+1),"A client reset boundary unwound incorrectly.");
                Require(std::array<std::uint64_t,8>{context.Rbx,context.Rbp,context.Rsi,context.Rdi,context.R12,context.R13,context.R14,context.R15}==nonvolatile,
                    "Client reset unwind changed nonvolatile registers.");++contexts;
            }
            try {Validate(frame.entry,frame.body,0);}catch(const std::exception&){++refusals;}
            auto bad=frame.body;bad[prefix+24]^=1;
            try {Validate(frame.entry,bad,reinterpret_cast<std::uintptr_t>(&Clear));}catch(const std::exception&){++refusals;}
            Require(std::memcmp(frame.entry,frame.body.data(),frame.body.size())==0,"A refusal wrote client code.");
        }
        Require(refusals==4,"Client reset refusal count differs.");
        std::vector<unsigned char> clients(4*0x342720+32,0xCC),snapshots(2*clientBytes+32,0xDD);
        const auto snapshotAddress=reinterpret_cast<std::uintptr_t>(snapshots.data()+16);
        for(std::size_t index=0;index<frames.size();++index) {
            auto& frame=frames[index];Validate(frame.entry,frame.body,reinterpret_cast<std::uintptr_t>(&Clear));
            const auto prefix=index==0 ? 3u : 5u;auto replacement=frame.body;
            for(const auto offset:{prefix+14,prefix+52,prefix+77}) {
                const auto difference=reinterpret_cast<std::intptr_t>(relay)-reinterpret_cast<std::intptr_t>(frame.entry+offset+5);
                Require(difference>=INT32_MIN && difference<=INT32_MAX,"Owned client clear relay is unreachable.");
                const auto relative=static_cast<std::int32_t>(difference);std::memcpy(replacement.data()+offset+1,&relative,4);
            }
            std::memcpy(replacement.data()+prefix+33,&snapshotAddress,8);Replace(frame.entry,replacement);
        }
        *target=reinterpret_cast<std::uintptr_t>(&Clear);
        using Invoke=void* (*)(void*,int,std::size_t,std::uint32_t,FARPROC);
        const auto call=reinterpret_cast<Invoke>(invoke);
        unsigned int resets{};
        for(std::size_t index=0;index<frames.size();++index)for(std::uint32_t client=0;client<2;++client)for(unsigned int iteration=0;iteration<2;++iteration) {
            std::memset(clients.data(),0xCC,clients.size());std::memset(snapshots.data(),0xDD,snapshots.size());clears.clear();
            auto* cg=clients.data()+16+client*0x342720;auto* external=snapshots.data()+16+client*clientBytes;
            Require(call(cg,0,0x342720,client,bridges[index])==cg,"Client reset return differs.");
            Require(clears==std::vector<std::pair<void*,std::size_t>>{{cg,0x342720},{external,clientBytes},{cg+2*0x342720,0x342720}},"Client reset order, ownership, or extent differs.");
            Require(std::memcmp(witness,nonvolatile.data(),sizeof(nonvolatile))==0,"An actual client reset changed nonvolatile registers.");
            CheckClientBanks(clients,client);CheckBytes(snapshots,16+client*clientBytes,clientBytes,0xDD);++resets;
        }
        std::array<DWORD64,2> entries{reinterpret_cast<DWORD64>(frames[0].entry),reinterpret_cast<DWORD64>(frames[1].entry)};
        module.release();
        for(const auto address:entries) {DWORD64 base{};Require(RtlLookupFunctionEntry(address,&base,nullptr)==nullptr,"Client lookup survived DLL unload.");}
        std::cout<<"{\"passed\":true,\"windowsUnwindContexts\":"<<contexts<<",\"refusals\":"<<refusals<<",\"completeResets\":"<<resets
                 <<",\"snapshotBytesPerLocalClient\":"<<clientBytes<<",\"actualNonvolatileChecks\":"<<resets
                 <<",\"lookupRemovedOnUnload\":true,\"dynamicRegistrations\":0,\"gameLaunches\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
