#include "MappedGate.h"
#include "../enhanced/Boot.h"
#include "../preentry/Identity.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <Psapi.h>
#include <algorithm>
#include <array>
#include <cstring>

namespace bo3::late_startup {
namespace {
const IMAGE_NT_HEADERS64& Header(HMODULE module) {
    const auto base=reinterpret_cast<const unsigned char*>(module);
    const auto dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    Require(dos->e_magic==IMAGE_DOS_SIGNATURE && dos->e_lfanew>0,"The gate DOS header differs.");
    const auto& header=*reinterpret_cast<const IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
    Require(header.Signature==IMAGE_NT_SIGNATURE && header.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64
        && header.OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC,"The gate requires an x64 DLL.");
    return header;
}
void Relocate(HMODULE local,std::uintptr_t remote,DWORD rva,std::vector<unsigned char>& bytes) {
    const auto& header=Header(local);const auto& directory=header.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    const auto base=reinterpret_cast<const unsigned char*>(local);const auto delta=remote-reinterpret_cast<std::uintptr_t>(local);
    DWORD position=0;
    while(position<directory.Size) {
        Require(directory.VirtualAddress<=header.OptionalHeader.SizeOfImage
            && directory.Size<=header.OptionalHeader.SizeOfImage-directory.VirtualAddress
            && sizeof(IMAGE_BASE_RELOCATION)<=directory.Size-position,"Invalid gate relocation range.");
        const auto block=reinterpret_cast<const IMAGE_BASE_RELOCATION*>(base+directory.VirtualAddress+position);
        Require(block->SizeOfBlock>=sizeof(*block) && block->SizeOfBlock<=directory.Size-position
            && (block->SizeOfBlock-sizeof(*block))%2==0,"Invalid gate relocation block.");
        const auto entries=reinterpret_cast<const WORD*>(block+1);
        for(std::size_t i=0;i<(block->SizeOfBlock-sizeof(*block))/2;++i) {
            const auto type=entries[i]>>12;const auto offset=std::uint64_t{block->VirtualAddress}+(entries[i]&0xfff);
            if(type==IMAGE_REL_BASED_ABSOLUTE || offset<rva || offset>=std::uint64_t{rva}+bytes.size())continue;
            Require(type==IMAGE_REL_BASED_DIR64 && bytes.size()>=8 && offset-rva<=bytes.size()-8,"Unsupported gate relocation.");
            std::uintptr_t value{};std::memcpy(&value,bytes.data()+offset-rva,8);value+=delta;
            std::memcpy(bytes.data()+offset-rva,&value,8);
        }
        position+=block->SizeOfBlock;
    }
}
}
MappedGate::MappedGate(const std::filesystem::path& file):file_(file),local_(LoadLibraryExW(file.c_str(),nullptr,DONT_RESOLVE_DLL_REFERENCES)) {
    Require(local_!=nullptr,"Cannot inspect the exact gate DLL.");
    try {
        size_=Header(local_).OptionalHeader.SizeOfImage;
        const auto offset=reinterpret_cast<std::uintptr_t>(GetProcAddress(local_,"Bo3StartupGateState"))-reinterpret_cast<std::uintptr_t>(local_);
        Require(size_>=sizeof(startup_gate::State) && offset<size_ && offset<=size_-sizeof(startup_gate::State),"Missing bounded gate state export.");
        stateRva_=static_cast<DWORD>(offset);
        const auto boot=reinterpret_cast<std::uintptr_t>(GetProcAddress(local_,"Bo3StartupGateBoot"))-reinterpret_cast<std::uintptr_t>(local_);
        Require(size_>=sizeof(enhanced::BootRecord) && boot<size_ && boot<=size_-sizeof(enhanced::BootRecord),"Missing bounded gate boot export.");
        bootRva_=static_cast<DWORD>(boot);
    } catch(...) {FreeLibrary(local_);throw;}
}
MappedGate::~MappedGate(){FreeLibrary(local_);}
void MappedGate::Admit(HANDLE process) {
    std::array<HMODULE,2048> modules{};DWORD bytes{};
    Require(K32EnumProcessModulesEx(process,modules.data(),sizeof(modules),&bytes,LIST_MODULES_64BIT)
        && bytes<=sizeof(modules) && bytes%sizeof(HMODULE)==0,"Cannot enumerate the gate modules.");
    remote_=0;
    for(std::size_t i=0;i<bytes/sizeof(HMODULE);++i) {
        std::array<wchar_t,32768> name{};
        const auto length=K32GetModuleFileNameExW(process,modules[i],name.data(),static_cast<DWORD>(name.size()));
        Require(length && length<name.size(),"Cannot read the gate module path.");
        if(std::filesystem::equivalent(file_,name.data())) {Require(!remote_,"Multiple gate module identities.");remote_=reinterpret_cast<std::uintptr_t>(modules[i]);}
    }
    Require(remote_ && remote_<=UINTPTR_MAX-size_,"The gate module is missing or exceeds its address range.");
    const auto bootBytes=vm_startup::ReadStopped(process,remote_+bootRva_,sizeof(enhanced::BootRecord));
    enhanced::BootRecord boot{};std::memcpy(&boot,bootBytes.data(),sizeof(boot));
    Require(boot.abi==enhanced::BootAbi && boot.bytes==sizeof(boot) && boot.module==remote_ && boot.ready==1 && !boot.reserved,
        "The gate helper did not publish its exact boot identity.");
    const auto& header=Header(local_);const auto sections=IMAGE_FIRST_SECTION(&header);unsigned int verified=0;
    for(unsigned int i=0;i<header.FileHeader.NumberOfSections;++i) {
        const auto& section=sections[i];
        if(!(section.Characteristics&IMAGE_SCN_MEM_EXECUTE) && std::memcmp(section.Name,".pdata",6)
            && std::memcmp(section.Name,".rdata",6))continue;
        const auto rva=section.VirtualAddress,size=section.Misc.VirtualSize;
        Require(size && size<=size_ && rva<=size_-size,"A gate section exceeds its image.");
        const auto begin=reinterpret_cast<const unsigned char*>(local_)+rva;
        std::vector<unsigned char> expected(begin,begin+size);Relocate(local_,remote_,rva,expected);
        auto observed=vm_startup::ReadStopped(process,remote_+rva,size);
        const auto& iat=header.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IAT];
        const auto first=std::max<std::uint64_t>(rva,iat.VirtualAddress);
        const auto last=std::min<std::uint64_t>(std::uint64_t{rva}+size,std::uint64_t{iat.VirtualAddress}+iat.Size);
        if(first<last)std::copy(expected.begin()+first-rva,expected.begin()+last-rva,observed.begin()+first-rva);
        Require(expected==observed,"The gate code or unwind metadata differs.");++verified;
    }
    Require(verified>=3,"The gate needs code, read-only data and unwind metadata.");
}
startup_gate::State MappedGate::Read(HANDLE process) const {
    Require(remote_!=0,"The gate module has not been admitted.");
    const auto bytes=vm_startup::ReadStopped(process,remote_+stateRva_,sizeof(startup_gate::State));
    startup_gate::State state{};std::memcpy(&state,bytes.data(),sizeof(state));return state;
}
void MappedGate::VerifyWaiting(HANDLE process,const startup_gate::Payload& payload,std::uint64_t generation) const {
    const auto state=Read(process);
    Require(state.abi==startup_gate::Abi && state.bytes==sizeof(state)
        && state.phase==static_cast<LONG>(startup_gate::Phase::Waiting) && !state.refusal
        && state.processId==payload.processId && state.primaryThreadId==payload.primaryThreadId
        && state.callbackThreadId==payload.primaryThreadId && state.processCreatedFileTime==payload.processCreatedFileTime
        && state.nonce[0]==payload.nonce[0] && state.nonce[1]==payload.nonce[1] && generation==1 && state.generation==generation
        && state.loaderCallout==0 && state.observationCount==1 && state.returnSite && state.wrapperCallerReturn
        && state.entryAnchorStart && state.entryAnchorEnd>state.entryAnchorStart && state.entryFrameCount>=1
        && state.entryFrameCount<=64 && state.entryAnchorPresent==1,
        "The exact process-bound CRT callback is not waiting.");
    Require(GetProcessId(process)==payload.processId && Created(process)==payload.processCreatedFileTime,
        "The owned gate process identity changed.");
}
}
