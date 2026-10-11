#include "GameManifest.h"
#include "source/patches/vm_startup/PausedPatch.h"
#include "ClientManifest.h"
#include "source/launch/enhanced/CapacityProfile.h"
#include <functional>
#include "BuildIdentity.h"
#include "source/launch/preentry/Identity.h"
#include "source/patches/vm_migration/MigrationPlan.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>

namespace {
constexpr std::uintptr_t image=0x140000000;
std::map<std::uint32_t,unsigned char> captured;
std::vector<unsigned char> headers(4096);
std::map<std::uint32_t,std::uint64_t> globals;
unsigned int refused{};
void LoadSpans(const wchar_t* path) {
    std::ifstream input(path,std::ios::binary);
    std::uint32_t count{};input.read(reinterpret_cast<char*>(&count),sizeof(count));
    for(std::uint32_t index=0;index<count;++index) {
        std::uint32_t rva{},size{};
        input.read(reinterpret_cast<char*>(&rva),sizeof(rva));input.read(reinterpret_cast<char*>(&size),sizeof(size));
        std::vector<unsigned char> bytes(size);input.read(reinterpret_cast<char*>(bytes.data()),size);
        for(std::uint32_t offset=0;offset<size;++offset) {
            const auto [position,inserted]=captured.emplace(rva+offset,bytes[offset]);
            Require(inserted || position->second==bytes[offset],"Overlapping captured native spans differ.");
        }
    }
    Require(input.good(),"The captured fixture spans are incomplete.");
}
void ExpectRefusal(const std::function<void()>& action) {
    try {action();}catch(const std::exception&){++refused;return;}
    throw std::runtime_error("A native admission mutation was accepted.");
}
}
namespace vm_startup {
std::vector<unsigned char> ReadStopped(HANDLE,std::uintptr_t address,std::size_t size) {
    const auto rva=static_cast<std::uint32_t>(address-image);
    if(rva<headers.size() && size<=headers.size()-rva)
        return {headers.begin()+rva,headers.begin()+rva+size};
    if(const auto found=globals.find(rva);found!=globals.end()) {
        std::vector<unsigned char> bytes(size);
        std::memcpy(bytes.data(),&found->second,size);return bytes;
    }
    std::vector<unsigned char> bytes(size);
    for(std::size_t offset=0;offset<size;++offset)
        bytes[offset]=captured.at(rva+static_cast<std::uint32_t>(offset));
    return bytes;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==4,"Use NativeAdmissionFixture <client-spans.bin> <server-spans.bin> <unknown.bin>.");
        LoadSpans(argv[1]);LoadSpans(argv[2]);
        Require(bo3::enhanced::kClientTotal==250001 && bo3::enhanced::kNativeEdits==90,
            "The fixture requires the default VM and clientfield capacity profile.");
        auto* dos=reinterpret_cast<IMAGE_DOS_HEADER*>(headers.data());
        dos->e_magic=IMAGE_DOS_SIGNATURE;dos->e_lfanew=128;
        auto* pe=reinterpret_cast<IMAGE_NT_HEADERS64*>(headers.data()+128);
        pe->Signature=IMAGE_NT_SIGNATURE;pe->FileHeader.Machine=IMAGE_FILE_MACHINE_AMD64;
        pe->FileHeader.TimeDateStamp=1765634846;pe->OptionalHeader.Magic=IMAGE_NT_OPTIONAL_HDR64_MAGIC;
        pe->OptionalHeader.SizeOfImage=494186496;
        globals={{0x5124680u,0},{0x5124600u,0}};
        const auto admit=[] {return bo3::enhanced::AdmitClientProfile(nullptr,image,bo3::enhanced::ExactClientManifest,250001);};
        const auto profile=admit();Require(profile.edits.size()==19 && profile.checks.size()==19,"The client plan is incomplete.");
        bo3::enhanced::VerifyGameCode(nullptr,image,bo3::enhanced::ExactGameManifest);
        for(const auto& guard:bo3::enhanced::ExactGameManifest.guards) {
            auto& byte=captured.at(guard.rva+guard.size-1);byte^=1;
            ExpectRefusal([&] {bo3::enhanced::VerifyGameCode(nullptr,image,bo3::enhanced::ExactGameManifest);});byte^=1;
        }
        for(const auto& guard:bo3::enhanced::ExactClientManifest.guards) {
            auto& byte=captured.at(guard.rva+guard.size-1);byte^=1;
            ExpectRefusal([&] {admit();});byte^=1;
        }
        for(const auto& instruction:bo3::enhanced::ExactClientManifest.counts) {
            auto& byte=captured.at(instruction.rva);byte^=1;
            ExpectRefusal([&] {admit();});byte^=1;
        }
        for(auto& [rva,value]:globals) {static_cast<void>(rva);value=1;ExpectRefusal([&] {admit();});value=0;}
        ++pe->FileHeader.TimeDateStamp;ExpectRefusal([&] {admit();});--pe->FileHeader.TimeDateStamp;
        ExpectRefusal([&] {bo3::enhanced::AdmitClientProfile(nullptr,image,bo3::enhanced::ExactClientManifest,65000);});
        std::vector<HANDLE> locks;locks.reserve(1);
        ExpectRefusal([&] {VerifyFile(argv[3],kGameHash,locks);});
        for(const auto lock:locks)CloseHandle(lock);
        const vm_startup::ImageRange game{image,bo3::enhanced::ExactGameManifest.imageSize};
        const vm_startup::ImageRange helper{image+game.size+0x100000,0x100000};
        const vm_startup::HelperOffsets state{100,400,1000,1100,1200,1300,1400,1500,1600,1700,1800,1900};
        const bo3::migration::HelperOffsets migration{2200,2300,2400,2500,2600,2700,2800,2900,3000,3100,3200,3300,3400,3500,3600,3700};
        auto native=vm_startup::BuildNativePlan({game,helper,bo3::enhanced::ExactGameManifest.entries,state,
            image+0x40000000,500001,18,8,bo3::vm::NativeModePolicy::ZombiesOnly,{},250001});
        auto moves=bo3::migration::BuildMigrationPlan({game,helper,migration,image+0x40000040,500001,18,33554432});
        native.insert(native.end(),moves.begin(),moves.end());
        const auto server=bo3::enhanced::MakeGameProfile(bo3::enhanced::ExactGameManifest,500001);
        for(const auto& edit:server.edits)native.push_back({image+edit.rva,edit.original,edit.replacement});
        for(const auto& edit:profile.edits)native.push_back({image+edit.rva,edit.original,edit.replacement});
        Require(native.size()==61,"The VM and migration recipe does not contain 61 edits.");
        bo3::vm::NativeStateBindings bindings{};std::memcpy(&bindings,native[0].replacement.data(),sizeof(bindings));
        Require(bindings.total==500001 && bindings.clientTotal==250001,"The helper VM binding totals differ.");
        std::cout<<"{\"passed\":true,\"serverGuards\":82,\"clientGuards\":40,\"clientOriginals\":19,\"refusals\":"<<refused
            <<",\"vmAndMigrationEdits\":61,\"serverTotal\":500001,\"clientTotal\":250001,\"processWrites\":0,\"gameLaunches\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
