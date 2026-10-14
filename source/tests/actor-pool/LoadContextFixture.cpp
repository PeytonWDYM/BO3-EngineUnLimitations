// Exercise the actor root policy and immutable reader bindings with owned native-callback endpoints.
#include "../../patches/actor_pool/LoadContext.h"
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>

namespace {
void Require(bool value,const char* reason) {if(!value)throw std::runtime_error(reason);}
unsigned int NativeCalls{};
void NativeRead(void* file,std::uint32_t thread) {
    Require(bo3::actors::ReaderAllowed(file,thread),"An unbound reader reached a native callback.");++NativeCalls;
}
}
int main(int argc,char** argv) {
    try {
        Require(argc==2,"Supply a private actor context receipt path.");
        using namespace bo3::actors;
        ReadCounts counts=LegacyCounts;Bo3ActorLoadBindings={&counts};
        constexpr std::uint32_t bytes=32*1024*1024;
        constexpr auto current=VmOnlyVersion;
        static_assert(current!=Actor500Version && Actor500Version!=3);
        std::array<std::uint32_t,3> versions{3,current,Actor500Version};
        int file{},other{};unsigned int accepted{},refused{};
        for(auto version:versions) {
            const RootHeader header{1024,version,0,0x4864,0,100};
            Require(BeginLoad(header,&file,17,bytes),"An admitted actor load failed.");
            const auto expanded=version==Actor500Version;
            Require(counts.actorBytes==(expanded?500ull:64ull)*0x2110 &&
                    counts.sentientBytes==(expanded?540ull:104ull)*0x3088 &&
                    counts.secondaryRecords==(expanded?500u:64u),"The actor load counts differ.");
            NativeRead(&file,17);++accepted;
            Require(!BeginLoad(header,&file,17,bytes),"A reentrant actor load changed its context.");++refused;
            Require(!ReaderAllowed(&other,17) && !ReaderAllowed(&file,18),"A wrong reader entered the admitted context.");refused+=2;
            bool competitor=true;
            std::thread competing([&] {competitor=BeginLoad(header,&other,18,bytes);});competing.join();
            Require(!competitor,"A competing actor load replaced the context.");++refused;
            Require(!EndLoad(&other,17) && !EndLoad(&file,18),"A wrong owner released the load context.");refused+=2;
            Require(EndLoad(&file,17),"The owning actor load did not close.");
            Require(counts.actorBytes==64ull*0x2110 && counts.sentientBytes==104ull*0x3088 &&
                    counts.secondaryRecords==64 && !ReaderAllowed(&other,18),"Legacy counts or unscoped reader refusal differ.");++refused;
        }
        const RootHeader valid{1024,Actor500Version,0,0x4864,0,100};
        for(auto bad:std::array<RootHeader,5>{{{0,Actor500Version,0,0x4864,0,100},{bytes+1,Actor500Version,0,0x4864,0,100},
                    {1024,0xC927A122,0,0x4864,0,100},{1024,Actor500Version,0,0x4865,0,100},{1024,0xCA27A121,0,0x4864,0,100}}}) {
            Require(!BeginLoad(bad,&file,17,bytes),"An invalid actor root reached a native callback.");++refused;
        }
        Require(!BeginLoad(valid,&file,17,bytes-1) && !BeginLoad(valid,nullptr,17,bytes) && !BeginLoad(valid,&file,0,bytes),
                "Invalid actor binding arguments were admitted.");refused+=3;
        Require(BeginLoad(valid,&file,17,bytes),"The error-context load did not open.");
        ClearLoadContext(18);Require(!ReaderAllowed(&other,18),"A foreign error cleared the owning actor context.");++refused;
        ClearLoadContext(17);Require(!ReaderAllowed(&other,18) && counts.secondaryRecords==64,"Error cleanup retained actor counts.");++refused;
        Require(NativeCalls==3,"An invalid actor root invoked native code.");
        std::ofstream receipt(argv[1]);Require(static_cast<bool>(receipt),"Cannot write the owned actor context receipt.");
        receipt<<"{\"passed\":true,\"acceptedRoots\":"<<accepted<<",\"refusals\":"<<refused
               <<",\"nativeCallbacks\":"<<NativeCalls<<",\"restoredLegacyCounts\":true,\"gameWrites\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
